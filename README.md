Ares - Automated Resource Engagement System

Panoramica
Ares (Automated Resource Engagement System) è
una dashboard operativa di nuova generazione, progettata per il monitoraggio in tempo reale delle prestazioni di sistema, l'analisi ambientale e l'interazione con motori di Intelligenza Artificiale.   
Con un'estetica ispirata alle interfacce HUD (Heads-Up Display) fantascientifiche, Ares trasforma dati grezzi in informazioni azionabili per l'utente, mantenendo il controllo completo su risorse hardware e flussi di rete.


Funzionalità Principali

1. Monitoraggio Stato Sistema
- Carico CPU/GPU: Monitoraggio in tempo reale del carico computazionale.
- Utilizzo Memoria: Visualizzazione dinamica del consumo di RAM.
- Archiviazione SSD: Controllo dello spazio su disco principale (Totale, Usato, Libero) per una gestione ottimale dei dati.

2. Analisi Meteo e Ambiente
- Dati Locali: Aggiornamenti meteo in tempo reale (temperatura, condizioni atmosferiche, umidità e velocità del vento) per la posizione corrente (es. Milano).

3. Networking e Connettività
- Flusso di Rete: Monitoraggio del throughput di rete in tempo reale (Download MB/s) per analizzare picchi di traffico e latenze.

4. Integrazione API (Motori AI)
- Gestione Provider: Interfaccia dedicata per la gestione di diverse API (Gemini, Groq, OpenRouter, Cerebras, Fireworks AI).
- Controllo Token: Monitoraggio del consumo dei token per ogni chiamata, garantendo una gestione economica ed efficiente dei prompt.

5. Interazione Intelligente
- Comandi Ares: Un terminale di input integrato che permette di interrogare il sistema (es. "com'è il meteo a Milano?") o interagire con le AI collegate tramite un workflow automatizzato.

Layout Personalizzabile
Ares offre una gestione modulare dei componenti grazie al supporto per layout drag-and-drop.   
È possibile personalizzare la posizione di ogni widget in base alle proprie esigenze di workflow, con una funzione di "Reset Layout" che ripristina la configurazione predefinita in caso di necessità.

---------------------------------------------------------------------------------------------------------------------------

### Configurazione API e Servizi
Per utilizzare le funzionalità avanzate di Ares, è necessario configurare i file di configurazione nella directory principale.   
Per motivi di sicurezza, questi file non sono inclusi nel repository:

1. Configurazione AI (`llm_config.json`)
Questo file contiene le credenziali per i vari provider AI.
```json
{
  "gemini_api_key": "LA_TUA_CHIAVE_API",
  "groq_api_key": "LA_TUA_CHIAVE_API",
  "openrouter_api_key": "LA_TUA_CHIAVE_API",
  "cerebras_api_key": "LA_TUA_CHIAVE_API",
  "fireworks_ai_api_key": "LA_TUA_CHIAVE_API"
}
```
2. Configurazione Email (email_config.json).   
Questo file è necessario per consentire ad Ares di accedere al tuo account e gestire i flussi di posta elettronica.
```json
{
  "email_address": "tuo.indirizzo@email.com",
  "app_password": "LA_TUA_PASSWORD_SPECIFICA_PER_APP",
  "imap_server": "imap.tuoprovider.com"
}
```
