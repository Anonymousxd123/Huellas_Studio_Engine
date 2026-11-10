from pathlib import Path

from PIL import Image, ImageFilter


def prepare_reference_image(source, destination, width, height, blur_radius=24):
    """Fit a full reference image to a target canvas without cropping or stretching."""
    if width <= 0 or height <= 0:
        raise ValueError("La resolución debe ser positiva")
    if blur_radius < 0:
        raise ValueError("El radio de desenfoque no puede ser negativo")

    source = Path(source).expanduser()
    destination = Path(destination).expanduser()
    if not source.is_file():
        raise FileNotFoundError(source)

    with Image.open(source) as original:
        image = original.convert("RGB")
        scale = min(width / image.width, height / image.height)
        resized = image.resize(
            (max(1, round(image.width * scale)),
             max(1, round(image.height * scale))),
            Image.Resampling.LANCZOS
        )

        background = image.resize(
            (width, height),
            Image.Resampling.LANCZOS
        )
        if blur_radius:
            background = background.filter(
                ImageFilter.GaussianBlur(radius=blur_radius)
            )

        x = (width - resized.width) // 2
        y = (height - resized.height) // 2
        background.paste(resized, (x, y))

        destination.parent.mkdir(parents=True, exist_ok=True)
        background.save(destination, format="PNG")

    return destination
