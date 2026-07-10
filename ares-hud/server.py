"""
Ares — entry point. Questo file contiene solo l'app Flask, le route HTTP e il
bootstrap all'avvio. Tutta la logica vive nei moduli:
  - config.py      percorsi condivisi
  - services/      hardware, meteo, voce, notifiche (dati grezzi/integrazioni di sistema)
  - tools/         browser, whatsapp, promemoria (azioni esterne)
  - core/          skills (motore di comandi), llm (Gemini), memory (storico), rag (documenti locali)
"""
import base64
import threading

from flask import Flask, jsonify, request
from flask_cors import CORS

from core import email_analysis, llm, memory, skills
from services import hardware, voice, weather
from tools import reminders

app = Flask(__name__)
CORS(app)


@app.route('/api/data')
def get_data():
    return jsonify({
        "hardware": {
            "cpu": hardware.get_cpu_percent(),
            "ram": hardware.get_ram_percent(),
            "gpu": hardware.get_gpu_percent(),
            "disk": hardware.disk_info(),
        },
        "weather": weather.get_cached_weather(),
    })


@app.route('/api/update_city', methods=['POST'])
def update_city():
    data = request.json or {}
    raw_city = data.get('city', '').strip()

    if not raw_city:
        return jsonify({"status": "error", "message": "Nome città mancante"}), 400

    new_weather = weather.fetch_weather_for_city(raw_city)
    if new_weather:
        weather.set_active_city(new_weather)
        return jsonify({"status": "success", "weather": new_weather})

    return jsonify({"status": "error", "message": "Città non trovata"}), 404


@app.route('/api/chat', methods=['POST'])
def chat():
    data = request.json or {}
    message = data.get('message', '').strip()

    if not message:
        return jsonify({"status": "error", "message": "Messaggio vuoto"}), 400

    reply, weather_data = skills.handle_chat_message(message)

    audio_b64 = None
    audio_bytes = voice.synthesize_speech(reply)
    if audio_bytes:
        audio_b64 = base64.b64encode(audio_bytes).decode('utf-8')

    return jsonify({
        "status": "success",
        "reply": reply,
        "weather": weather_data,
        "audio": audio_b64,  # None se la voce non è configurata in voice_config.json
    })


@app.route('/api/reminders')
def get_reminders():
    return jsonify({"status": "success", "reminders": reminders.list_pending()})


@app.route('/api/llm_usage')
def get_llm_usage():
    return jsonify({"status": "success", "providers": llm.get_usage_dashboard()})


@app.route('/api/llm_usage/toggle', methods=['POST'])
def toggle_llm_provider():
    data = request.json or {}
    name = data.get('name')
    enabled = data.get('enabled')

    if name is None or enabled is None:
        return jsonify({"status": "error", "message": "Parametri mancanti"}), 400

    if not llm.set_provider_enabled(name, bool(enabled)):
        return jsonify({"status": "error", "message": "Provider non trovato"}), 404

    return jsonify({"status": "success", "providers": llm.get_usage_dashboard()})


@app.route('/api/email_summary')
def get_email_summary():
    return jsonify(email_analysis.get_cached_summary())


@app.route('/api/email_summary/refresh', methods=['POST'])
def refresh_email_summary_route():
    return jsonify(email_analysis.refresh_email_summary())


if __name__ == '__main__':
    weather.load_initial_city()
    reminders.load_reminders()
    memory.init_db()

    initial_weather = weather.fetch_weather_for_city(weather.get_current_city_query())
    if initial_weather:
        weather.set_active_city(initial_weather)

    threading.Thread(target=weather.refresh_weather_loop, daemon=True).start()
    threading.Thread(target=hardware.gpu_reader_loop, daemon=True).start()
    threading.Thread(target=reminders.reminder_loop, daemon=True).start()
    threading.Thread(target=email_analysis.refresh_loop, daemon=True).start()

    app.run(debug=True, port=5001, use_reloader=False)
