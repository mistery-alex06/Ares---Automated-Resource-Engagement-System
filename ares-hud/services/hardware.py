"""
Servizio hardware: lettura di CPU, RAM, GPU e disco. Nessuna logica di business
qui dentro, solo dati grezzi dal sistema operativo.
"""
import os
import re
import subprocess
import threading

import psutil

from config import IS_MAC

# Inizializza il contatore interno di psutil (la prima chiamata è sempre 0.0)
psutil.cpu_percent(interval=None)


def get_cpu_percent():
    # interval=0.3 blocca per 300ms e misura il carico reale in quella finestra,
    # invece di fare la media (spesso imprecisa) dal tempo trascorso dall'ultima chiamata.
    return psutil.cpu_percent(interval=0.3)


def get_ram_percent():
    """
    Replica il calcolo di Activity Monitor: Wired + App Memory (active) + Compressa,
    escludendo la memoria 'inactive' che macOS tiene solo come cache e libera all'istante
    se serve. psutil.virtual_memory().percent invece conta anche quella, gonfiando il valore.
    """
    if not IS_MAC:
        return psutil.virtual_memory().percent

    try:
        out = subprocess.check_output(['vm_stat'], text=True, timeout=2)
        page_size_match = re.search(r'page size of (\d+) bytes', out)
        page_size = int(page_size_match.group(1)) if page_size_match else 4096

        def pages(label):
            m = re.search(rf'{label}:\s+(\d+)\.', out)
            return int(m.group(1)) if m else 0

        wired = pages('Pages wired down')
        active = pages('Pages active')
        compressed = pages('Pages occupied by compressor')

        used_bytes = (wired + active + compressed) * page_size
        total_bytes = psutil.virtual_memory().total

        return round((used_bytes / total_bytes) * 100, 1)
    except Exception as e:
        print(f"Errore lettura RAM (vm_stat): {e}")
        return psutil.virtual_memory().percent


# --- GPU: lettura in background via powermetrics (richiede sudo, vedi note sotto) ---
_gpu_state = {"percent": None}
_gpu_lock = threading.Lock()


def gpu_reader_loop():
    if not IS_MAC:
        return
    try:
        proc = subprocess.Popen(
            ['sudo', 'powermetrics', '--samplers', 'gpu_power', '-i', '1000'],
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
        )
    except FileNotFoundError:
        print("powermetrics non trovato: la GPU resterà N/D")
        return

    buffer_values = []
    # Formati diversi a seconda del chip/macOS: alcuni riportano "Active Residency",
    # altri (come le GPU Intel integrate) riportano "GPU Busy". Cerchiamo entrambi.
    pattern = re.compile(r'(?:Active Residency|GPU\s*Busy)\s*:\s*([\d.]+)%', re.IGNORECASE)
    for line in proc.stdout:
        m = pattern.search(line)
        if m:
            buffer_values.append(float(m.group(1)))
        # powermetrics stampa un blocco per campione separato da una riga di intestazione;
        # quando arriva la prossima intestazione "***", chiudiamo il campione corrente.
        if line.startswith('***') and buffer_values:
            with _gpu_lock:
                _gpu_state["percent"] = max(buffer_values)
            buffer_values = []


def get_gpu_percent():
    with _gpu_lock:
        return _gpu_state["percent"]  # None se non disponibile


def disk_info():
    # Legge il volume "Dati" (dove vivono i tuoi file) invece di "/", che su macOS
    # moderno è spesso un volume di sistema separato e può dare numeri fuorvianti.
    path = os.path.expanduser('~')
    usage = psutil.disk_usage(path)
    return {
        "percent": usage.percent,
        "total": f"{usage.total / (1024 ** 3):.0f} GB",
        "used": f"{usage.used / (1024 ** 3):.0f} GB",
        "free": f"{usage.free / (1024 ** 3):.0f} GB",
    }
