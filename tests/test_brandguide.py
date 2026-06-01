import json
import types

from brandguide.config import Config
from brandguide.scrape import ScrapeResult
from brandguide.brandguide import synthesize, sanitize, _merge_detected, build_prompt
from brandguide.render import render_html


def test_sanitize_strips_emojis_and_em_dashes():
    out = sanitize({"voice_tone": "Bold \U0001f525 - punchy — fast", "list": ["a — b"]})
    assert out["voice_tone"] == "Bold  - punchy - fast"
    assert out["list"] == ["a - b"]


class FakeBlock:
    def __init__(self, text): self.text = text


class FakeMessage:
    def __init__(self, text): self.content = [FakeBlock(text)]


class FakeAnthropic:
    def __init__(self, text):
        self._text = text
        self.messages = types.SimpleNamespace(create=lambda **k: FakeMessage(self._text))


def _scrape():
    return ScrapeResult(
        url="https://acme.com", final_url="https://acme.com",
        title="Acme", description="We make things",
        colors=["#ff5500", "#1133aa"], fonts=["Poppins", "Inter"],
        text_sample="Bold things for bold people.",
    )


def test_build_prompt_includes_detected_signals():
    p = build_prompt(_scrape())
    assert "#ff5500" in p and "Poppins" in p and "acme.com" in p


def test_merge_fills_colors_and_fonts_from_detected():
    guide = {"brand_name": "Acme"}  # model returned no colors/fonts
    merged = _merge_detected(guide, _scrape(), logo_palette=["#00cc88"])
    assert merged["primary_color"] == "#00cc88"   # logo color wins primary
    assert merged["secondary_color"] == "#ff5500"
    assert merged["font_heading"] == "Poppins"
    assert merged["_detected"]["source_url"] == "https://acme.com"


def test_synthesize_parses_model_json():
    payload = json.dumps({
        "brand_name": "Acme", "tagline": "Bold things",
        "primary_color": "#ff5500", "personas": [{"name": "Bo", "description": "bold"}],
        "selling_points": ["fast"], "emotional_motivations": ["pride"],
    })
    cfg = Config(env={"ANTHROPIC_API_KEY": "k"})
    guide = synthesize(cfg, _scrape(), client=FakeAnthropic(payload))
    assert guide["brand_name"] == "Acme"
    assert guide["personas"][0]["name"] == "Bo"
    # detected colors ground the guide: model gave only primary, so the next
    # detected color is promoted to secondary (leftovers would go to the palette).
    assert guide["primary_color"] == "#ff5500"
    assert guide["secondary_color"] == "#1133aa"


def test_render_html_is_self_contained_and_has_sections():
    guide = {
        "brand_name": "Acme", "tagline": "Bold", "mission": "make bold",
        "target_audience": "founders", "personas": [{"name": "Bo", "description": "x"}],
        "selling_points": ["fast"], "emotional_motivations": ["pride"],
        "primary_color": "#ff5500", "color_palette": ["#1133aa"],
        "font_heading": "Poppins", "font_body": "Inter",
        "voice_tone": "punchy", "casting_notes": "young", "rules": "no fluff",
        "_detected": {"source_url": "https://acme.com"},
    }
    guide["assets"] = [
        {"kind": "product_photo", "label": "Product photo", "file_path": "assets/product_photo-1.jpg"},
        {"kind": "social_reference", "label": "Social reference", "file_path": "assets/social_reference-1.jpg"},
    ]
    guide["social_links"] = {"instagram": "https://instagram.com/acme"}
    out = render_html(guide, logo_rel="logo.png")
    assert out.startswith("<!doctype html>")
    for section in ("Mission", "Audience", "Messaging", "Visual Elements", "Style", "Social"):
        assert section in out
    assert "#ff5500" in out and "logo.png" in out
    # galleries and social links render
    assert "assets/product_photo-1.jpg" in out
    assert "Social Reference Photos" in out
    assert "https://instagram.com/acme" in out
