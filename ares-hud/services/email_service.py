"""
Servizio email: si connette alla casella via IMAP e recupera le email più
recenti (mittente, oggetto, data, anteprima del testo). Nessuna logica di
riassunto qui dentro — solo dati grezzi dalla casella di posta. Il riassunto
vero e proprio è compito di core.email_analysis.
"""
import email
import imaplib
import json
from email.header import decode_header
from email.utils import parsedate_to_datetime

from config import EMAIL_CONFIG_FILE

DEFAULT_CONFIG = {
    "enabled": False,
    "imap_host": "imap.gmail.com",
    "imap_port": 993,
    "email_address": "",
    "app_password": "",
    "max_emails": 12,
    "refresh_minutes": 10,
}


def load_email_config():
    """
    Legge la configurazione IMAP da email_config.json. Se il file non esiste
    ne crea uno di default (disattivato, da compilare a mano con le proprie
    credenziali).
    """
    try:
        with open(EMAIL_CONFIG_FILE, "r", encoding="utf-8") as f:
            cfg = json.load(f)
            return {**DEFAULT_CONFIG, **cfg}
    except FileNotFoundError:
        try:
            with open(EMAIL_CONFIG_FILE, "w", encoding="utf-8") as f:
                json.dump(DEFAULT_CONFIG, f, indent=2)
        except Exception as e:
            print(f"Errore creazione email_config.json: {e}")
        return dict(DEFAULT_CONFIG)
    except Exception as e:
        print(f"Errore lettura email_config.json: {e}")
        return dict(DEFAULT_CONFIG)


def _decode_mime_words(raw):
    if not raw:
        return ""
    parts = decode_header(raw)
    decoded = ""
    for text, enc in parts:
        if isinstance(text, bytes):
            try:
                decoded += text.decode(enc or "utf-8", errors="ignore")
            except Exception:
                decoded += text.decode("utf-8", errors="ignore")
        else:
            decoded += text
    return decoded


def _extract_snippet(msg, max_chars=400):
    """Estrae un'anteprima testuale semplice dal corpo dell'email (solo testo, niente HTML)."""
    body = ""
    if msg.is_multipart():
        for part in msg.walk():
            content_type = part.get_content_type()
            disposition = str(part.get("Content-Disposition") or "")
            if content_type == "text/plain" and "attachment" not in disposition:
                try:
                    charset = part.get_content_charset() or "utf-8"
                    payload = part.get_payload(decode=True)
                    if payload:
                        body = payload.decode(charset, errors="ignore")
                        break
                except Exception:
                    continue
    else:
        try:
            charset = msg.get_content_charset() or "utf-8"
            payload = msg.get_payload(decode=True)
            if payload:
                body = payload.decode(charset, errors="ignore")
        except Exception:
            body = ""

    body = " ".join(body.split())  # righe vuote multiple, spazi ripetuti
    return body[:max_chars]


def fetch_recent_emails():
    """
    Si connette alla casella via IMAP e restituisce le email più recenti come
    lista di dict: {sender, subject, date, snippet}.
    Restituisce (lista, None) in caso di successo, oppure (None, motivo) in
    caso di fallimento. motivo è 'not_configured' se mancano le credenziali,
    altrimenti una stringa con il dettaglio dell'errore.
    """
    cfg = load_email_config()
    if not cfg.get("enabled") or not cfg.get("email_address") or not cfg.get("app_password"):
        return None, "not_configured"

    try:
        imap = imaplib.IMAP4_SSL(cfg["imap_host"], cfg["imap_port"])
        imap.login(cfg["email_address"], cfg["app_password"])
        imap.select("INBOX")

        status, data = imap.search(None, "ALL")
        if status != "OK":
            imap.logout()
            return None, "Impossibile leggere la casella di posta"

        ids = data[0].split()
        recent_ids = ids[-cfg.get("max_emails", 12):]
        recent_ids.reverse()  # dal più recente al meno recente

        emails = []
        for eid in recent_ids:
            status, msg_data = imap.fetch(eid, "(RFC822)")
            if status != "OK" or not msg_data or not msg_data[0]:
                continue
            raw = msg_data[0][1]
            msg = email.message_from_bytes(raw)

            sender = _decode_mime_words(msg.get("From", ""))
            subject = _decode_mime_words(msg.get("Subject", "(nessun oggetto)"))
            date_raw = msg.get("Date", "")
            try:
                date_parsed = parsedate_to_datetime(date_raw).isoformat()
            except Exception:
                date_parsed = None

            emails.append({
                "sender": sender,
                "subject": subject,
                "date": date_parsed,
                "snippet": _extract_snippet(msg),
            })

        imap.logout()
        return emails, None
    except imaplib.IMAP4.error as e:
        return None, f"Credenziali IMAP non valide: {e}"
    except Exception as e:
        return None, str(e)
