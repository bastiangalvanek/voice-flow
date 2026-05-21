"""Generate voice-flow.ico for Windows shortcuts.

Logic:
- If logo.png is in the voice-flow/ directory → used as icon source
- Otherwise → falls back to a drawn microphone icon

Re-run after changing the logo: `python make_icon.py`
"""
from pathlib import Path

from PIL import Image, ImageDraw

HERE = Path(__file__).parent
LOGO_PNG = HERE / "logo.png"
OUT = HERE / "voice-flow.ico"
ICO_SIZES = [(16, 16), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)]


def make_microphone_fallback(size: int = 256) -> Image.Image:
    """Red microphone icon as fallback when logo.png is missing."""
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    pad = size // 12
    draw.ellipse((pad, pad, size - pad, size - pad), fill=(220, 50, 50))

    mic_w = size // 3
    mic_h = size // 2 + size // 16
    cx = size // 2
    cy = size // 2 - size // 16
    draw.rounded_rectangle(
        (cx - mic_w // 2, cy - mic_h // 2, cx + mic_w // 2, cy + mic_h // 2),
        radius=mic_w // 2,
        fill=(255, 255, 255),
    )
    arc_w = mic_w * 2
    arc_top = cy + mic_h // 4
    arc_bot = arc_top + arc_w
    draw.arc(
        (cx - arc_w // 2, arc_top, cx + arc_w // 2, arc_bot),
        start=0, end=180, fill=(255, 255, 255), width=max(2, size // 28),
    )
    return img


def _square_pad(img: Image.Image) -> Image.Image:
    """Pad non-square image to square with transparent border."""
    w, h = img.size
    if w == h:
        return img
    side = max(w, h)
    out = Image.new("RGBA", (side, side), (0, 0, 0, 0))
    out.paste(img, ((side - w) // 2, (side - h) // 2))
    return out


def load_logo_or_fallback() -> tuple[Image.Image, str]:
    if LOGO_PNG.exists():
        img = Image.open(LOGO_PNG).convert("RGBA")
        img = _square_pad(img)
        img.thumbnail((256, 256), Image.LANCZOS)
        if img.size != (256, 256):
            base = Image.new("RGBA", (256, 256), (0, 0, 0, 0))
            base.paste(
                img,
                ((256 - img.size[0]) // 2, (256 - img.size[1]) // 2),
            )
            img = base
        return img, f"logo.png ({LOGO_PNG})"
    return make_microphone_fallback(256), "microphone fallback (no logo.png)"


def main() -> None:
    img, source = load_logo_or_fallback()
    img.save(OUT, format="ICO", sizes=ICO_SIZES)
    print(f"Source:  {source}")
    print(f"Output:  {OUT}  ({len(ICO_SIZES)} sizes)")


if __name__ == "__main__":
    main()
