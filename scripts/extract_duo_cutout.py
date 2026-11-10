import argparse
from pathlib import Path

import numpy as np
from PIL import Image
from rembg import remove, new_session

parser = argparse.ArgumentParser()
parser.add_argument(
    "--source",
    default="/Users/christianblasacosta/Huellas_Studio_Assets/characters/duo/Duo_Master_v1.png"
)
args = parser.parse_args()

source = Path(args.source).expanduser()

if not source.is_file():
    raise FileNotFoundError(source)

output = source.parent.parent / "cutouts"
output.mkdir(parents=True, exist_ok=True)

print("Cargando modelo de segmentación...")

session = new_session("u2net")

with Image.open(source) as original:
    original = original.convert("RGBA")
    result = remove(original, session=session).convert("RGBA")

result.save(output / "duo_master_rgba.png")

alpha = np.asarray(result.getchannel("A"))
occupancy = (alpha > 32).sum(axis=0)

width, height = result.size

# Buscar el espacio entre ambos personajes.
start = int(width * 0.48)
end = int(width * 0.70)

split = start + int(np.argmin(occupancy[start:end]))

print("Resolución:", width, height)
print("Separación detectada:", split)

def save_character(name, bounds):
    crop = result.crop(bounds)

    bbox = crop.getchannel("A").getbbox()

    if bbox is None:
        raise RuntimeError(f"No se detectó el personaje {name}")

    crop = crop.crop(bbox)
    crop.save(output / f"{name}_cutout.png")

    print(
        f"[OK] {name}: "
        f"{crop.width}x{crop.height}"
    )

save_character("dog", (0, 0, split, height))
save_character("cat", (split, 0, width, height))

print("\nEXTRACCIÓN COMPLETADA")
print("Directorio:", output)
