"""
Servizio voce (ElevenLabs, opzionale): sintesi vocale delle risposte di Ares.
"""
import json

import requests

from config import VOICE_CONFIG_FILE


def _load_voice_config():
    """
    Legge la chiave API e l'ID voce di ElevenLabs da voice_config.json.
    Se il file non esiste ne crea uno vuoto da compilare a mano.
    """
    try:
        with open(VOICE_CONFIG_FILE, "r", encoding="utf-8") as f:
            cfg = json.load(f)
            return cfg.get("elevenlabs_api_key", "").strip(), cfg.get("elevenlabs_voice_id", "").strip()
    except FileNotFoundError:
        try:
            with open(VOICE_CONFIG_FILE, "w", encoding="utf-8") as f:
                json.dump({"elevenlabs_api_key": "", "elevenlabs_voice_id": ""}, f, indent=2)
        except Exception as e:
            print(f"Errore creazione voice_config.json: {e}")
        return "", ""
    except Exception as e:
        print(f"Errore lettura voice_config.json: {e}")
        return "", ""


ELEVENLABS_API_KEY, ELEVENLABS_VOICE_ID = _load_voice_config()


def synthesize_speech(text):
    """Genera l'audio (mp3, bytes) tramite ElevenLabs. None se non configurato o in errore."""
    if not ELEVENLABS_API_KEY or not ELEVENLABS_VOICE_ID:
        return None
    try:
        resp = requests.post(
            f"https://api.elevenlabs.io/v1/text-to-speech/{ELEVENLABS_VOICE_ID}",
            headers={
                "xi-api-key": ELEVENLABS_API_KEY,
                "Content-Type": "application/json",
                "Accept": "audio/mpeg",
            },
            json={
                "text": text,
                "model_id": "eleven_multilingual_v2",
                "voice_settings": {"stability": 0.5, "similarity_boost": 0.75},
            },
            timeout=20,
        )
        resp.raise_for_status()
        return resp.content
    except Exception as e:
        print(f"Errore sintesi vocale (ElevenLabs): {e}")
        return None
