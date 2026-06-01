"""Synthesize a structured brand guide from scraped signals via Claude.

The output is a structured brand-guide schema: tagline/mission/summary,
target_audience + personas, selling points + emotional motivations,
primary/secondary/accent colors + palette, heading/body fonts,
voice_tone/voice_notes, casting_notes, and rules.
"""
from __future__ import annotations

import json
from typing import Any

from .config import Config
from .llm import complete
from .scrape import ScrapeResult

SYSTEM = (
    "You are a senior brand strategist who builds brand guides that drive AI ad "
    "creative. Given real signals scraped from a company's website, you infer a "
    "sharp, specific, usable brand guide - never generic filler. You return "
    "STRICT JSON only, no prose, no markdown fences."
)

# A standard brand-guide model: identity, audience/personas, messaging, visual, style.
SCHEMA_HINT = """{
  "brand_name": str,
  "tagline": str,
  "mission": str,
  "summary": str,
  "target_audience": str,
  "personas": [ { "name": str, "description": str } ],
  "selling_points": [str],
  "emotional_motivations": [str],
  "primary_color": "#rrggbb",
  "secondary_color": "#rrggbb",
  "accent_color": "#rrggbb",
  "color_palette": ["#rrggbb", ...],
  "font_heading": str,
  "font_body": str,
  "voice_tone": str,
  "voice_notes": str,
  "casting_notes": str,
  "rules": str
}"""


def build_prompt(scrape: ScrapeResult) -> str:
    return (
        f"WEBSITE: {scrape.final_url or scrape.url}\n"
        f"TITLE: {scrape.title}\n"
        f"META DESCRIPTION: {scrape.description}\n"
        f"DETECTED COLORS (hex, from the site's CSS/logo, ordered): "
        f"{', '.join(scrape.colors) or 'none'}\n"
        f"DETECTED FONTS: {', '.join(scrape.fonts) or 'none'}\n\n"
        f"VISIBLE COPY (voice + offer signal):\n{scrape.text_sample or '(none)'}\n\n"
        "Build the brand guide. Requirements:\n"
        "- Choose primary_color, secondary_color, accent_color FROM the detected "
        "colors (pick the most brand-defining ones); put the rest in color_palette.\n"
        "- Use the detected fonts for font_heading/font_body when present.\n"
        "- personas = 2-4 'creative personas' (the people who'd star in or watch the "
        "brand's ads): give each a name + a vivid 1-2 sentence description.\n"
        "- selling_points = concrete product/offer selling points.\n"
        "- emotional_motivations = the underlying emotional drivers to buy.\n"
        "- casting_notes = who to cast in UGC/video ads (age, look, energy, setting).\n"
        "- voice_tone = a short phrase; voice_notes = how to write for the brand.\n"
        "- rules = brand do/don't guardrails for generated creative.\n"
        f"Fill EVERY field of this exact JSON shape:\n{SCHEMA_HINT}\n\n"
        "Return only the JSON object."
    )


def _parse_json_object(raw: str) -> dict:
    start = raw.find("{")
    end = raw.rfind("}")
    if start == -1 or end == -1 or end < start:
        raise ValueError(f"No JSON object found in response: {raw!r}")
    return json.loads(raw[start : end + 1])


def _merge_detected(guide: dict, scrape: ScrapeResult, logo_palette: list[str]) -> dict:
    """Ground the guide in real detected colors/fonts; fill any gaps."""
    detected: list[str] = []
    seen = set()
    for hex_ in (logo_palette + scrape.colors):
        h = str(hex_).lower()
        if h.startswith("#") and h not in seen:
            seen.add(h)
            detected.append(h)

    # Fill primary/secondary/accent from detected colors if the model left them blank.
    for i, field in enumerate(("primary_color", "secondary_color", "accent_color")):
        if not guide.get(field) and i < len(detected):
            guide[field] = detected[i]

    # color_palette: ensure it's a list and includes detected colors not already used.
    palette = guide.get("color_palette") or []
    if isinstance(palette, str):
        palette = [c.strip() for c in palette.split(",") if c.strip()]
    used = {
        str(guide.get(f, "")).lower()
        for f in ("primary_color", "secondary_color", "accent_color")
    }
    for hex_ in detected:
        if hex_ not in {p.lower() for p in palette} and hex_ not in used:
            palette.append(hex_)
    guide["color_palette"] = palette[:8]

    # Fonts fallback.
    if not guide.get("font_heading") and scrape.fonts:
        guide["font_heading"] = scrape.fonts[0]
    if not guide.get("font_body") and scrape.fonts:
        guide["font_body"] = scrape.fonts[-1]

    guide["_detected"] = {
        "colors": scrape.colors,
        "logo_colors": logo_palette,
        "fonts": scrape.fonts,
        "source_url": scrape.final_url or scrape.url,
    }
    return guide


def synthesize(
    config: Config,
    scrape: ScrapeResult,
    *,
    logo_palette: list[str] | None = None,
    client: Any | None = None,
) -> dict:
    raw = complete(
        config,
        SYSTEM,
        build_prompt(scrape),
        client=client,
        max_tokens=2600,
        temperature=0.5,
    )
    guide = _parse_json_object(raw)
    return _merge_detected(guide, scrape, logo_palette or [])
