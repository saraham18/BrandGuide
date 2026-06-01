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
<h1>Bold things for bold people</h1>
<p>We craft tools that punch above their weight.</p>
</body></html>"""


def _fake_session(html):
    def get(url, **kw):
        return types.SimpleNamespace(text=html, url=url, headers={}, content=b"")
    return types.SimpleNamespace(get=get)


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
