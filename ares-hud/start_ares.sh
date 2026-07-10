#!/bin/bash
# Script di avvio automatico di Ares
# - termina eventuali vecchi processi Python appesi sulla porta 5001
# - riavvia il server pulito
# - apre la dashboard in Chrome

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$PROJECT_DIR" || exit 1

# Termina qualsiasi processo già in ascolto sulla porta 5001
OLD_PIDS=$(lsof -ti :5001)
if [ -n "$OLD_PIDS" ]; then
    kill -9 $OLD_PIDS
    sleep 1
fi

# Avvia il server in background, log su file per debug
nohup python3 server.py > server.log 2>&1 &

# Piccola attesa per dare tempo a Flask di partire
sleep 2

# Apre la dashboard in Chrome
open -a "Google Chrome" "$PROJECT_DIR/index.html"
