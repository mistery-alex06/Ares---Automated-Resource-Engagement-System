"""
Servizio meteo: geocoding e previsioni correnti via Open-Meteo, più la cache in
memoria e la persistenza della città attiva su city.txt.
"""
import threading
import time

import requests

from config import CITY_FILE

WEATHER_CODES = {
    0: ("Sereno", "☀️"),
    1: ("Prevalentemente sereno", "🌤️"),
    2: ("Parzialmente nuvoloso", "⛅"),
    3: ("Nuvoloso", "☁️"),
    45: ("Nebbia", "🌫️"),
    48: ("Nebbia con brina", "🌫️"),
    51: ("Pioggerella leggera", "🌦️"),
    53: ("Pioggerella moderata", "🌦️"),
    55: ("Pioggerella intensa", "🌧️"),
    56: ("Pioggerella gelata leggera", "🌧️"),
    57: ("Pioggerella gelata intensa", "🌧️"),
    61: ("Pioggia leggera", "🌧️"),
    63: ("Pioggia moderata", "🌧️"),
    65: ("Pioggia intensa", "🌧️"),
    66: ("Pioggia gelata leggera", "🌧️"),
    67: ("Pioggia gelata intensa", "🌧️"),
    71: ("Nevicata leggera", "🌨️"),
    73: ("Nevicata moderata", "🌨️"),
    75: ("Nevicata intensa", "❄️"),
    77: ("Granelli di neve", "❄️"),
    80: ("Rovesci leggeri", "🌦️"),
    81: ("Rovesci moderati", "🌧️"),
    82: ("Rovesci violenti", "⛈️"),
    85: ("Rovesci di neve leggeri", "🌨️"),
    86: ("Rovesci di neve intensi", "❄️"),
    95: ("Temporale", "⛈️"),
    96: ("Temporale con grandine leggera", "⛈️"),
    99: ("Temporale con grandine intensa", "⛈️"),
}

_WEATHER_CACHE = {"data": {
    "city": "In attesa...",
    "temp": "N/D",
    "icon": "❔",
    "condition": "N/D",
    "humidity": "N/D",
    "windSpeed": "N/D",
}}
_current_city_query = "Roma"
_weather_lock = threading.Lock()


def geocode(city_query):
    try:
        resp = requests.get(
            "https://geocoding-api.open-meteo.com/v1/search",
            params={"name": city_query, "count": 8, "language": "it", "format": "json"},
            timeout=6,
        )
        resp.raise_for_status()
        results = resp.json().get("results")
        if not results:
            return None

        query_lower = city_query.strip().lower()
        candidates = [r for r in results if r.get("name", "").lower().startswith(query_lower)]
        if not candidates:
            candidates = results

        candidates.sort(key=lambda r: r.get("population") or 0, reverse=True)
        best = candidates[0]

        return {
            "name": best["name"],
            "latitude": best["latitude"],
            "longitude": best["longitude"],
        }
    except Exception as e:
        print(f"Errore geocoding: {e}")
        return None


def fetch_weather_for_city(city_query):
    location = geocode(city_query)
    if not location:
        return None

    try:
        resp = requests.get(
            "https://api.open-meteo.com/v1/forecast",
            params={
                "latitude": location["latitude"],
                "longitude": location["longitude"],
                "current": "temperature_2m,relative_humidity_2m,wind_speed_10m,weather_code",
                "timezone": "auto",
            },
            timeout=6,
        )
        resp.raise_for_status()
        current = resp.json().get("current", {})

        code = current.get("weather_code")
        condition, icon = WEATHER_CODES.get(code, ("N/D", "❔"))

        temp = current.get("temperature_2m")
        wind = current.get("wind_speed_10m")

        return {
            "city": location["name"],
            "temp": round(temp) if temp is not None else "N/D",
            "icon": icon,
            "condition": condition,
            "humidity": current.get("relative_humidity_2m", "N/D"),
            "windSpeed": round(wind) if wind is not None else "N/D",
        }
    except Exception as e:
        print(f"Errore meteo: {e}")
        return None


def get_cached_weather():
    with _weather_lock:
        return _WEATHER_CACHE["data"]


def get_current_city_query():
    with _weather_lock:
        return _current_city_query


def _update_cache_only(weather):
    global _current_city_query
    with _weather_lock:
        _current_city_query = weather["city"]
        _WEATHER_CACHE["data"] = weather


def set_active_city(weather):
    """Aggiorna la cache in memoria E persiste la nuova città su city.txt."""
    _update_cache_only(weather)
    _save_city_to_file(weather["city"])


def refresh_weather_loop():
    while True:
        time.sleep(600)
        data = fetch_weather_for_city(get_current_city_query())
        if data:
            _update_cache_only(data)


def load_initial_city():
    global _current_city_query
    try:
        with open(CITY_FILE, "r", encoding="utf-8") as f:
            saved = f.read().strip()
            if saved:
                _current_city_query = saved
    except FileNotFoundError:
        pass


def _save_city_to_file(city_name):
    try:
        with open(CITY_FILE, "w", encoding="utf-8") as f:
            f.write(city_name)
    except Exception as e:
        print(f"Errore salvataggio città: {e}")
