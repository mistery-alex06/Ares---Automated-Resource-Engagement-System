"""
Analisi email: prende le email grezze da services.email_service e usa la
catena di LLM (core.llm) per estrarne un riassunto conciso, le informazioni
chiave e un livello di urgenza stimato. Il risultato viene messo in cache
(email_cache.json) e aggiornato sia periodicamente in background sia su
richiesta esplicita dal widget "ANALISI EMAIL".
"""
import json
import re
import threading
import time
from datetime import datetime

from config import EMAIL_CACHE_FILE
from services import email_service
from core import llm

_cache_lock = threading.Lock()

SYSTEM_PROMPT_EMAIL = (
    "Sei un assistente che analizza email per un utente italiano. Riceverai una "
    "lista di email, ciascuna con indice, mittente, oggetto e anteprima del testo. "
    "Per OGNI email produci: un riassunto conciso in italiano (massimo 20 parole), "
    "le informazioni chiave se presenti (scadenze, richieste specifiche, importi), "
    "e un livello di urgenza tra \"alta\", \"media\", \"bassa\". "
    "Rispondi SOLO con un array JSON valido, senza testo aggiuntivo, commenti o "
    "blocchi di codice, nel formato esatto: "
    "[{\"index\": 0, \"summary\": \"...\", \"key_info\": \"...\", \"urgency\": \"media\"}]. "
    "L'array deve avere esattamente un elemento per ogni email ricevuta in input, "
    "nello stesso ordine, con lo stesso indice."
)


def _build_prompt(emails):
    lines = []
    for i, e in enumerate(emails):
        lines.append(f"[{i}] Da: {e['sender']}\nOggetto: {e['subject']}\nAnteprima: {e['snippet']}\n")
    return "\n".join(lines)


def _parse_llm_json(raw_text):
    """Estrae un array JSON dalla risposta dell'LLM, tollerando eventuali blocchi ```json```."""
    text = raw_text.strip()
    text = re.sub(r'^```(?:json)?\s*', '', text)
    text = re.sub(r'\s*```$', '', text)
    try:
        parsed = json.loads(text)
        return parsed if isinstance(parsed, list) else None
    except Exception as e:
        print(f"Errore parsing JSON riassunti email: {e}")
        return None


def _empty_cache():
    return {"status": "not_configured", "updated_at": None, "emails": [], "error": None}


def _load_cache():
    try:
        with open(EMAIL_CACHE_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return _empty_cache()


def _save_cache(cache):
    try:
        with open(EMAIL_CACHE_FILE, "w", encoding="utf-8") as f:
            json.dump(cache, f, indent=2, ensure_ascii=False)
    except Exception as e:
        print(f"Errore salvataggio email_cache.json: {e}")


def get_cached_summary():
    """Restituisce l'ultimo risultato disponibile, senza rifare la scansione (per il widget)."""
    with _cache_lock:
        return _load_cache()


def refresh_email_summary():
    """
    Recupera le email recenti via IMAP, le fa riassumere dall'LLM, e aggiorna
    la cache. Va chiamata sia periodicamente in background (refresh_loop) sia
    su richiesta esplicita dell'utente (pulsante "Aggiorna" nel widget).
    Restituisce la cache aggiornata.
    """
    emails, error = email_service.fetch_recent_emails()

    with _cache_lock:
        cache = _load_cache()
        cache["updated_at"] = datetime.now().isoformat()

        if error == "not_configured":
            cache["status"] = "not_configured"
            cache["error"] = None
            _save_cache(cache)
            return cache

        if error:
            cache["status"] = "error"
            cache["error"] = error
            _save_cache(cache)
            return cache

        if not emails:
            cache["status"] = "empty"
            cache["error"] = None
            cache["emails"] = []
            _save_cache(cache)
            return cache

        prompt = _build_prompt(emails)
        raw_reply = llm.ask_llm_raw(SYSTEM_PROMPT_EMAIL, prompt)

        summaries_by_index = {}
        if raw_reply:
            parsed = _parse_llm_json(raw_reply)
            if parsed:
                for item in parsed:
                    idx = item.get("index")
                    if isinstance(idx, int):
                        summaries_by_index[idx] = item

        enriched = []
        for i, e in enumerate(emails):
            s = summaries_by_index.get(i, {})
            enriched.append({
                "sender": e["sender"],
                "subject": e["subject"],
                "date": e["date"],
                "summary": s.get("summary") or e["snippet"][:100] or "(nessuna anteprima disponibile)",
                "key_info": s.get("key_info", ""),
                "urgency": s.get("urgency", "media"),
            })

        cache["status"] = "ok" if summaries_by_index else "ok_no_summary"
        cache["error"] = None
        cache["emails"] = enriched
        _save_cache(cache)
        return cache


def refresh_loop():
    """Ricontrolla la posta periodicamente, secondo l'intervallo configurato (refresh_minutes)."""
    while True:
        cfg = email_service.load_email_config()
        minutes = cfg.get("refresh_minutes", 10)
        if cfg.get("enabled"):
            try:
                refresh_email_summary()
            except Exception as e:
                print(f"Errore aggiornamento analisi email: {e}")
        time.sleep(max(60, minutes * 60))
