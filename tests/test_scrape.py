from brandforge.scrape import (
    extract_colors,
    extract_fonts,
    rank_logo_candidates,
    classify_image,
    _norm_hex,
    _is_greyish,
)


def test_norm_hex_expands_shorthand():
    assert _norm_hex("#ABC") == "#aabbcc"
    assert _norm_hex("#11AA33") == "#11aa33"


def test_extract_colors_prioritizes_brand_over_grey_and_drops_bw():
    css = "a{color:#ff5500}b{color:#ff5500}c{color:#808080}d{color:#000}e{color:#fff}"
    colors = extract_colors(css)
    assert colors[0] == "#ff5500"          # most frequent brand color first
    assert "#000000" not in colors and "#ffffff" not in colors
    assert _is_greyish("#808080")


def test_extract_colors_handles_rgb():
    assert "#ff5500" in extract_colors("x{color:rgb(255, 85, 0)}")


def test_extract_fonts_skips_generics_and_dedupes():
    css = "h1{font-family:'Poppins', sans-serif}p{font-family:Poppins, Arial}"
    fonts = extract_fonts(css)
    assert fonts[0] == "Poppins"
    assert fonts.count("Poppins") == 1
    assert "sans-serif" not in fonts


def test_rank_logo_candidates_prefers_logo_assets():
    cands = [
        "https://x.com/favicon.ico",
        "https://x.com/assets/logo.svg",
        "https://x.com/apple-touch-icon.png",
    ]
    ranked = rank_logo_candidates(cands)
    assert "logo.svg" in ranked[0]
    assert ranked[-1].endswith("favicon.ico")


def test_classify_image_buckets_and_skips():
    assert classify_image("/cdn/shop/products/tee.jpg product-card") == "product"
    assert classify_image("instagram feed ugc photo") == "social"
    assert classify_image("homepage hero banner") == "lifestyle"
    assert classify_image("site-logo.svg") is None      # logos/icons skipped
    assert classify_image("random decorative blob") is None  # no signal -> skip
