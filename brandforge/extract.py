"""Download the brand's real logo and (where possible) sample its palette."""
from __future__ import annotations

import os
from pathlib import Path
from urllib.parse import urlparse

from .scrape import USER_AGENT

_EXT_BY_CONTENT_TYPE = {
    "image/svg+xml": ".svg",
    "image/png": ".png",
    "image/jpeg": ".jpg",
    "image/webp": ".webp",
    "image/x-icon": ".ico",
    "image/vnd.microsoft.icon": ".ico",
    "image/gif": ".gif",
}


def _guess_ext(url: str, content_type: str) -> str:
    ct = (content_type or "").split(";")[0].strip().lower()
    if ct in _EXT_BY_CONTENT_TYPE:
        return _EXT_BY_CONTENT_TYPE[ct]
    suffix = Path(urlparse(url).path).suffix.lower()
    return suffix if suffix in {".svg", ".png", ".jpg", ".jpeg", ".webp", ".ico", ".gif"} else ".png"


def download_logo(
    candidates: list[str], dest_dir: str, *, session: object | None = None
) -> str | None:
    """Download the first candidate that fetches successfully. Returns path or None."""
    if not candidates:
        return None
    try:
        import requests
    except ImportError as exc:  # pragma: no cover
        raise RuntimeError("'requests' is required. Install: pip install requests") from exc
    http = session or requests

    os.makedirs(dest_dir, exist_ok=True)
    for url in candidates:
        try:
            resp = http.get(url, headers={"User-Agent": USER_AGENT}, timeout=12)
            content = resp.content
            if not content or len(content) < 64:  # skip empties / 1px trackers
                continue
            ext = _guess_ext(url, resp.headers.get("content-type", ""))
            path = os.path.join(dest_dir, "logo" + ext)
            with open(path, "wb") as fh:
                fh.write(content)
            return path
        except Exception:
            continue
    return None


def palette_from_image(path: str, *, count: int = 5) -> list[str]:
    """Sample dominant colors from a raster logo. SVG/unsupported -> []."""
    if path is None or path.lower().endswith(".svg"):
        return []
    try:
        from PIL import Image
    except ImportError:  # pragma: no cover
        return []
    try:
        img = Image.open(path).convert("RGBA")
    except Exception:
        return []

    # Composite onto white so transparent logos don't sample as black.
    from PIL import Image as _Image

    bg = _Image.new("RGBA", img.size, (255, 255, 255, 255))
    img = _Image.alpha_composite(bg, img).convert("RGB")
    img = img.resize((80, 80))
    quant = img.quantize(colors=8, method=2)
    palette = quant.getpalette()
    color_counts = sorted(quant.getcolors(), reverse=True)  # (count, index)

    hexes: list[str] = []
    for _, idx in color_counts:
        r, g, b = palette[idx * 3 : idx * 3 + 3]
        # Skip near-white (the composited background).
        if r > 240 and g > 240 and b > 240:
            continue
        hexes.append("#%02x%02x%02x" % (r, g, b))
        if len(hexes) >= count:
            break
    return hexes
