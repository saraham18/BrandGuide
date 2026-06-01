"""Scrape a website for brand signals: title, copy, logo candidates, colors, fonts.

Pure parsing logic (color/font regexes, candidate ranking) is dependency-free and
unit-tested directly. Network fetching and HTML parsing import requests/bs4 lazily.
"""
from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass, field
from urllib.parse import urljoin, urlparse

USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) BrandForge/0.1 Safari/537.36"
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


def fetch(url: str, *, timeout: int = 15, session: object | None = None) -> ScrapeResult:
    """Fetch and parse a page into a ScrapeResult."""
    if not url.startswith(("http://", "https://")):
        url = "https://" + url
    try:
        import requests
        from bs4 import BeautifulSoup
    except ImportError as exc:  # pragma: no cover
        raise RuntimeError(
            "BrandForge needs 'requests' and 'beautifulsoup4'. "
            "Install: pip install requests beautifulsoup4"
        ) from exc

    http = session or requests
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
