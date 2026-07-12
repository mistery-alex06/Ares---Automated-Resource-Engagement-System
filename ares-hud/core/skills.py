"""
Motore di comandi estensibile (skill registry). Ogni skill è una funzione che
riceve il messaggio dell'utente e restituisce:
  - None                          se non è di sua competenza
  - (reply_text, weather_or_None) se ha gestito la richiesta

Le skill sono ordinate per "priority" (più basso = eseguito prima). L'ultima
skill registrata (priority molto alta) è il fallback finale e gestisce sempre
qualunque messaggio, quindi il dispatcher termina sempre con una risposta.

Per aggiungere una nuova skill: scrivere una funzione con questa forma e
decorarla con @skill("nome_skill", priority=N). La logica delle singole azioni
(automazione browser, chiamate LLM, hardware, ecc.) vive nei moduli
tools/ e services/; qui c'è solo l'interpretazione dell'intento e l'orchestrazione.
"""
import re
from datetime import datetime, timedelta

from core import llm as llm_service
from core import memory
from core import email_analysis
from services import weather as weather_service
from tools import browser
from tools import whatsapp
from tools import reminders
from tools import spotify
from tools import discord_app

_SKILLS = []


def skill(name, priority=50):
    def decorator(func):
        _SKILLS.append({"name": name, "priority": priority, "handler": func})
        _SKILLS.sort(key=lambda s: s["priority"])
        return func
    return decorator


# --- Skill: Invio messaggi WhatsApp Web --------------------------------------

def _extract_whatsapp_command(text):
    """
    Riconosce comandi come:
      - 'manda un messaggio a mamma su whatsapp: come stai?'
      - 'invia a Marco su whatsapp che sto arrivando'
      - 'scrivi a Luca su whatsapp ci vediamo alle 8'
    Restituisce (contatto, testo_messaggio) oppure None. Case originale preservato
    per il testo del messaggio (il riconoscimento del comando è case-insensitive).
    """
    m = re.search(
        r"\b(?:manda|invia|scrivi)\s+(?:un\s+messaggio\s+)?a\s+(.+?)\s+su\s+whatsapp\s*(?:[:,]|che\s+dice|dicendo)?\s*(.+)",
        text,
        re.IGNORECASE,
    )
    if not m:
        return None
    contatto = m.group(1).strip()
    messaggio = m.group(2).strip()
    if not contatto or not messaggio:
        return None
    return contatto, messaggio


@skill("whatsapp_invia", priority=15)
def _skill_whatsapp(message):
    result = _extract_whatsapp_command(message)
    if not result:
        return None

    contatto, testo = result
    ok, motivo = whatsapp.send_message(contatto, testo)

    if ok:
        return f"Messaggio inviato a {contatto} su WhatsApp.", None
    if motivo == 'no_tab':
        return "Non ho trovato nessuna scheda di WhatsApp Web aperta in Chrome.", None
    if motivo == 'no_results':
        return f"Non ho trovato nessun contatto o gruppo chiamato \"{contatto}\" su WhatsApp.", None
    return "Non sono riuscito a inviare il messaggio su WhatsApp. Controlla che in Chrome sia attiva l'opzione \"Consenti JavaScript da Apple Events\" (Vista > Opzioni per sviluppatori).", None


# --- Skill: Spotify (controllo nativo via AppleScript) ----------------------

def _extract_spotify_command(text):
    """
    Riconosce comandi Spotify. Richiede sempre una parola chiave esplicita
    ('spotify', 'la musica' o 'canzone') tranne che per l'apertura, così da
    non entrare in conflitto con il controllo video di YouTube (che usa le
    stesse parole 'pausa'/'play' ma senza richiedere un contesto musicale).
    Restituisce (azione, valore_o_None) oppure None.
    """
    text_lower = text.lower().strip()

    if re.search(r"\bapri\s+spotify\b", text_lower):
        return "open", None

    # Frasi inequivocabili: non serve la parola chiave 'spotify/musica/canzone'
    if re.search(r"\b(cosa\s+sta\s+suonando|che\s+canzone\s+(è|e['’])|che\s+musica\s+(è|e['’]))\b", text_lower):
        return "current", None

    mentions_music = bool(re.search(r"\b(spotify|la musica|canzone)\b", text_lower))
    if not mentions_music:
        return None

    if re.search(r"\b(prossima|salta|skip|avanti)\b", text_lower):
        return "next", None
    if re.search(r"\b(precedente|indietro)\b", text_lower):
        return "previous", None
    vol_match = re.search(r"volume\D*(\d{1,3})", text_lower)
    if vol_match:
        return "volume", int(vol_match.group(1))
    if re.search(r"\b(pausa|ferma|stoppa|metti\s+in\s+pausa)\b", text_lower):
        return "pause", None
    if re.search(r"\b(riprendi|fai\s+partire|avvia|riproduci|play)\b", text_lower):
        return "play", None

    return None


@skill("spotify", priority=12)
def _skill_spotify(message):
    result = _extract_spotify_command(message)
    if not result:
        return None
    azione, valore = result

    if azione == "open":
        return ("Apro Spotify.", None) if spotify.open_app() else ("Non sono riuscito ad aprire Spotify.", None)

    if azione == "current":
        track = spotify.get_current_track()
        if not track:
            return "Spotify non è aperto o non sta riproducendo nulla al momento.", None
        stato = "in pausa" if track["state"] == "paused" else "in riproduzione"
        return f"Sto ascoltando {track['title']} di {track['artist']}, {stato}.", None

    if azione == "volume":
        ok = spotify.set_volume(valore)
        return (f"Volume di Spotify impostato al {valore}%.", None) if ok else ("Spotify non sembra aperto.", None)

    azioni_semplici = {
        "pause": (spotify.pause, "Musica in pausa."),
        "play": (spotify.play, "Riprendo la riproduzione."),
        "next": (spotify.next_track, "Prossima canzone."),
        "previous": (spotify.previous_track, "Canzone precedente."),
    }
    funzione, messaggio_ok = azioni_semplici[azione]
    return (messaggio_ok, None) if funzione() else ("Spotify non sembra aperto.", None)


# --- Skill: Discord (controllo via scorciatoie da tastiera native) ----------

def _extract_discord_command(text):
    """Riconosce comandi Discord. Richiede sempre la parola 'discord' esplicita."""
    text_lower = text.lower().strip()
    if "discord" not in text_lower:
        return None

    if re.search(r"\bapri\b", text_lower):
        return "open"
    if re.search(r"\b(silenzia|muta|disattiva\s+il\s+microfono|riattiva\s+il\s+microfono)\b", text_lower):
        return "mute"
    if re.search(r"\bdisattiva\s+(completamente\s+)?l['’]audio\b", text_lower):
        return "deafen"

    return None


@skill("discord", priority=13)
def _skill_discord(message):
    azione = _extract_discord_command(message)
    if not azione:
        return None

    if azione == "open":
        return ("Apro Discord.", None) if discord_app.open_app() else ("Non sono riuscito ad aprire Discord.", None)

    funzioni = {"mute": discord_app.toggle_mute, "deafen": discord_app.toggle_deafen}
    messaggi_ok = {"mute": "Fatto, ho attivato/disattivato il microfono su Discord.", "deafen": "Fatto, ho attivato/disattivato l'audio su Discord."}

    ok, motivo = funzioni[azione]()
    if ok:
        return messaggi_ok[azione], None
    if motivo == 'not_running':
        return "Discord non risulta aperto al momento.", None
    return "Non sono riuscito a controllare Discord.", None


# --- Skill: Meteo -----------------------------------------------------------

def _extract_city_from_message(text):
    """
    Estrae il nome della città da una frase come 'com'è il meteo a Parigi?'.
    Riconosce la richiesta solo se compare una parola legata al meteo,
    poi cerca l'ultima occorrenza di 'a/in/di <città>' nella frase.
    """
    text_lower = text.lower()
    if not any(k in text_lower for k in ("meteo", "tempo", "temperatura")):
        return None

    matches = re.findall(r"\b(?:a|ad|in|di)\s+([a-zà-ù][a-zà-ù\s']*?)(?:\?|!|\.|,|$)", text_lower)
    if not matches:
        return None
    return matches[-1].strip()


def _build_weather_reply(w):
    return (
        f"A {w['city']} ci sono {w['temp']} gradi, cielo {w['condition'].lower()}. "
        f"Umidità al {w['humidity']} per cento, vento a {w['windSpeed']} chilometri orari."
    )


@skill("meteo", priority=10)
def _skill_meteo(message):
    city = _extract_city_from_message(message)
    if not city:
        return None

    w = weather_service.fetch_weather_for_city(city)
    if not w:
        return f"Non sono riuscito a trovare la città \"{city}\".", None

    weather_service.set_active_city(w)
    return _build_weather_reply(w), w


# --- Skill: Controllo video YouTube ------------------------------------------

def _extract_media_command(text):
    """Riconosce comandi per controllare un video YouTube già aperto."""
    text_lower = text.lower().strip()
    if re.search(r"\b(metti in pausa|pausa|ferma il video|stoppa il video|fermalo|mettilo in pausa)\b", text_lower):
        return "pause"
    if re.search(r"\b(riprendi|riproduci|fai partire il video|manda avanti il video|play)\b", text_lower):
        return "play"
    return None


@skill("controllo_video", priority=20)
def _skill_media(message):
    media_action = _extract_media_command(message)
    if not media_action:
        return None

    status = browser.control_youtube(media_action)
    if status == "paused":
        return "Video messo in pausa.", None
    if status == "playing":
        return "Video ripreso.", None
    if status == "no_video":
        return "Ho trovato la tab di YouTube ma nessun video attivo al suo interno.", None
    return "Non ho trovato nessun video di YouTube aperto in Chrome.", None


# --- Skill: Promemoria / task pianificati ------------------------------------

_UNITA_MINUTI = {"minuto": 1, "minuti": 1, "ora": 60, "ore": 60}


def _extract_reminder_command(text):
    """
    Riconosce comandi come:
      - 'ricordami tra 10 minuti di comprare il latte'
      - 'ricordami fra 2 ore di chiamare Marco'
      - 'ricordami alle 18:30 di uscire'
    Restituisce (datetime, testo_promemoria) oppure None.
    """
    text_lower = text.lower().strip()

    # Relativo: "tra/fra N minuti|ore di ..."
    m = re.search(
        r"\bricordami\s+(?:tra|fra)\s+(\d+)\s*(minuti|minuto|ore|ora)\s+di\s+(.+)",
        text_lower,
    )
    if m:
        quantita = int(m.group(1))
        unita = m.group(2)
        contenuto = m.group(3).strip().rstrip('?!.')
        minuti_totali = quantita * _UNITA_MINUTI.get(unita, 1)
        when = datetime.now() + timedelta(minutes=minuti_totali)
        return when, contenuto

    # Assoluto: "alle HH:MM di ..." (oggi, o domani se l'orario è già passato)
    m = re.search(
        r"\bricordami\s+alle\s+(\d{1,2})[:.](\d{2})\s+di\s+(.+)",
        text_lower,
    )
    if m:
        ora, minuto = int(m.group(1)), int(m.group(2))
        contenuto = m.group(3).strip().rstrip('?!.')
        when = datetime.now().replace(hour=ora, minute=minuto, second=0, microsecond=0)
        if when <= datetime.now():
            when += timedelta(days=1)
        return when, contenuto

    return None


@skill("promemoria_lista", priority=25)
def _skill_lista_promemoria(message):
    text_lower = message.lower()
    if not re.search(r"\b(che\s+promemoria\s+ho|elenco\s+promemoria|i\s+miei\s+promemoria)\b", text_lower):
        return None

    pending = reminders.list_pending()
    if not pending:
        return "Non hai promemoria attivi al momento.", None

    pending.sort(key=lambda r: r["when"])
    voci = [f"alle {datetime.fromisoformat(r['when']).strftime('%H:%M')}: {r['text']}" for r in pending]
    return "Promemoria attivi — " + "; ".join(voci) + ".", None


@skill("promemoria_crea", priority=26)
def _skill_crea_promemoria(message):
    result = _extract_reminder_command(message)
    if not result:
        return None

    when_dt, contenuto = result
    if not contenuto:
        return "Ho capito che vuoi un promemoria, ma non ho capito per cosa.", None

    reminders.create_reminder(when_dt, contenuto)
    return f"Promemoria impostato per le {when_dt.strftime('%H:%M')}: {contenuto}.", None


# --- Skill: Riassunto email ---------------------------------------------------

_URGENZA_LABEL = {"alta": "urgente", "media": "normale", "bassa": "poco urgente"}


@skill("email_riassunto", priority=27)
def _skill_email_riassunto(message):
    text_lower = message.lower()
    if not re.search(
        r"\b(riassum\w*\s+(le\s+)?(mie\s+)?email|che\s+email\s+ho|controlla\s+(la\s+)?posta|leggimi\s+le\s+email|novit[a\u00e0]\s+(nella\s+)?posta)\b",
        text_lower,
    ):
        return None

    cache = email_analysis.get_cached_summary()
    status = cache.get("status")

    if status in (None, "not_configured"):
        return "L'analisi email non è ancora configurata. Inserisci le tue credenziali IMAP in email_config.json.", None
    if status == "error":
        return f"Non sono riuscito a controllare la posta: {cache.get('error', 'errore sconosciuto')}.", None
    if status == "empty":
        return "La tua casella di posta risulta vuota.", None

    emails = cache.get("emails", [])
    if not emails:
        return "Non ho ancora nessun riassunto email pronto, prova tra poco.", None

    top = emails[:3]
    voci = []
    for e in top:
        mittente = e["sender"].split('<')[0].strip() or e["sender"]
        voci.append(f"da {mittente} ({_URGENZA_LABEL.get(e['urgency'], e['urgency'])}): {e['summary']}")
    return "Ultime email — " + "; ".join(voci) + ".", None


# --- Skill: Domande dirette (ora, data, giorno) ------------------------------

GIORNI_IT = ["lunedì", "martedì", "mercoledì", "giovedì", "venerdì", "sabato", "domenica"]
MESI_IT = [
    "gennaio", "febbraio", "marzo", "aprile", "maggio", "giugno",
    "luglio", "agosto", "settembre", "ottobre", "novembre", "dicembre",
]


@skill("domande_dirette", priority=30)
def _skill_domande_dirette(message):
    """
    Intercetta domande dirette semplici (che ore sono, che giorno è, ecc.) e
    risponde con un valore calcolato localmente, così non finiscono mai su Google.
    """
    text_lower = message.lower().strip()
    now = datetime.now()

    if re.search(r"\b(che\s+or[ae]|mi\s+dici\s+l['’]?\s*ora)\b", text_lower):
        return f"Sono le {now.strftime('%H:%M')}.", None

    if re.search(r"\b(che\s+giorno\s+(è|e['’])?\s*oggi|che\s+data\s+(è|e['’])|oggi\s+che\s+giorno\s+è)\b", text_lower):
        giorno_sett = GIORNI_IT[now.weekday()]
        mese = MESI_IT[now.month - 1]
        return f"Oggi è {giorno_sett} {now.day} {mese} {now.year}.", None

    if re.search(r"\bche\s+giorno\s+della\s+settimana\b", text_lower):
        return f"Oggi è {GIORNI_IT[now.weekday()]}.", None

    return None


# --- Skill: Apertura siti -----------------------------------------------------

def _extract_open_command(text):
    """Riconosce comandi come 'apri youtube', 'vai su github', 'apri il sito reddit'."""
    text_lower = text.lower().strip()
    m = re.search(
        r"\b(?:apri(?:\s+il\s+sito|\s+la\s+pagina)?|vai su)\s+([a-z\u00e0-\u00f90-9\.\-\s]+?)(?:\?|!|\.|$)",
        text_lower,
    )
    if not m:
        return None
    return m.group(1).strip()


@skill("apri_sito", priority=40)
def _skill_apri_sito(message):
    site_name = _extract_open_command(message)
    if not site_name:
        return None

    url, label = browser.resolve_site_url(site_name)
    if browser.open_in_chrome(url):
        return f"Apro {label.capitalize()}.", None
    return "Non sono riuscito ad aprire Chrome.", None


# --- Skill: Ricerca esplicita su Google --------------------------------------

def _extract_search_query(text):
    """Riconosce comandi come 'cerca ricette di pasta', 'fai una ricerca su gatti siberiani'."""
    text_lower = text.lower().strip()
    m = re.search(r"\b(?:cerca(?:\s+su\s+google)?|fai\s+una\s+ricerca(?:\s+su)?)\s+(.+)", text_lower)
    if not m:
        return None
    return m.group(1).strip().rstrip('?!.')


@skill("ricerca_esplicita", priority=50)
def _skill_ricerca_esplicita(message):
    query = _extract_search_query(message)
    if not query:
        return None
    return browser.google_search_reply(query)


# --- Skill: Fallback finale — LLM cloud (Gemini), poi Google -----------------
# Questa skill ha priorità altissima (eseguita per ultima) e gestisce sempre
# il messaggio: prima prova a farlo rispondere da Gemini (arricchito con
# memoria e documenti locali); solo se non risponde, ripiega su Google.

@skill("fallback_llm_o_google", priority=1000)
def _skill_fallback(message):
    llm_reply = llm_service.ask_llm_fallback(message)
    if llm_reply:
        return llm_reply, None

    fallback_query = message.strip().rstrip('?!.')
    return browser.google_search_reply(fallback_query)


def handle_chat_message(message):
    """
    Passa il messaggio a ogni skill registrata, in ordine di priorità, finché
    una di esse lo gestisce, poi salva lo scambio nella memoria persistente
    (core.memory) così l'LLM potrà usarlo come contesto nelle richieste future.
    La skill di fallback (priorità 1000) gestisce sempre qualunque messaggio,
    quindi questa funzione restituisce sempre una risposta valida.
    """
    reply, extra = None, None
    for entry in _SKILLS:
        result = entry["handler"](message)
        if result is not None:
            reply, extra = result
            break

    if reply is None:
        reply, extra = "Non ho capito, puoi ripetere?", None

    memory.save_interaction(message, reply)
    return reply, extra


# ══════════════════════════════════════════════════════════════════════════
#  CONTROLLO APP — azioni dirette dal widget (pulsanti, non testo libero)
# ══════════════════════════════════════════════════════════════════════════

def handle_app_control(app_name, action):
    """
    Gestisce i clic sui pulsanti del widget "CONTROLLO APP". A differenza delle
    skill sopra (che interpretano testo libero), qui app/azione arrivano già
    determinati dal frontend. Restituisce (ok: bool, message: str).
    """
    if app_name == "youtube":
        if action == "playpause":
            status = browser.control_youtube("toggle")
            if status == "paused":
                return True, "Video in pausa."
            if status == "playing":
                return True, "Video in riproduzione."
            if status == "no_video":
                return False, "Nessun video attivo nella tab YouTube."
            return False, "Nessuna tab YouTube aperta."
        if action in ("next", "previous"):
            fn = browser.youtube_next if action == "next" else browser.youtube_previous
            status = fn()
            if status == "ok":
                return True, "Fatto."
            if status == "not_available":
                return False, "Disponibile solo con una playlist attiva."
            return False, "Nessuna tab YouTube aperta."
        return False, "Azione non valida."

    if app_name == "spotify":
        if action == "playpause":
            return (True, "Fatto.") if spotify.play_pause() else (False, "Spotify non sembra aperto.")
        if action == "next":
            return (True, "Prossima canzone.") if spotify.next_track() else (False, "Spotify non sembra aperto.")
        return False, "Azione non valida."

    if app_name == "discord":
        if action == "camera":
            ok, motivo = discord_app.toggle_camera()
        elif action == "mic":
            ok, motivo = discord_app.toggle_mute()
        else:
            return False, "Azione non valida."
        if ok:
            return True, "Fatto."
        return (False, "Discord non risulta aperto.") if motivo == 'not_running' else (False, "Non sono riuscito a controllare Discord.")

    return False, "App non riconosciuta."
