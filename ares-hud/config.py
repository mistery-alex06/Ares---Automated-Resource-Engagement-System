import os
import platform

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

CITY_FILE = os.path.join(BASE_DIR, 'city.txt')
VOICE_CONFIG_FILE = os.path.join(BASE_DIR, 'voice_config.json')
LLM_CONFIG_FILE = os.path.join(BASE_DIR, 'llm_config.json')
LLM_USAGE_FILE = os.path.join(BASE_DIR, 'llm_usage.json')
REMINDERS_FILE = os.path.join(BASE_DIR, 'reminders.json')
EMAIL_CONFIG_FILE = os.path.join(BASE_DIR, 'email_config.json')
EMAIL_CACHE_FILE = os.path.join(BASE_DIR, 'email_cache.json')
MEMORY_DB_FILE = os.path.join(BASE_DIR, 'ares_memory.db')
KNOWLEDGE_DIR = os.path.join(BASE_DIR, 'knowledge')

IS_MAC = platform.system() == 'Darwin'
