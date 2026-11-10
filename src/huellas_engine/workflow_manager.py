import copy
from pathlib import Path
import json


def load_workflow(path):
    path = Path(path).expanduser()

    with path.open("r", encoding="utf-8") as file:
        workflow = json.load(file)

    if not isinstance(workflow, dict):
        raise ValueError("El workflow no tiene formato API válido")

    return workflow


def node_by_title(workflow, title):
    matches = [
        node for node in workflow.values()
        if node.get("_meta", {}).get("title") == title
    ]

    if len(matches) != 1:
        raise ValueError(
            f"Se esperaba un nodo '{title}', encontrados: {len(matches)}"
        )

    return matches[0]


def node_id_by_title(workflow, title):
    matches = [
        node_id for node_id, node in workflow.items()
        if node.get("_meta", {}).get("title") == title
    ]

    if len(matches) != 1:
        raise ValueError(f"Nodo no encontrado o duplicado: {title}")

    return matches[0]


def prepare_workflow(
    source,
    reference=None,
    prompt=None,
    negative=None,
    seed=None,
    width=None,
    height=None,
    steps=None,
    cfg=None,
    ip_weight=None,
    prefix=None,
    denoise=0.25,
    latent_mode="reference"
):
    workflow = copy.deepcopy(source)

    def update(title, key, value):
        if value is not None:
            node_by_title(workflow, title)["inputs"][key] = value

    update("Load Image", "image", reference)
    update("Positive Prompt", "text", prompt)
    update("Negative Prompt", "text", negative)

    update("KSampler", "seed", seed)
    update("KSampler", "steps", steps)
    update("KSampler", "cfg", cfg)
    update("KSampler", "denoise", denoise)

    update("IPAdapter Advanced", "weight", ip_weight)
    update("Save Image", "filename_prefix", prefix)

    sampler = node_by_title(workflow, "KSampler")

    if latent_mode == "reference":
        load_image_id = node_id_by_title(workflow, "Load Image")
        checkpoint_id = node_id_by_title(workflow, "Load Checkpoint")

        numeric_ids = [
            int(key) for key in workflow
            if str(key).isdigit()
        ]

        new_id = str(max(numeric_ids, default=0) + 1)

        workflow[new_id] = {
            "class_type": "VAEEncode",
            "inputs": {
                "pixels": [load_image_id, 0],
                "vae": [checkpoint_id, 2]
            },
            "_meta": {
                "title": "Reference VAE Encode"
            }
        }

        sampler["inputs"]["latent_image"] = [new_id, 0]

    elif latent_mode == "noise":
        update("Empty Latent", "width", width)
        update("Empty Latent", "height", height)

        empty_latent_id = node_id_by_title(
            workflow, "Empty Latent"
        )

        sampler["inputs"]["latent_image"] = [
            empty_latent_id, 0
        ]

    else:
        raise ValueError(
            f"Modo latent no soportado: {latent_mode}"
        )

    return workflow


def inspect_workflow(workflow):
    return [
        {
            "id": node_id,
            "type": node.get("class_type"),
            "title": node.get("_meta", {}).get("title")
        }
        for node_id, node in workflow.items()
    ]
