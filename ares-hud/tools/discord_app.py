"""
Tool Discord: controllo dell'app Discord desktop. A differenza di Spotify,
Discord non espone un dizionario di scripting AppleScript (è un'app
Electron), quindi qui si opera tramite le sue scorciatoie da tastiera native,
inviate via System Events dopo aver attivato l'app — lo stesso approccio
usato per l'automazione di WhatsApp Web.

NOTA: richiede che l'app "System Events" abbia il permesso di Accessibilità
in Impostazioni di Sistema > Privacy e Sicurezza > Accessibilità (di solito
già concesso se altre automazioni di Ares, come WhatsApp, funzionano).
"""
import subprocess
import time


def open_app():
    try:
        subprocess.run(['open', '-a', 'Discord'], timeout=5)
        return True
    except Exception as e:
        print(f"Errore apertura Discord: {e}")
        return False


def is_running():
    try:
        result = subprocess.run(
            ['osascript', '-e', 'application "Discord" is running'],
            capture_output=True, text=True, timeout=5,
        )
        return result.stdout.strip() == "true"
    except Exception:
        return False


def _activate_discord():
    try:
        subprocess.run(['osascript', '-e', 'tell application "Discord" to activate'], timeout=5)
        time.sleep(0.3)
        return True
    except Exception as e:
        print(f"Errore attivazione Discord: {e}")
        return False


def _send_keystroke(key, modifiers):
    """modifiers: lista di stringhe tipo ['command down', 'shift down']."""
    mod_str = ", ".join(modifiers)
    script = f'tell application "System Events" to keystroke "{key}" using {{{mod_str}}}'
    try:
        subprocess.run(['osascript', '-e', script], timeout=5)
        return True
    except Exception as e:
        print(f"Errore invio scorciatoia Discord: {e}")
        return False


def toggle_mute():
    """Attiva/disattiva il microfono (⌘⇧M). Restituisce (True, None) o (False, motivo)."""
    if not is_running():
        return False, 'not_running'
    if not _activate_discord():
        return False, 'activation_failed'
    _send_keystroke("m", ["command down", "shift down"])
    return True, None


def toggle_deafen():
    """Disattiva/riattiva completamente l'audio, incluso il microfono (⌘⇧D)."""
    if not is_running():
        return False, 'not_running'
    if not _activate_discord():
        return False, 'activation_failed'
    _send_keystroke("d", ["command down", "shift down"])
    return True, None


def toggle_camera():
    """
    Attiva/disattiva la videocamera durante una videochiamata (⌘⇧V).
    NOTA: questa scorciatoia è meno documentata ufficialmente delle altre due
    (mute/deafen); se non dovesse funzionare sulla tua versione di Discord,
    fammelo sapere e la sostituiamo con un click diretto sul pulsante nell'UI.
    """
    if not is_running():
        return False, 'not_running'
    if not _activate_discord():
        return False, 'activation_failed'
    _send_keystroke("v", ["command down", "shift down"])
    return True, None


def open_quick_switcher(query=None):
    """Apre il Quick Switcher (⌘K) e, se fornita, digita una query e preme Invio."""
    if not is_running():
        return False, 'not_running'
    if not _activate_discord():
        return False, 'activation_failed'
    _send_keystroke("k", ["command down"])
    if query:
        time.sleep(0.3)
        safe_query = query.replace('\\', '\\\\').replace('"', '\\"')
        try:
            subprocess.run(['osascript', '-e', f'tell application "System Events" to keystroke "{safe_query}"'], timeout=5)
            time.sleep(0.3)
            subprocess.run(['osascript', '-e', 'tell application "System Events" to key code 36'], timeout=5)
        except Exception as e:
            print(f"Errore digitazione query Discord: {e}")
    return True, None
