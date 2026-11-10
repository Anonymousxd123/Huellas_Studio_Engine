from pathlib import Path
from PIL import Image
from rembg import remove, new_session

ROOT = Path.home() / "Huellas_Studio_Assets"

SOURCES = {
    "dog": ROOT / "characters/dog/dog_master_v1.png",
    "cat": ROOT / "characters/cat/Cat_Master_v1.png",
}

OUTPUT = ROOT / "characters/cutouts_v2"
OUTPUT.mkdir(parents=True, exist_ok=True)

print("\nHUELLAS STUDIO - CHARACTER ASSETS")
print("=" * 45)

session = new_session("isnet-anime")

for name, source in SOURCES.items():

    if not source.is_file():
        raise FileNotFoundError(source)

    print(f"\nProcesando: {name}")

    with Image.open(source) as original:
        original = original.convert("RGBA")

        alpha = original.getchannel("A")

        if alpha.getextrema() == (255, 255):
            print("Eliminando fondo...")
            result = remove(
                original,
                session=session
            ).convert("RGBA")
        else:
            print("Conservando transparencia existente...")
            result = original.copy()

    alpha = result.getchannel("A")
    bbox = alpha.point(
        lambda p: 255 if p > 8 else 0
    ).getbbox()

    if bbox is None:
        raise RuntimeError(f"No se detectó {name}")

    # Recorte con margen de seguridad.
    x1, y1, x2, y2 = bbox
    margin = 24

    bbox = (
        max(0, x1 - margin),
        max(0, y1 - margin),
        min(result.width, x2 + margin),
        min(result.height, y2 + margin)
    )

    result = result.crop(bbox)

    destination = OUTPUT / f"{name}_master_rgba.png"
    result.save(destination)

    print("Dimensiones:", result.size)
    print("Alpha:", result.getchannel("A").getextrema())
    print("[OK]", destination)

print("\nEXTRACCIÓN COMPLETADA")
print("Salida:", OUTPUT)
