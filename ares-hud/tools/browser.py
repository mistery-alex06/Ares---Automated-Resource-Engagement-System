"""
Tool di controllo del browser: esecuzione di JavaScript nelle tab di Chrome via
AppleScript, apertura siti, ricerca Google, controllo video YouTube.

NOTA IMPORTANTE per l'utente: perché queste funzioni possano eseguire
JavaScript nelle pagine, in Chrome deve essere attiva l'opzione
"Vista > Opzioni per sviluppatori > Consenti JavaScript da Apple Events"
(va abilitata una volta per ciascun profilo Chrome che usi).
"""
import re
import subprocess
from urllib.parse import quote

from config import IS_MAC


def applescript_escape(text):
    """Rende sicura una stringa da inserire in un literal AppleScript tra virgolette."""
    return text.replace('\\', '\\\\').replace('"', '\\"')


def run_js_in_tab_matching(url_substring, js_code):
    """
    Esegue js_code nella prima tab di Chrome (in qualunque finestra) la cui URL
    contiene url_substring. js_code NON deve contenere doppi apici (") — usa
    apici singoli per le stringhe JS, così non serve fare escaping complesso.
    Restituisce il risultato testuale, oppure None se nessuna tab corrisponde
    o si verifica un errore (es. l'esecuzione JS è disattivata in Chrome).
    """
    applescript = f'''
    tell application "Google Chrome"
        set resultText to "__NO_TAB__"
        repeat with w in windows
            repeat with t in tabs of w
                if URL of t contains "{url_substring}" then
                    tell t
                        try
                            set resultText to execute javascript "{js_code}"
                        on error errMsg
                            set resultText to "__JS_ERROR__: " & errMsg
                        end try
                    end tell
                end if
            end repeat
        end repeat
        return resultText
    end tell
    '''
    try:
        result = subprocess.run(['osascript', '-e', applescript], capture_output=True, text=True, timeout=10)
        output = result.stdout.strip()
    except Exception as e:
        print(f"Errore esecuzione JS in Chrome: {e}")
        return None

    if output == "__NO_TAB__":
        return None
    if output.startswith("__JS_ERROR__"):
        print(f"Errore JavaScript in Chrome: {output}")
        return None
    return output


def focus_tab_matching(url_substring):
    """Porta in primo piano (finestra + tab) la prima tab la cui URL contiene url_substring."""
    applescript = f'''
    tell application "Google Chrome"
        set foundTab to false
        repeat with w in windows
            set idx to 0
            repeat with t in tabs of w
                set idx to idx + 1
                if URL of t contains "{url_substring}" then
                    set active tab index of w to idx
                    set index of w to 1
                    set foundTab to true
                end if
            end repeat
        end repeat
        return foundTab
    end tell
    '''
    try:
        result = subprocess.run(['osascript', '-e', applescript], capture_output=True, text=True, timeout=10)
        if result.stdout.strip() != "true":
            return False
    except Exception as e:
        print(f"Errore attivazione tab: {e}")
        return False

    try:
        subprocess.run(['osascript', '-e', 'tell application "Google Chrome" to activate'], timeout=5)
    except Exception as e:
        print(f"Errore attivazione Chrome: {e}")
    return True


def type_with_keystrokes(text):
    """
    Digita testo reale tramite System Events, come se l'utente lo stesse scrivendo
    con la tastiera. Più lento del JS ma molto piu' affidabile con editor di testo
    complessi come quello di WhatsApp Web, che ignorano l'inserimento diretto via JS.
    Richiede che l'elemento giusto abbia gia' il focus (vedi chiamanti).
    """
    safe_text = applescript_escape(text)
    script = f'tell application "System Events" to keystroke "{safe_text}"'
    try:
        subprocess.run(['osascript', '-e', script], timeout=15)
    except Exception as e:
        print(f"Errore durante la digitazione: {e}")


def press_return_key():
    try:
        subprocess.run(['osascript', '-e', 'tell application "System Events" to key code 36'], timeout=5)
    except Exception as e:
        print(f"Errore pressione tasto Invio: {e}")


def open_in_chrome(url):
    try:
        subprocess.Popen(['open', '-a', 'Google Chrome', url])
        return True
    except Exception as e:
        print(f"Errore apertura Chrome: {e}")
        return False


def control_youtube(action):
    """
    Mette in pausa o fa ripartire il video nella prima tab YouTube trovata,
    eseguendo JavaScript nella pagina tramite AppleScript.
    Restituisce 'paused', 'playing', 'no_video' o 'not_found'.
    """
    if not IS_MAC:
        return "not_found"

    if action == "pause":
        js_body = "if(!v.paused){v.pause();}"
    elif action == "play":
        js_body = "if(v.paused){v.play();}"
    else:  # "toggle": vero toggle, usato dal pulsante Play/Pausa del widget
        js_body = "if(v.paused){v.play();}else{v.pause();}"

    js = (
        "(function(){"
        "var v=document.querySelector('video');"
        "if(!v){return 'no_video';}"
        f"{js_body}"
        "return v.paused ? 'paused' : 'playing';"
        "})();"
    )

    applescript = f'''
    tell application "Google Chrome"
        set resultText to "not_found"
        repeat with w in windows
            repeat with t in tabs of w
                if URL of t contains "youtube.com/watch" then
                    tell t
                        set resultText to execute javascript "{js}"
                    end tell
                end if
            end repeat
        end repeat
        return resultText
    end tell
    '''

    try:
        result = subprocess.run(['osascript', '-e', applescript], capture_output=True, text=True, timeout=10)
        return result.stdout.strip() or "not_found"
    except Exception as e:
        print(f"Errore controllo YouTube: {e}")
        return "not_found"


def _click_youtube_button(selector_class):
    """
    Clicca un pulsante del player YouTube (es. 'ytp-next-button') tramite un
    click JS sintetico (stesso approccio affidabile usato per WhatsApp Web).
    Restituisce 'ok' se il pulsante esiste e viene cliccato, 'not_available'
    se il pulsante non è presente (es. video non in una playlist), oppure
    'not_found' se non c'è nessuna tab YouTube aperta.
    """
    if not IS_MAC:
        return "not_found"

    js = (
        "(function(){"
        f"var b=document.querySelector('.{selector_class}');"
        "if(!b){return 'not_available';}"
        "b.click();"
        "return 'ok';"
        "})();"
    )

    applescript = f'''
    tell application "Google Chrome"
        set resultText to "not_found"
        repeat with w in windows
            repeat with t in tabs of w
                if URL of t contains "youtube.com/watch" then
                    tell t
                        set resultText to execute javascript "{js}"
                    end tell
                end if
            end repeat
        end repeat
        return resultText
    end tell
    '''

    try:
        result = subprocess.run(['osascript', '-e', applescript], capture_output=True, text=True, timeout=10)
        return result.stdout.strip() or "not_found"
    except Exception as e:
        print(f"Errore controllo YouTube: {e}")
        return "not_found"


def youtube_next():
    """Salta al video successivo (funziona solo se il video fa parte di una playlist/coda)."""
    return _click_youtube_button("ytp-next-button")


def youtube_previous():
    """Torna al video precedente (funziona solo se il video fa parte di una playlist/coda)."""
    return _click_youtube_button("ytp-prev-button")


SITE_ALIASES = {
    "youtube": "https://www.youtube.com",
    "google": "https://www.google.com",
    "gmail": "https://mail.google.com",
    "posta": "https://mail.google.com",
    "drive": "https://drive.google.com",
    "maps": "https://maps.google.com",
    "mappe": "https://maps.google.com",
    "netflix": "https://www.netflix.com",
    "spotify": "https://open.spotify.com",
    "amazon": "https://www.amazon.it",
    "whatsapp": "https://web.whatsapp.com",
    "facebook": "https://www.facebook.com",
    "instagram": "https://www.instagram.com",
    "twitter": "https://twitter.com",
    "x": "https://twitter.com",
    "github": "https://github.com",
    "wikipedia": "https://www.wikipedia.org",
    "twitch": "https://www.twitch.tv",
    "reddit": "https://www.reddit.com",
    "linkedin": "https://www.linkedin.com",
}


def resolve_site_url(name):
    """Trasforma un nome parlato (es. 'youtube') nell'URL da aprire, con un'etichetta leggibile."""
    name_clean = re.sub(r"^(il|lo|la|l')\s+", "", name.strip().lower())

    if name_clean in SITE_ALIASES:
        return SITE_ALIASES[name_clean], name_clean.capitalize()

    # Se sembra già un dominio (es. 'openai.com'), usalo così com'è
    if '.' in name_clean and ' ' not in name_clean:
        url = name_clean if name_clean.startswith('http') else f'https://{name_clean}'
        return url, name_clean

    # Altrimenti tenta un dominio .com plausibile
    guess = name_clean.replace(' ', '')
    return f'https://www.{guess}.com', name_clean


def google_search_reply(query):
    if not query:
        return "Non ho capito, puoi ripetere?", None
    url = f"https://www.google.com/search?q={quote(query)}"
    if open_in_chrome(url):
        return f'Cerco "{query}" su Google.', None
    return "Non sono riuscito ad aprire Chrome per la ricerca.", None
