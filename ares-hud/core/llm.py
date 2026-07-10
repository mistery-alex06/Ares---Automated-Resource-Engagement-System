"""
LLM cloud multi-provider: catena di fallback fra diversi provider LLM, con
tracciamento dell'utilizzo di ciascuno (per il widget "UTILIZZO API" nell'HUD).

Espone due funzioni per il resto del codice:
  - ask_llm_fallback(message)              per la chat di Ares (con memoria + RAG)
  - ask_llm_raw(system_prompt, content)     per usi generici (es. analisi email),
                                            senza cronologia né documenti locali

Entrambe passano dalla stessa catena di fallback (_run_chain) e dallo stesso
tracciamento di utilizzo, quindi ogni chiamata — chat o analisi email che sia —
compare nel widget "UTILIZZO API".

Ogni provider ha un "type":
  - "gemini"        per Google AI Studio (formato di richiesta proprietario)
  - "openai_compat" per qualunque provider con endpoint /chat/completions in
                     stile OpenAI (Groq, OpenRouter, Cerebras, Fireworks, NVIDIA
                     NIM, ecc.) — un'unica funzione li gestisce tutti.
"""
import json
import threading
from datetime import datetime

import requests

from config import LLM_CONFIG_FILE, LLM_USAGE_FILE
from core import memory, rag

# Ordine di fallback di default. Le chiavi vanno compilate in llm_config.json
# (creato automaticamente al primo avvio) — quelle vuote vengono saltate.
DEFAULT_PROVIDERS = [
    {"name": "gemini", "label": "Gemini (Google)", "type": "gemini", "api_key": "",
     "model": "gemini-2.5-flash", "enabled": True},
    {"name": "groq", "label": "Groq", "type": "openai_compat", "base_url": "https://api.groq.com/openai/v1",
     "api_key": "", "model": "openai/gpt-oss-120b", "enabled": True},
    {"name": "openrouter", "label": "OpenRouter", "type": "openai_compat", "base_url": "https://openrouter.ai/api/v1",
     "api_key": "", "model": "openrouter/free", "enabled": True},
    {"name": "cerebras", "label": "Cerebras", "type": "openai_compat", "base_url": "https://api.cerebras.ai/v1",
     "api_key": "", "model": "llama-4-scout", "enabled": True},
    {"name": "fireworks", "label": "Fireworks AI", "type": "openai_compat", "base_url": "https://api.fireworks.ai/inference/v1",
     "api_key": "", "model": "accounts/fireworks/models/llama-v3p3-70b-instruct", "enabled": True},
    {"name": "nvidia", "label": "NVIDIA NIM", "type": "openai_compat", "base_url": "https://integrate.api.nvidia.com/v1",
     "api_key": "", "model": "meta/llama-3.3-70b-instruct", "enabled": True},
]

SYSTEM_PROMPT_ARES = (
    "Sei Ares, un assistente vocale locale che vive in un HUD sul Mac dell'utente. "
    "Rispondi sempre in italiano, in modo breve e diretto (massimo 2-3 frasi), come farebbe "
    "un assistente vocale. Se ti viene chiesta un'informazione che richiede dati aggiornati "
    "in tempo reale (notizie, prezzi, risultati sportivi, orari di eventi attuali) dillo "
    "onestamente invece di inventare una risposta. Se ricevi del \"Contesto dai documenti "
    "locali dell'utente\", usalo per rispondere in modo pertinente al suo lavoro, citando "
    "brevemente da quale file viene l'informazione quando è utile."
)


def _load_llm_config():
    """
    Legge la configurazione multi-provider da llm_config.json. Se il file non
    esiste ne crea uno di default. Se esiste ma è nel vecchio formato a
    provider singolo, lo migra automaticamente preservando la chiave già presente.
    Aggiunge inoltre "enabled": True/"label" ai provider di config preesistenti
    che ne fossero privi (retrocompatibilità).
    """
    default_cfg = {"enabled": True, "timeout_seconds": 15, "providers": DEFAULT_PROVIDERS}
    try:
        with open(LLM_CONFIG_FILE, "r", encoding="utf-8") as f:
            cfg = json.load(f)
    except FileNotFoundError:
        try:
            with open(LLM_CONFIG_FILE, "w", encoding="utf-8") as f:
                json.dump(default_cfg, f, indent=2)
        except Exception as e:
            print(f"Errore creazione llm_config.json: {e}")
        return default_cfg
    except Exception as e:
        print(f"Errore lettura llm_config.json: {e}")
        return default_cfg

    changed = False
    if "providers" not in cfg:
        old_key = cfg.get("api_key", "")
        providers = [dict(p) for p in DEFAULT_PROVIDERS]
        if old_key:
            providers[0]["api_key"] = old_key
        cfg = {
            "enabled": cfg.get("enabled", True),
            "timeout_seconds": cfg.get("timeout_seconds", 15),
            "providers": providers,
        }
        changed = True
    else:
        defaults_by_name = {p["name"]: p for p in DEFAULT_PROVIDERS}
        for p in cfg["providers"]:
            defaults = defaults_by_name.get(p.get("name"), {})
            if "enabled" not in p:
                p["enabled"] = True
                changed = True
            if "label" not in p:
                p["label"] = defaults.get("label", p.get("name", "?").capitalize())
                changed = True

    if changed:
        try:
            with open(LLM_CONFIG_FILE, "w", encoding="utf-8") as f:
                json.dump(cfg, f, indent=2)
        except Exception as e:
            print(f"Errore salvataggio llm_config.json: {e}")

    return {**default_cfg, **cfg}


LLM_CONFIG = _load_llm_config()

# ═══════════════════════════════════════════════════════════
#  UTILIZZO — tracciamento per il widget "UTILIZZO API"
# ═══════════════════════════════════════════════════════════

_usage_lock = threading.Lock()


def _empty_usage_entry():
    return {
        "calls_total": 0,
        "calls_success": 0,
        "calls_failed": 0,
        "tokens_total": 0,
        "last_used": None,
        "last_status": None,
        "last_error": None,
    }


def _load_usage():
    try:
        with open(LLM_USAGE_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def _save_usage(usage):
    try:
        with open(LLM_USAGE_FILE, "w", encoding="utf-8") as f:
            json.dump(usage, f, indent=2, ensure_ascii=False)
    except Exception as e:
        print(f"Errore salvataggio llm_usage.json: {e}")


def _record_usage(name, success, tokens=None, error=None):
    with _usage_lock:
        usage = _load_usage()
        entry = usage.get(name, _empty_usage_entry())
        entry["calls_total"] += 1
        if success:
            entry["calls_success"] += 1
            entry["last_status"] = "success"
            entry["last_error"] = None
        else:
            entry["calls_failed"] += 1
            entry["last_status"] = "error"
            entry["last_error"] = (error or "")[:200]
        if tokens:
            entry["tokens_total"] += tokens
        entry["last_used"] = datetime.now().isoformat()
        usage[name] = entry
        _save_usage(usage)


def get_usage_dashboard():
    usage = _load_usage()
    dashboard = []
    for provider in LLM_CONFIG.get("providers", []):
        name = provider.get("name", "?")
        entry = usage.get(name, _empty_usage_entry())
        dashboard.append({
            "name": name,
            "label": provider.get("label", name.capitalize()),
            "has_key": bool(provider.get("api_key", "").strip()),
            "enabled": provider.get("enabled", True),
            **entry,
        })
    return dashboard


def set_provider_enabled(name, enabled):
    found = False
    for provider in LLM_CONFIG.get("providers", []):
        if provider.get("name") == name:
            provider["enabled"] = bool(enabled)
            found = True
            break
    if not found:
        return False
    try:
        with open(LLM_CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(LLM_CONFIG, f, indent=2)
    except Exception as e:
        print(f"Errore salvataggio llm_config.json: {e}")
    return True


# ═══════════════════════════════════════════════════════════
#  CHIAMATE AI PROVIDER
# ═══════════════════════════════════════════════════════════

def _call_gemini(provider, system_prompt, user_content, history, timeout):
    """Restituisce (testo_risposta_o_None, token_totali_o_None)."""
    api_key = provider.get("api_key", "").strip()
    if not api_key:
        return None, None

    model = provider.get("model", "gemini-2.5-flash")
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"

    contents = []
    for user_msg, ares_reply in history:
        contents.append({"role": "user", "parts": [{"text": user_msg}]})
        contents.append({"role": "model", "parts": [{"text": ares_reply}]})
    contents.append({"role": "user", "parts": [{"text": user_content}]})

    resp = requests.post(
        url,
        headers={"x-goog-api-key": api_key, "Content-Type": "application/json"},
        json={
            "system_instruction": {"parts": [{"text": system_prompt}]},
            "contents": contents,
        },
        timeout=timeout,
    )
    resp.raise_for_status()
    data = resp.json()
    tokens = data.get("usageMetadata", {}).get("totalTokenCount")
    candidates = data.get("candidates", [])
    if not candidates:
        return None, tokens
    parts = candidates[0].get("content", {}).get("parts", [])
    text = "".join(p.get("text", "") for p in parts).strip()
    return (text or None), tokens


def _call_openai_compat(provider, system_prompt, user_content, history, timeout):
    """
    Gestisce qualunque provider con un endpoint /chat/completions in stile
    OpenAI: Groq, OpenRouter, Cerebras, Fireworks, NVIDIA NIM, ecc.
    Restituisce (testo_risposta_o_None, token_totali_o_None).
    """
    api_key = provider.get("api_key", "").strip()
    if not api_key:
        return None, None

    base_url = provider.get("base_url", "").rstrip('/')
    model = provider.get("model", "")

    messages = [{"role": "system", "content": system_prompt}]
    for user_msg, ares_reply in history:
        messages.append({"role": "user", "content": user_msg})
        messages.append({"role": "assistant", "content": ares_reply})
    messages.append({"role": "user", "content": user_content})

    resp = requests.post(
        f"{base_url}/chat/completions",
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        json={"model": model, "messages": messages, "temperature": 0.7, "max_tokens": 800},
        timeout=timeout,
    )
    resp.raise_for_status()
    data = resp.json()
    tokens = data.get("usage", {}).get("total_tokens")
    content = data["choices"][0]["message"]["content"]
    return (content.strip() if content else None), tokens


_PROVIDER_HANDLERS = {
    "gemini": _call_gemini,
    "openai_compat": _call_openai_compat,
}


def _run_chain(system_prompt, user_content, history=None):
    """
    Prova ogni provider abilitato in ordine, finché uno risponde, registrando
    l'esito (successo/errore, token usati) per il dashboard di utilizzo.
    Usata sia dalla chat di Ares sia da qualunque altro modulo che debba
    interrogare un LLM (es. core.email_analysis).
    """
    if not LLM_CONFIG.get("enabled", True):
        return None

    history = history or []
    timeout = LLM_CONFIG.get("timeout_seconds", 15)

    for provider in LLM_CONFIG.get("providers", []):
        if not provider.get("enabled", True):
            continue
        if not provider.get("api_key", "").strip():
            continue

        handler = _PROVIDER_HANDLERS.get(provider.get("type"))
        if not handler:
            continue

        name = provider.get("name", "?")
        try:
            reply, tokens = handler(provider, system_prompt, user_content, history, timeout)
            if reply:
                _record_usage(name, success=True, tokens=tokens)
                return reply
            _record_usage(name, success=False, error="Risposta vuota dal provider")
        except Exception as e:
            print(f"{name} non disponibile ({e}), provo il prossimo provider.")
            _record_usage(name, success=False, error=str(e))
            continue

    return None


def _build_prompt_context(message):
    """Prepara cronologia + contesto RAG per la chat di Ares."""
    history = memory.get_recent_history(limit=6)
    context = rag.build_context_for_query(message)
    if context:
        final_message = (
            f"Contesto dai documenti locali dell'utente:\n{context}\n\n"
            f"Domanda dell'utente: {message}"
        )
    else:
        final_message = message
    return history, final_message


def ask_llm_fallback(message):
    """
    Interroga la catena di provider per la chat di Ares, arricchita con
    cronologia recente e documenti locali. Restituisce la risposta testuale,
    oppure None se nessun provider è configurato/abilitato o tutti falliscono
    — in quel caso il chiamante (core.skills) ripiega su Google.
    """
    history, final_message = _build_prompt_context(message)
    return _run_chain(SYSTEM_PROMPT_ARES, final_message, history)


def ask_llm_raw(system_prompt, user_content):
    """
    Interroga la stessa catena di provider ma con un system prompt e un
    contenuto arbitrari, senza cronologia né RAG — pensata per usi generici
    come l'analisi email. Restituisce il testo della risposta, o None.
    """
    return _run_chain(system_prompt, user_content, history=[])
