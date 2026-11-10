import argparse
from pathlib import Path

import numpy as np
from PIL import Image


DEFAULT_SOURCE = (
    Path.home()
    / "Huellas_Studio_Assets/characters/duo/Duo_Master_v1.png"
)


def extract_duo_cutouts(source, output_dir, model="u2net"):
    try:
        from rembg import new_session, remove
    except ImportError as error:
        raise RuntimeError(
            "Falta rembg. Instala las dependencias con: "
            "pip install -e '.[background-removal]'"
        ) from error

    source = Path(source).expanduser()
    output = Path(output_dir).expanduser()
    if not source.is_file():
        raise FileNotFoundError(source)
    output.mkdir(parents=True, exist_ok=True)

    print("Cargando modelo de segmentación...")
    session = new_session(model)
    with Image.open(source) as original:
        result = remove(
            original.convert("RGBA"),
            session=session
        ).convert("RGBA")

    result.save(output / "duo_master_rgba.png")
    alpha = np.asarray(result.getchannel("A"))
    occupancy = (alpha > 32).sum(axis=0)
    width, height = result.size

    start = int(width * 0.40)
    end = int(width * 0.75)
    if end <= start:
        raise ValueError("La imagen es demasiado estrecha para separar personajes")

    split = start + int(np.argmin(occupancy[start:end]))
    print("Resolución:", width, height)
    print("Separación detectada:", split)

    outputs = []
    for name, bounds in (
        ("dog_master_rgba", (0, 0, split, height)),
        ("cat_master_rgba", (split, 0, width, height))
    ):
        crop = result.crop(bounds)
        bbox = crop.getchannel("A").point(
            lambda value: 255 if value > 8 else 0
        ).getbbox()
        if bbox is None:
            raise RuntimeError(f"No se detectó el personaje {name}")
        crop = crop.crop(bbox)
        destination = output / f"{name}.png"
        crop.save(destination)
        outputs.append(destination)
        print(f"[OK] {name}: {crop.width}x{crop.height}")

    print("\nEXTRACCIÓN COMPLETADA")
    print("Directorio:", output)
    return outputs


def main():
    parser = argparse.ArgumentParser(
        description="Split the duo master image into dog and cat cutouts"
    )
    parser.add_argument("--source", default=str(DEFAULT_SOURCE))
    parser.add_argument(
        "--output-dir",
        default=str(Path.home() / "Huellas_Studio_Assets/characters/cutouts_v2")
    )
    parser.add_argument("--model", default="u2net")
    args = parser.parse_args()
    extract_duo_cutouts(args.source, args.output_dir, args.model)


if __name__ == "__main__":
    main()
