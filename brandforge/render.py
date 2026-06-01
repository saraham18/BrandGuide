"""Render a structured brand-guide dict into a polished, self-contained HTML page.

Sections: Mission, Audience, Messaging, Visual Elements, Style.
"""
from __future__ import annotations

import html
from typing import Any


def _esc(value: Any) -> str:
    return html.escape(str(value or ""))


def _ul(items: list, *, cls: str = "") -> str:
    items = [i for i in (items or []) if str(i).strip()]
    if not items:
        return '<p class="muted">-</p>'
    return f'<ul class="{cls}">' + "".join(f"<li>{_esc(i)}</li>" for i in items) + "</ul>"


def _personas(personas: list[dict]) -> str:
    cards = []
    for p in personas or []:
        if isinstance(p, dict):
            name, desc = p.get("name"), p.get("description")
        else:
            name, desc = "", p
        cards.append(
            f'<div class="card"><h4>{_esc(name)}</h4><p>{_esc(desc)}</p></div>'
        )
    return f'<div class="grid">{"".join(cards)}</div>' if cards else '<p class="muted">-</p>'


def _text_color(hex_: str) -> str:
    try:
        h = hex_.lstrip("#")
        r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
        return "#000" if (0.299 * r + 0.587 * g + 0.114 * b) > 150 else "#fff"
    except Exception:
        return "#000"


def _swatch(hex_: str, label: str) -> str:
    hex_ = _esc(hex_ or "#000000")
    return (
        f'<div class="swatch" style="background:{hex_};color:{_text_color(hex_)}">'
        f'<span class="sw-role">{_esc(label)}</span>'
        f'<span class="hex">{hex_}</span></div>'
    )


def _colors(g: dict) -> str:
    cells = []
    for role, field in (("Primary", "primary_color"), ("Secondary", "secondary_color"),
                        ("Accent", "accent_color")):
        if g.get(field):
            cells.append(_swatch(g[field], role))
    for hex_ in g.get("color_palette") or []:
        cells.append(_swatch(hex_, ""))
    return f'<div class="swatches">{"".join(cells)}</div>' if cells else '<p class="muted">-</p>'


def render_html(guide: dict, *, logo_rel: str | None = None) -> str:
    g = guide
    logo_img = (
        f'<img class="logo" src="{_esc(logo_rel)}" alt="logo">' if logo_rel else ""
    )
    source = (g.get("_detected") or {}).get("source_url")

    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{_esc(g.get('brand_name'))} - Brand Guide</title>
<style>
  :root {{ --ink:#16181d; --muted:#6b7280; --line:#e7e8ec; --bg:#fbfbfc; }}
  * {{ box-sizing:border-box; }}
  body {{ margin:0; font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,
         Helvetica,Arial,sans-serif; color:var(--ink); background:var(--bg); line-height:1.5; }}
  .wrap {{ max-width:880px; margin:0 auto; padding:56px 28px 96px; }}
  header {{ display:flex; align-items:center; gap:20px; border-bottom:1px solid var(--line);
           padding-bottom:28px; margin-bottom:8px; }}
  .logo {{ width:88px; height:88px; object-fit:contain; border-radius:14px; background:#fff;
          border:1px solid var(--line); padding:8px; }}
  h1 {{ font-size:34px; margin:0 0 4px; letter-spacing:-0.02em; }}
  .tagline {{ color:var(--muted); font-size:18px; margin:0; }}
  .section {{ margin:40px 0; }}
  .label {{ font-size:12px; text-transform:uppercase; letter-spacing:0.1em; color:#9aa1ab;
           border-bottom:1px solid var(--line); padding-bottom:8px; margin:0 0 18px; }}
  h3 {{ font-size:14px; text-transform:uppercase; letter-spacing:0.06em; color:var(--muted);
        margin:0 0 10px; }}
  h4 {{ margin:0 0 6px; font-size:16px; }}
  p {{ margin:0 0 12px; }}
  .lead {{ font-size:18px; }}
  .muted {{ color:var(--muted); }}
  ul {{ margin:0 0 12px; padding-left:20px; }} li {{ margin:5px 0; }}
  .two {{ display:grid; grid-template-columns:1fr 1fr; gap:28px; }}
  .grid {{ display:grid; grid-template-columns:1fr 1fr; gap:14px; }}
  .card {{ border:1px solid var(--line); border-radius:12px; padding:14px 16px; background:#fff; }}
  .swatches {{ display:flex; flex-wrap:wrap; gap:12px; }}
  .swatch {{ width:120px; height:92px; border-radius:12px; padding:10px; display:flex;
            flex-direction:column; justify-content:space-between; border:1px solid rgba(0,0,0,0.06);
            font-size:12px; }}
  .swatch .hex {{ font-family:ui-monospace,Menlo,monospace; font-weight:600; }}
  .sw-role {{ font-weight:600; }}
  .do {{ color:#137a3f; }} .dont {{ color:#b42318; }}
  .mono {{ font-family:ui-monospace,Menlo,monospace; }}
  footer {{ margin-top:52px; color:var(--muted); font-size:13px; border-top:1px solid var(--line);
           padding-top:18px; }}
  @media (max-width:640px) {{ .two,.grid {{ grid-template-columns:1fr; }} }}
</style></head>
<body><div class="wrap">
  <header>{logo_img}<div>
    <h1>{_esc(g.get('brand_name'))}</h1>
    <p class="tagline">{_esc(g.get('tagline'))}</p>
  </div></header>

  <div class="section"><p class="label">Mission</p>
    <p class="lead">{_esc(g.get('mission'))}</p>
    <p>{_esc(g.get('summary'))}</p>
  </div>

  <div class="section"><p class="label">Audience</p>
    <h3>Target Audience</h3><p>{_esc(g.get('target_audience'))}</p>
    <h3>Creative Personas</h3>{_personas(g.get('personas', []))}
  </div>

  <div class="section"><p class="label">Messaging</p>
    <div class="two">
      <div><h3>Product Selling Points</h3>{_ul(g.get('selling_points', []))}</div>
      <div><h3>Emotional Motivations</h3>{_ul(g.get('emotional_motivations', []))}</div>
    </div>
  </div>

  <div class="section"><p class="label">Visual Elements</p>
    <h3>Brand Colors</h3>{_colors(g)}
    <h3 style="margin-top:22px">Typography</h3>
    <p><strong>Heading:</strong> <span class="mono">{_esc(g.get('font_heading'))}</span></p>
    <p><strong>Body:</strong> <span class="mono">{_esc(g.get('font_body'))}</span></p>
  </div>

  <div class="section"><p class="label">Style</p>
    <div class="two">
      <div><h3>Voice &amp; Tone</h3>
        <p><strong>{_esc(g.get('voice_tone'))}</strong></p>
        <p>{_esc(g.get('voice_notes'))}</p>
      </div>
      <div><h3>Casting Notes</h3><p>{_esc(g.get('casting_notes'))}</p></div>
    </div>
    <h3 style="margin-top:8px">Rules</h3><p>{_esc(g.get('rules'))}</p>
  </div>

  <footer>Generated by BrandForge from {_esc(source)}</footer>
</div></body></html>"""
