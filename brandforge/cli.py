"""BrandForge CLI: turn a website URL into a brand guide (JSON + HTML)."""
from __future__ import annotations

import argparse
import json
import os
import re
import sys

from .config import Config, MissingCredential
from .brandguide import synthesize
from .extract import download_logo, palette_from_image
from .render import render_html
from .scrape import fetch


def _slug(domain: str, fallback: str = "brand") -> str:
    s = re.sub(r"^www\.", "", domain.lower())
    s = re.sub(r"[^a-z0-9]+", "-", s).strip("-")
    return s or fallback


def cmd_generate(args, config: Config) -> int:
    config.require_llm()

    print(f"-> Scraping {args.url} ...")
    scrape = fetch(args.url)
    print(f"  title: {scrape.title or '(none)'}")
    print(f"  colors: {', '.join(scrape.colors) or '(none)'}")
    print(f"  fonts: {', '.join(scrape.fonts) or '(none)'}")
    print(f"  logo candidates: {len(scrape.logo_candidates)}")

    slug = args.name or _slug(scrape.domain)
    out_dir = os.path.join(args.out, slug)
    os.makedirs(out_dir, exist_ok=True)

    logo_path = download_logo(scrape.logo_candidates, out_dir)
    logo_rel = os.path.basename(logo_path) if logo_path else None
    logo_palette = palette_from_image(logo_path) if logo_path else []
    print(f"  logo: {logo_rel or 'not found'}; logo colors: {', '.join(logo_palette) or '-'}")

    print("-> Synthesizing brand guide with Claude ...")
    guide = synthesize(config, scrape, logo_palette=logo_palette)
    guide["logo_path"] = logo_rel  # downloaded brand logo

    json_path = os.path.join(out_dir, "brand-guide.json")
    html_path = os.path.join(out_dir, "brand-guide.html")
    with open(json_path, "w") as fh:
        json.dump(guide, fh, indent=2)
    with open(html_path, "w") as fh:
        fh.write(render_html(guide, logo_rel=logo_rel))

    print(f"\n{guide.get('brand_name', slug)} - brand guide ready")
    print(f"   {json_path}")
    print(f"   {html_path}")
    if logo_rel:
        print(f"   {os.path.join(out_dir, logo_rel)}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="brandforge", description="BrandForge")
    parser.add_argument("--env", default=".env", help="Path to .env (default: .env)")
    sub = parser.add_subparsers(dest="command", required=True)

    g = sub.add_parser("generate", help="Generate a brand guide from a website URL")
    g.add_argument("--url", required=True, help="Website URL to analyze")
    g.add_argument("--name", help="Project slug (default: derived from domain)")
    g.add_argument("--out", default="projects", help="Output root (default: projects/)")
    g.set_defaults(func=cmd_generate)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    config = Config.load(args.env)
    try:
        return args.func(args, config)
    except MissingCredential as exc:
        print(f" {exc}", file=sys.stderr)
        return 1
    except Exception as exc:
        print(f"{type(exc).__name__}: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
