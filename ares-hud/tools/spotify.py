"""
Tool Spotify: controllo dell'app Spotify desktop via AppleScript nativo.
Spotify espone un vero dizionario di scripting (a differenza di WhatsApp o
Discord), quindi qui il controllo è diretto e affidabile quanto un click
reale nell'app — non serve alcuna automazione dell'interfaccia.
"""
import subprocess


def open_app():
    try:
        subprocess.run(['open', '-a', 'Spotify'], timeout=5)
        return True
    except Exception as e:
        print(f"Errore apertura Spotify: {e}")
        return False


def is_running():
    try:
        result = subprocess.run(
            ['osascript', '-e', 'application "Spotify" is running'],
            capture_output=True, text=True, timeout=5,
        )
        return result.stdout.strip() == "true"
    except Exception:
        return False


def _run_spotify_script(script_body):
    """
    Esegue uno script AppleScript diretto a Spotify. Restituisce l'output
    (stringa, eventualmente vuota) in caso di successo, None in caso di errore.
    NOTA: 'tell application "Spotify"' avvia automaticamente Spotify se non è
    già in esecuzione — comportamento voluto per i comandi che agiscono
    (play, pause, ecc.), ma va evitato per le sole letture di stato.
    """
    full_script = f'tell application "Spotify"\n{script_body}\nend tell'
    try:
        result = subprocess.run(['osascript', '-e', full_script], capture_output=True, text=True, timeout=8)
        if result.returncode != 0:
            return None
        return result.stdout.strip()
    except Exception as e:
        print(f"Errore controllo Spotify: {e}")
        return None


def play():
    return _run_spotify_script("play") is not None


def pause():
    return _run_spotify_script("pause") is not None


def play_pause():
    return _run_spotify_script("playpause") is not None


def next_track():
    return _run_spotify_script("next track") is not None


def previous_track():
    return _run_spotify_script("previous track") is not None


def set_volume(percent):
    percent = max(0, min(100, int(percent)))
    return _run_spotify_script(f"set sound volume to {percent}") is not None


def get_current_track():
    """
    Restituisce {"artist", "title", "state"} sulla traccia corrente, oppure
    None se Spotify non è aperto o non sta riproducendo nulla. Non avvia
    Spotify se non è già in esecuzione (una semplice domanda non deve aprirlo).
    """
    if not is_running():
        return None
    out = _run_spotify_script(
        'set trackName to name of current track\n'
        'set trackArtist to artist of current track\n'
        'set playState to player state as string\n'
        'return trackArtist & "|||" & trackName & "|||" & playState'
    )
    if not out or "|||" not in out:
        return None
    parts = out.split("|||")
    if len(parts) != 3:
        return None
    artist, title, state = parts
    return {"artist": artist, "title": title, "state": state}
