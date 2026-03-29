"""生成 assets/icon.png 与 assets/icon.ico（默认蓝色圆角底 + 「DT」字标）。发布前可替换为自有品牌图。"""
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "assets" / "icon.png"
OUT_ICO = ROOT / "assets" / "icon.ico"


def main():
    OUT.parent.mkdir(parents=True, exist_ok=True)
    size = 256
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    pad = 16
    draw.rounded_rectangle(
        [pad, pad, size - pad, size - pad],
        radius=48,
        fill=(51, 112, 255, 255),
    )
    try:
        font = ImageFont.truetype("segoeui.ttf", 100)
    except Exception:
        try:
            font = ImageFont.truetype("arial.ttf", 100)
        except Exception:
            font = ImageFont.load_default()
    text = "DT"
    bbox = draw.textbbox((0, 0), text, font=font)
    tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
    draw.text(
        ((size - tw) / 2 - bbox[0], (size - th) / 2 - bbox[1] - 6),
        text,
        fill=(255, 255, 255, 255),
        font=font,
    )
    img.save(OUT, "PNG")
    print("wrote", OUT)
    sizes = [(16, 16), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)]
    ico_parts = [img.resize(sz, Image.Resampling.LANCZOS) for sz in sizes]
    ico_parts[0].save(
        OUT_ICO,
        format="ICO",
        sizes=[im.size for im in ico_parts],
        append_images=ico_parts[1:],
    )
    print("wrote", OUT_ICO)


if __name__ == "__main__":
    main()
