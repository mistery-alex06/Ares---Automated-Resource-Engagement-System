"""
Sistema di memoria: mantiene lo storico delle interazioni utente <-> Ares in un
database SQLite locale (ares_memory.db), così Ares può recuperare il contesto
delle conversazioni recenti quando risponde tramite l'LLM cloud.
"""
import sqlite3
from datetime import datetime

from config import MEMORY_DB_FILE


def init_db():
    """Crea la tabella delle interazioni se non esiste già. Va chiamata all'avvio."""
    try:
        conn = sqlite3.connect(MEMORY_DB_FILE)
        conn.execute('''
            CREATE TABLE IF NOT EXISTS interactions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                user_message TEXT NOT NULL,
                ares_reply TEXT NOT NULL
            )
        ''')
        conn.commit()
        conn.close()
    except Exception as e:
        print(f"Errore inizializzazione database memoria: {e}")


def save_interaction(user_message, ares_reply):
    """Salva uno scambio (messaggio utente + risposta di Ares) nello storico."""
    try:
        conn = sqlite3.connect(MEMORY_DB_FILE)
        conn.execute(
            "INSERT INTO interactions (timestamp, user_message, ares_reply) VALUES (?, ?, ?)",
            (datetime.now().isoformat(), user_message, ares_reply),
        )
        conn.commit()
        conn.close()
    except Exception as e:
        print(f"Errore salvataggio memoria: {e}")


def get_recent_history(limit=6):
    """
    Restituisce le ultime `limit` coppie (messaggio_utente, risposta_ares),
    in ordine cronologico (dalla più vecchia alla più recente), utili come
    contesto di conversazione per l'LLM.
    """
    try:
        conn = sqlite3.connect(MEMORY_DB_FILE)
        cur = conn.execute(
            "SELECT user_message, ares_reply FROM interactions ORDER BY id DESC LIMIT ?",
            (limit,),
        )
        rows = cur.fetchall()
        conn.close()
        return list(reversed(rows))
    except Exception as e:
        print(f"Errore lettura memoria: {e}")
        return []
