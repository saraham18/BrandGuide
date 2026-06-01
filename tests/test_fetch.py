"""Exercise the HTML parsing path of fetch() with a fake HTTP session (no network)."""
import types

from brandforge.scrape import fetch

PAGE = """<!doctype html><html><head>
<title>Acme - Bold Things</title>
<meta name="description" content="We make bold things for bold people.">
<meta property="og:image" content="/og.png">
<link rel="icon" href="/favicon.ico">
<link rel="apple-touch-icon" href="/touch.png">
<style>.hero{color:#ff5500}.btn{background:#1133aa}body{font-family:'Poppins',sans-serif}</style>
</head><body>
<img src="/assets/logo.svg" alt="Acme logo">
<img src="/cdn/shop/products/widget.jpg" class="product-card" alt="The Widget">
<img src="/img/insta-feed-1.jpg" class="instagram-feed" alt="social post">
<a href="https://instagram.com/acme">Instagram</a>
<a href="https://twitter.com/intent/tweet?url=x">Share</a>
<h1>Bold things for bold people</h1>
<p>We craft tools that punch above their weight.</p>
</body></html>"""


def _fake_session(html):
    def get(url, **kw):
        return types.SimpleNamespace(text=html, url=url, headers={}, content=b"")
    return types.SimpleNamespace(get=get)


def test_fetch_render_path_uses_playwright(monkeypatch):
    """render=True pulls HTML from the renderer, then parses it normally."""
    import brandforge.scrape as scrape_mod
    calls = {}

    def fake_render(url, **kw):
        calls["url"] = url
        return PAGE, "https://acme.com/rendered"

    monkeypatch.setattr(scrape_mod, "render_html_playwright", fake_render)
    r = fetch("https://acme.com", session=_fake_session(PAGE), render=True)
    assert calls["url"] == "https://acme.com"
    assert r.final_url == "https://acme.com/rendered"
    assert any("widget.jpg" in u for u in r.product_images)


def test_fetch_parses_brand_signals():
    r = fetch("https://acme.com", session=_fake_session(PAGE))
    assert r.title == "Acme - Bold Things"
    assert "bold things" in r.description.lower()
    assert "#ff5500" in r.colors and "#1133aa" in r.colors
    assert "Poppins" in r.fonts
    # logo.svg should rank ahead of favicon/og
    assert r.logo_candidates[0].endswith("logo.svg")
    assert r.domain == "acme.com"
    assert "punch above" in r.text_sample
    # content imagery is classified and the logo is excluded from it
    assert any("widget.jpg" in u for u in r.product_images)
    assert any("insta-feed-1.jpg" in u for u in r.social_images)
    assert all("logo.svg" not in u for u in r.product_images + r.social_images)
    # the brand's own social profile is captured; the share-intent link is not
    assert r.social_links.get("instagram") == "https://instagram.com/acme"
    assert "x" not in r.social_links
