import argparse
from pathlib import Path

from PIL import Image


DEFAULT_ROOT = Path.home() / "Huellas_Studio_Assets"


def build_character_assets(root=DEFAULT_ROOT, model="isnet-anime"):
    try:
        from rembg import new_session, remove
    except ImportError as error:
        raise RuntimeError(
            "Falta rembg. Instala las dependencias con: "
            "pip install -e '.[background-removal]'"
        ) from error

    root = Path(root).expanduser()
    sources = {
        "dog": root / "characters/dog/Dog_Master_v1.png",
        "cat": root / "characters/cat/Cat_Master_v1.png",
    }
    output = root / "characters/cutouts_v2"
    output.mkdir(parents=True, exist_ok=True)

    print("\nHUELLAS STUDIO - CHARACTER ASSETS")
    print("=" * 45)

    session = None
    completed = []
    for name, source in sources.items():
        if not source.is_file():
            raise FileNotFoundError(source)

        print(f"\nProcesando: {name}")
        with Image.open(source) as original:
            original = original.convert("RGBA")
            if original.getchannel("A").getextrema() == (255, 255):
                if session is None:
                    print("Cargando modelo de segmentación...")
                    session = new_session(model)
                print("Eliminando fondo...")
                result = remove(original, session=session).convert("RGBA")
            else:
                print("Conservando transparencia existente...")
                result = original.copy()

        bbox = result.getchannel("A").point(
            lambda value: 255 if value > 8 else 0
        ).getbbox()
        if bbox is None:
            raise RuntimeError(f"No se detectó {name}")

        x1, y1, x2, y2 = bbox
        margin = 24
        bbox = (
            max(0, x1 - margin),
            max(0, y1 - margin),
            min(result.width, x2 + margin),
            min(result.height, y2 + margin)
        )
        result = result.crop(bbox)

        destination = output / f"{name}_master_rgba.png"
        result.save(destination)
        completed.append(destination)
        print("Dimensiones:", result.size)
        print("Alpha:", result.getchannel("A").getextrema())
        print("[OK]", destination)

    print("\nEXTRACCIÓN COMPLETADA")
    print("Salida:", output)
    return completed


def main():
    parser = argparse.ArgumentParser(
        description="Remove backgrounds from the dog and cat master assets"
    )
    parser.add_argument("--assets-root", default=str(DEFAULT_ROOT))
    parser.add_argument("--model", default="isnet-anime")
    args = parser.parse_args()
    build_character_assets(args.assets_root, args.model)


if __name__ == "__main__":
    main()
