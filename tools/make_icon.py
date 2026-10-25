"""Génère l'icône Windows (assets/ziggy.ico) et les logos de l'interface à partir de assets/lotus_source.png.
Le fond blanc est converti en transparence (dé-mélange du blanc, sans halo)."""
import sys
from pathlib import Path
from PIL import Image
import numpy as np

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "assets" / "lotus_source.png"


def to_transparent(img: Image.Image) -> Image.Image:
    a = np.asarray(img.convert("RGB")).astype(np.float32)
    # Le motif est bleu nuit (canal rouge très bas) sur fond blanc : alpha = distance au blanc
    alpha = np.clip((255.0 - a[..., 0]) / (255.0 - 14.0), 0.0, 1.0)
    alpha = np.where(alpha < 0.03, 0.0, alpha)
    safe = np.maximum(alpha, 1e-3)[..., None]
    rgb = np.clip((a - (1.0 - alpha[..., None]) * 255.0) / safe, 0, 255)
    out = np.dstack([rgb, alpha * 255.0]).astype(np.uint8)
    return Image.fromarray(out, "RGBA")


def crop_square(img: Image.Image, pad: float = 0.08) -> Image.Image:
    bbox = img.getchannel("A").point(lambda v: 255 if v > 8 else 0).getbbox()
    img = img.crop(bbox)
    side = int(max(img.size) * (1 + 2 * pad))
    canvas = Image.new("RGBA", (side, side), (0, 0, 0, 0))
    canvas.paste(img, ((side - img.width) // 2, (side - img.height) // 2), img)
    return canvas


def tint(img: Image.Image, rgb) -> Image.Image:
    r, g, b, a = img.split()
    return Image.merge("RGBA", (Image.new("L", img.size, rgb[0]), Image.new("L", img.size, rgb[1]),
                                Image.new("L", img.size, rgb[2]), a))


def main():
    base = crop_square(to_transparent(Image.open(SRC)))
    big = base.resize((512, 512), Image.LANCZOS)
    out = ROOT / "assets"
    big.save(out / "ziggy.png")
    tint(big, (130, 170, 255)).save(out / "ziggy_light.png")        # variante lisible sur fond sombre
    # Icône de fenêtre/raccourci : lotus sur pastille claire pour rester lisible sur tous les fonds
    sizes = [16, 24, 32, 48, 64, 128, 256]
    plate = Image.new("RGBA", (512, 512), (0, 0, 0, 0))
    from PIL import ImageDraw
    ImageDraw.Draw(plate).rounded_rectangle((0, 0, 511, 511), radius=112, fill=(244, 239, 227, 255))
    logo = big.resize((400, 400), Image.LANCZOS)
    plate.paste(logo, (56, 62), logo)
    plate.save(out / "ziggy_icon.png")
    plate.save(out / "ziggy.ico", format="ICO", sizes=[(s, s) for s in sizes])
    # Interface web
    web = ROOT / "static"
    big.resize((256, 256), Image.LANCZOS).save(web / "logo.png")
    tint(big, (130, 170, 255)).resize((256, 256), Image.LANCZOS).save(web / "logo-light.png")
    plate.resize((64, 64), Image.LANCZOS).save(web / "favicon.ico", format="ICO", sizes=[(32, 32), (64, 64)])
    print("OK :", ", ".join(p.name for p in sorted(out.glob("ziggy*"))))


if __name__ == "__main__":
    sys.exit(main())
