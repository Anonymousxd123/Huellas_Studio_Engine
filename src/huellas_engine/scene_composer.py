from pathlib import Path

from PIL import Image, ImageFilter


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_ASSETS = Path.home() / "Huellas_Studio_Assets/characters/cutouts_v2"
ALPHA_BBOX_THRESHOLD = 8
DOG = "dog_master_rgba.png"
CAT = "cat_master_rgba.png"

# Static character placements. Character motion belongs to the animation stage.
SCENE_LAYOUTS = {
    "SC001": [
        {"asset": DOG, "center_x": 0.34, "bottom": 0.96, "height": 0.57, "shadow_opacity": 65},
        {"asset": CAT, "center_x": 0.73, "bottom": 0.96, "height": 0.57, "shadow_opacity": 65},
    ],
    "SC002": [
        {"asset": CAT, "center_x": 0.34, "bottom": 0.96, "height": 0.54, "shadow_opacity": 65},
        {"asset": DOG, "center_x": 0.74, "bottom": 0.96, "height": 0.56, "shadow_opacity": 65},
    ],
    "SC003": [
        {"asset": DOG, "center_x": 0.36, "bottom": 0.96, "height": 0.61, "shadow_opacity": 65},
        {"asset": CAT, "center_x": 0.73, "bottom": 0.96, "height": 0.49, "shadow_opacity": 65},
    ],
    "SC004": [
        {"asset": DOG, "center_x": 0.29, "bottom": 0.96, "height": 0.52, "shadow_opacity": 65},
        {"asset": CAT, "center_x": 0.70, "bottom": 0.96, "height": 0.56, "shadow_opacity": 65},
    ],
    "SC005": [
        {"asset": DOG, "center_x": 0.36, "bottom": 0.96, "height": 0.62, "shadow_opacity": 65},
        {"asset": CAT, "center_x": 0.76, "bottom": 0.96, "height": 0.47, "shadow_opacity": 65},
    ],
    "SC006": [
        {"asset": CAT, "center_x": 0.35, "bottom": 0.96, "height": 0.55, "shadow_opacity": 65},
        {"asset": DOG, "center_x": 0.75, "bottom": 0.96, "height": 0.52, "shadow_opacity": 65},
    ],
    "SC007": [
        {"asset": CAT, "center_x": 0.35, "bottom": 0.96, "height": 0.55, "shadow_opacity": 65},
        {"asset": DOG, "center_x": 0.74, "bottom": 0.96, "height": 0.54, "shadow_opacity": 65},
    ],
    "SC008": [
        {"asset": DOG, "center_x": 0.35, "bottom": 0.96, "height": 0.59, "shadow_opacity": 65},
        {"asset": CAT, "center_x": 0.69, "bottom": 0.96, "height": 0.56, "shadow_opacity": 65},
    ],
}


def load_character(path, alpha_threshold=ALPHA_BBOX_THRESHOLD):
    image = Image.open(path).convert("RGBA")
    alpha = image.getchannel("A")
    bbox = alpha.point(
        lambda value: 255 if value > alpha_threshold else 0
    ).getbbox()
    if bbox is None:
        raise ValueError(f"Personaje completamente transparente: {path}")

    image = image.crop(bbox)
    cropped_alpha = image.getchannel("A").point(
        lambda value: 0 if value <= alpha_threshold else value
    )
    image.putalpha(cropped_alpha)
    return image


def resize_character(image, target_height):
    if target_height <= 0:
        raise ValueError("La altura del personaje debe ser positiva")
    ratio = target_height / image.height
    target_width = max(1, round(image.width * ratio))
    return image.resize(
        (target_width, target_height),
        Image.Resampling.LANCZOS
    )


def make_shadow(character, opacity=65):
    if not 0 <= opacity <= 100:
        raise ValueError("La opacidad de sombra debe estar entre 0 y 100")
    alpha = character.getchannel("A").point(
        lambda value: round(value * opacity / 100)
    )
    alpha = alpha.filter(ImageFilter.GaussianBlur(12))
    shadow = Image.new("RGBA", character.size, (35, 25, 20, 0))
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

    if width <= 0 or height <= 0:
        raise ValueError("La resolución debe ser positiva")
    if not background_path.is_file():
        raise FileNotFoundError(background_path)
    if scene_id not in SCENE_LAYOUTS:
        raise ValueError(f"No existe distribución visual para {scene_id}")

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
        target_height = round(height * placement["height"])
        character = resize_character(character, target_height)
        x = round(width * placement["center_x"] - character.width / 2)
        y = round(height * placement["bottom"] - character.height)

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
        canvas.alpha_composite(shadow, (x, y + 10))
        canvas.alpha_composite(character, (x, y))
        print(
            f"[OK] {placement['asset']} "
            f"posición=({x},{y}) tamaño={character.size}"
        )

    output_path.parent.mkdir(parents=True, exist_ok=True)
    canvas.convert("RGB").save(output_path, format="PNG", optimize=True)
    print("\nCOMPOSICIÓN COMPLETADA")
    print("Salida:", output_path)
    print("Resolución:", f"{width}x{height}")
    return output_path
