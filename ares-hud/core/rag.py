"""
Context Injection (RAG locale): permette ad Ares di leggere file locali
(PDF, TXT, Markdown) messi nella cartella knowledge/ e di recuperarne i
frammenti più rilevanti per arricchire le risposte dell'LLM.

IMPORTANTE sulla privacy: la ricerca nei documenti avviene interamente in
locale (nessun documento intero viene mai inviato altrove). Solo quando Ares
usa l'LLM cloud (Gemini) per rispondere a una domanda, i pochi frammenti di
testo trovati rilevanti per QUELLA domanda specifica vengono inclusi nella
richiesta inviata a Gemini insieme alla domanda stessa — non l'intero
database di documenti.
"""
import os
import re

from config import KNOWLEDGE_DIR

try:
    from pypdf import PdfReader
    _PDF_SUPPORT = True
except ImportError:
    _PDF_SUPPORT = False

_CHUNK_SIZE = 700  # caratteri per frammento, un compromesso tra contesto e rumore

# Cache dei frammenti già estratti, invalidata quando la cartella cambia
# (nuovo file, file modificato o rimosso), controllato tramite _folder_signature().
_cache = {"signature": None, "chunks": []}


def _read_txt_like(path):
    try:
        with open(path, "r", encoding="utf-8", errors="ignore") as f:
            return f.read()
    except Exception as e:
        print(f"Errore lettura {path}: {e}")
        return ""


def _read_pdf(path):
    if not _PDF_SUPPORT:
        print(f"pypdf non installato: salto {path}. Installa con: pip3 install pypdf --break-system-packages")
        return ""
    try:
        reader = PdfReader(path)
        return "\n".join((page.extract_text() or "") for page in reader.pages)
    except Exception as e:
        print(f"Errore lettura PDF {path}: {e}")
        return ""


def _chunk_text(text, source):
    text = re.sub(r'\s+', ' ', text).strip()
    chunks = []
    for i in range(0, len(text), _CHUNK_SIZE):
        piece = text[i:i + _CHUNK_SIZE].strip()
        if piece:
            chunks.append({"source": source, "text": piece})
    return chunks


def _folder_signature():
    """Firma leggera (nome file + data modifica) per capire se serve ricaricare i documenti."""
    if not os.path.isdir(KNOWLEDGE_DIR):
        return None
    entries = []
    for name in sorted(os.listdir(KNOWLEDGE_DIR)):
        path = os.path.join(KNOWLEDGE_DIR, name)
        if os.path.isfile(path):
            entries.append((name, os.path.getmtime(path)))
    return tuple(entries)


def _load_documents():
    """Rilegge tutti i documenti supportati nella cartella knowledge/ e li suddivide in frammenti."""
    if not os.path.isdir(KNOWLEDGE_DIR):
        try:
            os.makedirs(KNOWLEDGE_DIR, exist_ok=True)
        except Exception as e:
            print(f"Errore creazione cartella knowledge: {e}")
        return []

    chunks = []
    for name in sorted(os.listdir(KNOWLEDGE_DIR)):
        path = os.path.join(KNOWLEDGE_DIR, name)
        if not os.path.isfile(path):
            continue
        lower = name.lower()
        if lower == 'readme.md':
            continue  # istruzioni per l'utente, non contenuto da indicizzare
        if lower.endswith(('.txt', '.md')):
            text = _read_txt_like(path)
        elif lower.endswith('.pdf'):
            text = _read_pdf(path)
        else:
            continue
        chunks.extend(_chunk_text(text, name))
    return chunks


def _ensure_fresh():
    signature = _folder_signature()
    if signature != _cache["signature"]:
        _cache["chunks"] = _load_documents()
        _cache["signature"] = signature


def search_knowledge(query, top_k=3):
    """
    Cerca nei documenti locali i frammenti più rilevanti per la query, con un
    punteggio semplice a conteggio di parole chiave (nessuna libreria di
    embedding pesante: resta leggero e comprensibile).
    """
    _ensure_fresh()
    if not _cache["chunks"]:
        return []

    words = [w for w in re.findall(r'\w+', query.lower()) if len(w) > 2]
    if not words:
        return []

    scored = []
    for chunk in _cache["chunks"]:
        text_lower = chunk["text"].lower()
        score = sum(text_lower.count(w) for w in words)
        if score > 0:
            scored.append((score, chunk))

    scored.sort(key=lambda x: x[0], reverse=True)
    return [c for _, c in scored[:top_k]]


def build_context_for_query(message, max_chars=1500):
    """Restituisce una stringa di contesto dai documenti locali rilevanti, oppure '' se nessuno lo è."""
    chunks = search_knowledge(message, top_k=3)
    if not chunks:
        return ""
    parts = [f"[{c['source']}] {c['text']}" for c in chunks]
    context = "\n\n".join(parts)
    return context[:max_chars]
