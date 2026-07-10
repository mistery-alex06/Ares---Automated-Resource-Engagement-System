"""
Tool promemoria: creazione, persistenza su reminders.json e notifica macOS
quando un promemoria scade.
"""
import json
import threading
import time
import uuid
from datetime import datetime, timedelta

from config import REMINDERS_FILE
from services.notifications import mac_notify

_reminders_lock = threading.Lock()
_reminders = []  # ogni elemento: {"id", "when" (iso), "text", "fired"}


def load_reminders():
    global _reminders
    try:
        with open(REMINDERS_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            # Alla riattivazione del server, scarta i promemoria già scaduti da
            # più di un giorno (evita raffiche di notifiche vecchie a ogni riavvio).
            now = datetime.now()
            _reminders = [
                r for r in data
                if not r.get("fired") or (now - datetime.fromisoformat(r["when"])) < timedelta(days=1)
            ]
    except FileNotFoundError:
        _reminders = []
    except Exception as e:
        print(f"Errore lettura reminders.json: {e}")
        _reminders = []


def _save_reminders():
    try:
        with open(REMINDERS_FILE, "w", encoding="utf-8") as f:
            json.dump(_reminders, f, indent=2, ensure_ascii=False)
    except Exception as e:
        print(f"Errore salvataggio reminders.json: {e}")


def reminder_loop():
    while True:
        time.sleep(15)
        now = datetime.now()
        with _reminders_lock:
            due = [r for r in _reminders if not r["fired"] and datetime.fromisoformat(r["when"]) <= now]
            for r in due:
                r["fired"] = True
        for r in due:
            mac_notify("Ares — Promemoria", r["text"])
        if due:
            _save_reminders()


def create_reminder(when_dt, testo):
    reminder = {
        "id": uuid.uuid4().hex[:8],
        "when": when_dt.isoformat(),
        "text": testo,
        "fired": False,
    }
    with _reminders_lock:
        _reminders.append(reminder)
    _save_reminders()
    return reminder


def list_pending():
    with _reminders_lock:
        return [r for r in _reminders if not r["fired"]]
