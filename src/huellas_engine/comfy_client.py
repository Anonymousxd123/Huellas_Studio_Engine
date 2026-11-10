import time
import uuid
from pathlib import Path

import requests


class ComfyClient:
    def __init__(self, url="http://127.0.0.1:8188"):
        self.url = url.rstrip("/")
        self.session = requests.Session()
        self.client_id = str(uuid.uuid4())

    def check(self):
        stats = self.session.get(
            f"{self.url}/system_stats", timeout=15
        )
        stats.raise_for_status()

        queue = self.session.get(
            f"{self.url}/queue", timeout=15
        )
        queue.raise_for_status()

        return {
            "system": stats.json(),
            "queue": queue.json()
        }

    def upload_image(self, path):
        path = Path(path).expanduser().resolve()

        if not path.is_file():
            raise FileNotFoundError(path)

        with path.open("rb") as image:
            response = self.session.post(
                f"{self.url}/upload/image",
                files={
                    "image": (
                        path.name,
                        image,
                        "application/octet-stream"
                    )
                },
                data={"type": "input", "overwrite": "true"},
                timeout=120
            )

        response.raise_for_status()
        data = response.json()

        name = data["name"]
        folder = data.get("subfolder", "")

        return f"{folder}/{name}" if folder else name

    def submit(self, workflow):
        response = self.session.post(
            f"{self.url}/prompt",
            json={
                "prompt": workflow,
                "client_id": self.client_id
            },
            timeout=60
        )

        if not response.ok:
            raise RuntimeError(
                f"ComfyUI rechazó el workflow: {response.text}"
            )

        return response.json()["prompt_id"]

    def wait(self, prompt_id, timeout=1800):
        deadline = time.monotonic() + timeout

        while time.monotonic() < deadline:
            response = self.session.get(
                f"{self.url}/history/{prompt_id}",
                timeout=30
            )
            response.raise_for_status()

            item = response.json().get(prompt_id)

            if item:
                status = item.get("status", {})
                status_name = status.get("status_str", "")

                if status_name.lower() in ("error", "failed"):
                    raise RuntimeError(str(status))

                if item.get("outputs") is not None:
                    return item

            time.sleep(2)

        raise TimeoutError(f"Timeout en trabajo {prompt_id}")

    def download_images(self, history, output_dir):
        output_dir = Path(output_dir).expanduser()
        output_dir.mkdir(parents=True, exist_ok=True)

        downloaded = []

        for node in history.get("outputs", {}).values():
            for item in node.get("images", []):
                response = self.session.get(
                    f"{self.url}/view",
                    params={
                        "filename": item["filename"],
                        "subfolder": item.get("subfolder", ""),
                        "type": item.get("type", "output")
                    },
                    timeout=120
                )
                response.raise_for_status()

                filename = Path(item["filename"]).name
                destination = output_dir / filename

                counter = 1
                while destination.exists():
                    destination = (
                        output_dir /
                        f"{Path(filename).stem}_{counter}"
                        f"{Path(filename).suffix}"
                    )
                    counter += 1

                destination.write_bytes(response.content)
                downloaded.append(destination)

        return downloaded
