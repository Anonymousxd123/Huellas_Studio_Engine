from pathlib import Path

from PIL import Image, ImageFilter


ROOT = Path(__file__).resolve().parents[2]

DEFAULT_ASSETS = (
    Path.home() / "Huellas_Studio_Assets/characters/cutouts_v2"
)

# Posiciones relativas al lienzo.
# center_x y bottom van de 0.0 a 1.0.
SCENE_LAYOUTS = {
    "SC001": [
        {
            "asset": "cat_master_rgba.png",
            "center_x": 0.34,
            "bottom": 0.96,
            "height": 0.57,
            "shadow_opacity": 65,
        },
        {
            "asset": "dog_master_rgba.png",
            "center_x": 0.73,
            "bottom": 0.96,
            "height": 0.57,
            "shadow_opacity": 65,
        },
    ]
}


def load_character(path):
    image = Image.open(path).convert("RGBA")

    # Eliminar solamente márgenes totalmente transparentes.
    bbox = image.getchannel("A").getbbox()

    if bbox is None:
        raise ValueError(f"Personaje completamente transparente: {path}")

    return image.crop(bbox)


def resize_character(image, target_height):
    ratio = target_height / image.height

    target_width = max(1, round(image.width * ratio))

    return image.resize(
        (target_width, target_height),
        Image.Resampling.LANCZOS
    )


def make_shadow(character, opacity=65):
    alpha = character.getchannel("A")

    alpha = alpha.point(
        lambda value: int(value * opacity / 255)
    )

    alpha = alpha.filter(ImageFilter.GaussianBlur(12))

    shadow = Image.new(
        "RGBA",
        character.size,
        (35, 25, 20, 0)
    )

    shadow.putalpha(alpha)

    return shadow


def compose_scene(
    background_path,
    output_path,
    scene_id,
    assets_dir=DEFAULT_ASSETS,
    width=1280,
    height=720
):
    background_path = Path(background_path).expanduser()
    output_path = Path(output_path).expanduser()
    assets_dir = Path(assets_dir).expanduser()

    if not background_path.is_file():
        raise FileNotFoundError(background_path)

    if scene_id not in SCENE_LAYOUTS:
        raise ValueError(
            f"No existe distribución visual para {scene_id}"
        )

    background = Image.open(background_path).convert("RGB")

    canvas = background.resize(
        (width, height),
        Image.Resampling.LANCZOS
    ).convert("RGBA")

    for placement in SCENE_LAYOUTS[scene_id]:

        character_path = assets_dir / placement["asset"]

        if not character_path.is_file():
            raise FileNotFoundError(character_path)

        character = load_character(character_path)

        target_height = round(
            height * placement["height"]
        )

        character = resize_character(
            character,
            target_height
        )

        x = round(
            width * placement["center_x"]
            - character.width / 2
        )

        y = round(
            height * placement["bottom"]
            - character.height
        )

        if (
            x < 0 or y < 0
            or x + character.width > width
            or y + character.height > height
        ):
            raise ValueError(
                f"Personaje fuera del lienzo: {placement['asset']}"
            )

        shadow = make_shadow(
            character,
            placement.get("shadow_opacity", 65)
        )

        canvas.alpha_composite(
            shadow,
            (x, y + 10)
        )

        canvas.alpha_composite(
            character,
            (x, y)
        )

        print(
            f"[OK] {placement['asset']} "
            f"posición=({x},{y}) "
            f"tamaño={character.size}"
        )

    output_path.parent.mkdir(
        parents=True,
        exist_ok=True
    )

    canvas.convert("RGB").save(
        output_path,
        format="PNG",
        optimize=True
    )

    print("\nCOMPOSICIÓN COMPLETADA")
    print("Salida:", output_path)
    print("Resolución:", f"{width}x{height}")

    return output_path
