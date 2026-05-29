# telegram-location-scraper

**telegram-location-scraper** è uno strumento automatizzato basato sull'Intelligenza Artificiale che estrae, categorizza e mappa le destinazioni di viaggio partendo da Reel di Instagram e messaggi Telegram. Sfrutta l'analisi video e l'estrazione intelligente del testo (OCR) per individuare luoghi turistici e posizionarli su mappa.

*Nota: Questo progetto, la sua struttura e documentazione sono stati sviluppati attivamente con il supporto di sistemi di Intelligenza Artificiale generativa.*

## Funzionalità principali
- **Importazione Automatica**: Raccoglie link o video direttamente da Telegram o Instagram.
- **OCR Avanzato**: Legge il testo in sovrimpressione dai video tramite `EasyOCR`.
- **Estrazione AI**: Utilizza modelli di Intelligenza Artificiale per comprendere e isolare il nome esatto della località e del Paese.
- **Categorizzazione**: Suddivide i luoghi in categorie tematiche (Ristoranti, Punti Panoramici, Musei, ecc.).
- **Geolocalizzazione**: Ricava coordinate e indirizzi completi tramite API di mapping.

---

## Installazione

1. **Clona** la repository nel tuo ambiente locale.
2. Assicurati di avere **Python 3.9+** installato.
3. Installa e avvia **[Ollama](https://ollama.com/)** per la componente di Intelligenza Artificiale locale.
   Al momento, il progetto utilizza di default il modello `qwen2.5:7b-instruct` oppure `qwen2.5:14b` . Assicurati di scaricarlo:
   ```bash
   ollama run qwen2.5:7b-instruct
   ```
4. Installa le dipendenze richieste eseguendo:
   ```bash
   pip install -r requirements.txt
   ```
5. **Configurazione Variabili d'Ambiente**:
   Crea un file `.env` nella cartella principale e inserisci le tue chiavi API (es. credenziali di Telegram `API_ID` e `API_HASH`, le API per l'AI e i servizi mappe).

---

## Tutorial di Funzionamento (Quick Start)

Per avviare il flusso di elaborazione, apri il terminale e lancia lo script principale:

```bash
python main.py
```

## Avvio con Docker

Per avviare i tre servizi separati in container usa:

```bash
docker compose up --build
```

Servizi inclusi:
- `api`: espone FastAPI su `http://localhost:8000`
- `main`: worker che processa i messaggi nel database
- `telegram`: importer Telegram che popola il database dai topic configurati

Il servizio `telegram` usa la sessione `telegram_session.session` montata dal progetto e legge le credenziali dal file `.env`.

### Come funziona il processo:
1. **Autenticazione Scanner**: Al primo avvio, se il modulo Telegram è attivo, ti verrà richiesto il numero di telefono e un codice di verifica per creare la sessione (verranno salvati nel file _telegram_session.session_).
2. **Scraping dei Video**: Il bot legge gli ultimi messaggi per trovare contenuti rilevanti da Reel o Shorts. I video vengono scaricati temporaneamente (e.g. con _yt-dlp_).
3. **Analisi Visiva**: Sfruttando `cv2` (OpenCV) e l'OCR, vengono estratti i fotogrammi e letto il testo che compare a schermo.
4. **Riconoscimento dell'Intelligenza Artificiale (AI)**: L'estratto testuale passa dal modulo AI che riconosce se si sta parlando di una località, e in quel caso lo associa a coordinate GPS e indirizzi.
5. **Salvataggio su DB**: Tutte le informazioni processate vengono normalizzate dal modello (_SQLModel/Pydantic_) e archiviate nel database integrato, pronte per essere mostrate su una mappa!

---

_Nota: Assicurati di verificare le norme sul copyright e la validità legale dello scraping sulle piattaforme di origine nel momento dell'uso in produzione._
