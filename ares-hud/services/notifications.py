"""
Servizio notifiche: invio di notifiche native macOS.
"""
import subprocess

from config import IS_MAC


def mac_notify(title, text):
    if not IS_MAC:
        print(f"[NOTIFICA] {title}: {text}")
        return
    # Escape delle virgolette per non rompere lo script AppleScript
    safe_title = title.replace('"', '\\"')
    safe_text = text.replace('"', '\\"')
    script = f'display notification "{safe_text}" with title "{safe_title}" sound name "Glass"'
    try:
        subprocess.run(['osascript', '-e', script], timeout=5)
    except Exception as e:
        print(f"Errore invio notifica macOS: {e}")
