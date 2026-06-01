"""Scrape a website for brand signals: title, copy, logo candidates, colors, fonts.

Pure parsing logic (color/font regexes, candidate ranking) is dependency-free and
unit-tested directly. Network fetching and HTML parsing import requests/bs4 lazily.
"""
from __future__ import annotations

import json
import re
from collections import Counter
from dataclasses import dataclass, field
from urllib.parse import urljoin, urlparse

USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) BrandGuide/0.1 Safari/537.36"
)

HEX_RE = re.compile(r"#(?:[0-9a-fA-F]{3}|[0-9a-fA-F]{6})\b")
RGB_RE = re.compile(r"rgba?\(\s*(\d{1,3})\s*,\s*(\d{1,3})\s*,\s*(\d{1,3})")
FONT_RE = re.compile(r"font-family\s*:\s*([^;}{]+)", re.IGNORECASE)

# Near-greyscale colors rarely carry brand identity; we down-rank them.
_GREYISH_TOLERANCE = 12


@dataclass
class ScrapeResult:
    url: str
    final_url: str = ""
    title: str = ""
    description: str = ""
    og_image: str = ""
    text_sample: str = ""
    logo_candidates: list[str] = field(default_factory=list)
    colors: list[str] = field(default_factory=list)
    fonts: list[str] = field(default_factory=list)
    product_images: list[str] = field(default_factory=list)
    lifestyle_images: list[str] = field(default_factory=list)
    social_images: list[str] = field(default_factory=list)
    social_links: dict = field(default_factory=dict)

    @property
    def domain(self) -> str:
        return urlparse(self.final_url or self.url).netloc


def _norm_hex(value: str) -> str:
    """Normalize #abc -> #aabbcc, lowercase."""
    v = value.lstrip("#").lower()
    if len(v) == 3:
        v = "".join(ch * 2 for ch in v)
    return "#" + v


def _rgb_to_hex(r: int, g: int, b: int) -> str:
    return "#%02x%02x%02x" % (min(r, 255), min(g, 255), min(b, 255))


def _is_greyish(hex_color: str) -> bool:
    r = int(hex_color[1:3], 16)
    g = int(hex_color[3:5], 16)
    b = int(hex_color[5:7], 16)
    return max(r, g, b) - min(r, g, b) <= _GREYISH_TOLERANCE


def extract_colors(css_text: str, *, limit: int = 6) -> list[str]:
    """Return the most frequent brand-ish colors, greys de-prioritized."""
    counts: Counter[str] = Counter()
    for m in HEX_RE.findall(css_text):
        counts[_norm_hex(m)] += 1
    for r, g, b in RGB_RE.findall(css_text):
        counts[_rgb_to_hex(int(r), int(g), int(b))] += 1
    # Drop pure black/white which dominate every site.
    for trivial in ("#000000", "#ffffff"):
        counts.pop(trivial, None)
    ordered = sorted(
        counts.items(),
        key=lambda kv: (_is_greyish(kv[0]), -kv[1]),  # non-grey first, then freq
    )
    return [hex_ for hex_, _ in ordered[:limit]]


def extract_fonts(css_text: str, *, limit: int = 4) -> list[str]:
    seen: list[str] = []
    for decl in FONT_RE.findall(css_text):
        first = decl.split(",")[0].strip().strip("'\"")
        generic = {"sans-serif", "serif", "monospace", "inherit", "initial", ""}
        if first.lower() in generic or first in seen:
            continue
        seen.append(first)
        if len(seen) >= limit:
            break
    return seen


def rank_logo_candidates(candidates: list[str]) -> list[str]:
    """Order logo URLs best-first: explicit 'logo' assets > touch icons > favicons."""
    def score(u: str) -> int:
        low = u.lower()
        s = 0
        if "logo" in low:
            s += 100
        if low.endswith(".svg"):
            s += 40
        if "apple-touch-icon" in low:
            s += 30
        if low.endswith((".png", ".webp")):
            s += 20
        if "favicon" in low or low.endswith(".ico"):
            s -= 20  # usually tiny/low quality
        return s

    seen, ordered = set(), []
    for u in sorted(candidates, key=score, reverse=True):
        if u not in seen:
            seen.add(u)
            ordered.append(u)
    return ordered


# Image classification by surrounding context (alt/class/id/url).
IMG_SKIP = (
    "logo", "favicon", "icon", "sprite", "badge", "avatar", "pixel", "spacer",
    "1x1", "placeholder", "loading", "data:image", ".svg",
)
PRODUCT_KW = (
    "product", "/products/", "/shop", "shop-", "/cdn/shop/products", "item",
    "bottle", "pack", "/sku", "pdp", "/collection", "swatch",
)
SOCIAL_KW = ("instagram", "insta-", "tiktok", "ugc", "social", "/feed", "user-generated")
LIFESTYLE_KW = (
    "hero", "lifestyle", "banner", "editorial", "story", "about", "model",
    "people", "feature", "campaign", "lookbook",
)

SOCIAL_DOMAINS = {
    "instagram.com": "instagram", "tiktok.com": "tiktok", "twitter.com": "x",
    "x.com": "x", "facebook.com": "facebook", "youtube.com": "youtube",
    "pinterest.com": "pinterest", "linkedin.com": "linkedin",
}


def classify_image(context: str) -> str | None:
    """Bucket an image as product / social / lifestyle from its context, or skip."""
    h = context.lower()
    if any(k in h for k in IMG_SKIP):
        return None
    if any(k in h for k in SOCIAL_KW):
        return "social"
    if any(k in h for k in PRODUCT_KW):
        return "product"
    if any(k in h for k in LIFESTYLE_KW):
        return "lifestyle"
    return None


def best_img_src(img, base: str) -> str:
    """Resolve the largest available image URL from src/data-src/srcset."""
    best, best_w = None, -1
    srcset = img.get("srcset") or img.get("data-srcset") or ""
    for part in srcset.split(","):
        bits = part.strip().split()
        if not bits:
            continue
        w = 0
        if len(bits) > 1 and bits[1].endswith("w"):
            try:
                w = int(bits[1][:-1])
            except ValueError:
                w = 0
        if w >= best_w:
            best_w, best = w, bits[0]
    src = best or img.get("src") or img.get("data-src") or ""
    return urljoin(base, src) if src else ""


def _social_links(soup) -> dict:
    links: dict = {}
    for a in soup.find_all("a", href=True):
        low = a["href"].lower()
        if any(s in low for s in ("sharer", "intent/", "/share?", "share-offsite")):
            continue  # share buttons, not the brand's own profile
        for domain, name in SOCIAL_DOMAINS.items():
            if domain in low and name not in links:
                links[name] = a["href"]
    return links


def render_html_playwright(url: str, *, timeout_ms: int = 30000, scrolls: int = 4) -> tuple:
    """Render a JS-heavy page with headless Chromium and return (html, final_url).

    Scrolls a few times so lazy-loaded product grids and feeds populate. Requires
    the optional 'playwright' extra plus a browser: `playwright install chromium`.
    """
    try:
        from playwright.sync_api import sync_playwright
    except ImportError as exc:  # pragma: no cover
        raise RuntimeError(
            "Rendering needs Playwright. Install: pip install playwright "
            "&& playwright install chromium"
        ) from exc
    with sync_playwright() as pw:  # pragma: no cover - exercised with a real browser
        browser = pw.chromium.launch(headless=True)
        try:
            page = browser.new_page(
                user_agent=USER_AGENT, viewport={"width": 1366, "height": 900}
            )
            # 'domcontentloaded' is far more reliable than 'networkidle', which
            # hangs on sites with persistent connections (analytics, long-poll).
            page.goto(url, wait_until="domcontentloaded", timeout=timeout_ms)
            page.wait_for_timeout(1500)  # let initial JS hydrate
            for _ in range(scrolls):  # trigger lazy-loaded galleries / feeds
                page.mouse.wheel(0, 2200)
                page.wait_for_timeout(700)
            return page.content(), page.url
        finally:
            browser.close()


def fetch(
    url: str, *, timeout: int = 15, session: object | None = None, render: bool = False
) -> ScrapeResult:
    """Fetch and parse a page into a ScrapeResult.

    With render=True, the page is loaded in headless Chromium first so
    JavaScript-rendered content (lazy galleries, SPAs) is captured.
    """
    if not url.startswith(("http://", "https://")):
        url = "https://" + url
    try:
        import requests
        from bs4 import BeautifulSoup
    except ImportError as exc:  # pragma: no cover
        raise RuntimeError(
            "BrandGuide needs 'requests' and 'beautifulsoup4'. "
            "Install: pip install requests beautifulsoup4"
        ) from exc

    http = session or requests
    if render:
        html, final_url = render_html_playwright(url, timeout_ms=timeout * 2000)
    else:
        resp = http.get(url, headers={"User-Agent": USER_AGENT}, timeout=timeout)
        html = resp.text
        final_url = str(getattr(resp, "url", url))
    soup = BeautifulSoup(html, "html.parser")

    result = ScrapeResult(url=url, final_url=final_url)

    if soup.title and soup.title.string:
        result.title = soup.title.string.strip()

    def meta(name: str, attr: str = "name") -> str:
        tag = soup.find("meta", attrs={attr: name})
        return (tag.get("content") or "").strip() if tag else ""

    result.description = meta("description") or meta("og:description", "property")
    result.og_image = meta("og:image", "property")

    # Visible copy that signals voice (headings + first paragraphs).
    chunks = []
    for tag in soup.find_all(["h1", "h2", "h3", "p"]):
        t = tag.get_text(" ", strip=True)
        if t:
            chunks.append(t)
        if sum(len(c) for c in chunks) > 1800:
            break
    result.text_sample = "\n".join(chunks)[:1800]

    # Logo candidates from icons + og:image + <img>/<svg> tagged "logo".
    candidates: list[str] = []
    for link in soup.find_all("link", rel=True):
        rels = " ".join(link.get("rel", [])).lower()
        if "icon" in rels and link.get("href"):
            candidates.append(urljoin(final_url, link["href"]))
    if result.og_image:
        candidates.append(urljoin(final_url, result.og_image))
    for img in soup.find_all("img"):
        hay = " ".join(
            str(img.get(a, "")) for a in ("src", "alt", "class", "id")
        ).lower()
        if "logo" in hay and img.get("src"):
            candidates.append(urljoin(final_url, img["src"]))
    result.logo_candidates = rank_logo_candidates(candidates)

    # Content imagery: product photos, lifestyle photos, social reference photos.
    buckets = {"product": [], "lifestyle": [], "social": []}

    def _add(cat: str, u: str) -> None:
        if u and u not in buckets[cat] and u not in result.logo_candidates:
            buckets[cat].append(u)

    # JSON-LD Product images are the most reliable product photos.
    for sc in soup.find_all("script", attrs={"type": "application/ld+json"}):
        try:
            data = json.loads(sc.get_text() or "{}")
        except Exception:
            continue
        objs = data if isinstance(data, list) else [data]
        for obj in objs:
            if not isinstance(obj, dict):
                continue
            nodes = obj.get("@graph", [obj]) if isinstance(obj.get("@graph"), list) else [obj]
            for node in nodes:
                if not isinstance(node, dict):
                    continue
                t = node.get("@type", "")
                t = " ".join(t) if isinstance(t, list) else str(t)
                if "Product" not in t:
                    continue
                imgs = node.get("image")
                for im in (imgs if isinstance(imgs, list) else [imgs]):
                    if isinstance(im, str):
                        _add("product", urljoin(final_url, im))
                    elif isinstance(im, dict) and im.get("url"):
                        _add("product", urljoin(final_url, im["url"]))

    # Classify <img> tags by their surrounding context.
    for img in soup.find_all("img"):
        hay = " ".join(
            str(img.get(a, "")) for a in ("src", "data-src", "srcset", "alt", "class", "id")
        )
        cat = classify_image(hay)
        if cat:
            _add(cat, best_img_src(img, final_url))

    # og:image is a representative brand/lifestyle image.
    if result.og_image:
        _add("lifestyle", urljoin(final_url, result.og_image))

    result.product_images = buckets["product"][:8]
    result.lifestyle_images = buckets["lifestyle"][:5]
    result.social_images = buckets["social"][:6]
    result.social_links = _social_links(soup)

    # Colors + fonts from inline styles and linked stylesheets (bounded).
    css_text = " ".join(s.get_text() for s in soup.find_all("style"))
    css_text += " " + " ".join(
        str(t.get("style", "")) for t in soup.find_all(style=True)
    )
    for sheet in soup.find_all("link", rel="stylesheet")[:3]:
        href = sheet.get("href")
        if not href:
            continue
        try:
            css = http.get(
                urljoin(final_url, href), headers={"User-Agent": USER_AGENT}, timeout=8
            )
            css_text += " " + css.text
        except Exception:
            continue  # a missing stylesheet shouldn't sink the whole scrape

    # Google Fonts hint via <link href=...fonts.googleapis.com?family=...>
    for ln in soup.find_all("link", href=True):
        if "fonts.googleapis.com" in ln["href"]:
            css_text += " font-family: " + ln["href"]

    result.colors = extract_colors(css_text)
    result.fonts = extract_fonts(css_text)
    return result
