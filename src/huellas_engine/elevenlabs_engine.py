import os
from pathlib import Path

import numpy as np
import requests

SAMPLE_RATE = 24000
API_URL = "https://api.elevenlabs.io/v1/text-to-speech/{voice_id}"


def get_api_key():
    """Load the API key from the environment or the repository .env file."""
    key = os.getenv("ELEVENLABS_API_KEY")
    if key:
        return key

    try:
        from dotenv import load_dotenv
    except ImportError:
        load_dotenv = None

    if load_dotenv is not None:
        env_path = Path(__file__).resolve().parents[2] / ".env"
        load_dotenv(env_path, override=False)
    key = os.getenv("ELEVENLABS_API_KEY")
    if not key:
        raise RuntimeError(
            "Falta ELEVENLABS_API_KEY. Añádela a .env en la raíz del "
            "repositorio o expórtala en el entorno. No la guardes en Git."
        )
    return key


def synthesize_text_to_file(
    text,
    output_path,
    voice_id,
    model_id="eleven_multilingual_v2",
    timeout=180
):
    """Generate 24 kHz PCM with the voice's saved ElevenLabs settings."""
    try:
        import soundfile as sf
    except ImportError as exc:
        raise RuntimeError(
            "Falta SoundFile. Instala las dependencias TTS del proyecto."
        ) from exc

    text = str(text).strip()
    if not text:
        raise ValueError("No se puede generar audio con texto vacío")
    if not voice_id or len(voice_id) < 8:
        raise ValueError("Voice ID de ElevenLabs inválido")

    response = requests.post(
        API_URL.format(voice_id=voice_id),
        params={"output_format": "pcm_24000"},
        headers={
            "xi-api-key": get_api_key(),
            "Content-Type": "application/json",
            "Accept": "application/octet-stream"
        },
        json={
            "text": text,
            "model_id": model_id
        },
        timeout=timeout
    )

    if not response.ok:
        detail = response.text[:1200]
        if response.status_code == 401:
            raise RuntimeError(
                "ElevenLabs rechazó la API Key (401). Revisa "
                "ELEVENLABS_API_KEY; no se ha guardado ni mostrado."
            )
        if response.status_code == 402:
            raise RuntimeError(
                "ElevenLabs indica que no hay créditos o cuota disponible "
                "(402). Revisa el saldo/plan antes de volver a generar."
            )
        if response.status_code == 429:
            raise RuntimeError(
                "ElevenLabs limitó las solicitudes (429). Espera y reintenta."
            )
        raise RuntimeError(
            f"ElevenLabs API error {response.status_code}: {detail}"
        )

    if not response.content or len(response.content) % 2:
        raise RuntimeError(
            "ElevenLabs devolvió PCM vacío o con tamaño inválido."
        )

    samples = np.frombuffer(response.content, dtype="<i2")
    if samples.size == 0:
        raise RuntimeError("ElevenLabs devolvió audio vacío.")

    waveform = (samples.astype(np.float32) / 32768.0).clip(-1.0, 1.0)
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = output_path.with_name(output_path.stem + ".tmp.wav")
    sf.write(temporary_path, waveform, SAMPLE_RATE, subtype="PCM_16")
    temporary_path.replace(output_path)

    return {
        "path": str(output_path),
        "duration_seconds": round(len(waveform) / SAMPLE_RATE, 3),
        "sample_rate": SAMPLE_RATE,
        "voice_id": voice_id,
        "model_id": model_id,
        "provider": "elevenlabs"
    }
