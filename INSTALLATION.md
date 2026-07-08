# INSTALLATION.md — SIMQIN JSON Platform

## Übersicht

Die Plattform besteht aus drei Docker-Services:

| Service | Technologie | Port (Default) | Aufgabe |
|:--------|:------------|:---------------|:--------|
| **API** | FastAPI (Python) | `8080` | REST-Gateway, Dateiannahme |
| **Worker** | FastAPI + lxml | `8090` | XML-Parsing, DTD-Validierung, JSON-Mapping |
| **Frontend** | React + Vite + TypeScript | `5173` | Browser-UI, Upload, Baumansicht |

---

## 1. Voraussetzungen

| Komponente | Min. Version | Prüfen |
|:-----------|:-------------|:-------|
| Docker | 24.x | `docker --version` |
| Docker Compose | 2.24.x | `docker compose version` |
| Git (optional) | beliebig | `git --version` |

> **Windows**: Docker Desktop mit WSL2-Backend wird empfohlen.
> **Linux/macOS**: Docker Engine + Compose-Plugin reichen aus.

---

## 2. Schnellstart (Docker Compose)

### 2.1 Repository klonen

```bash
git clone <repository-url> simqin-json-platform
cd simqin-json-platform
```

### 2.2 Umgebungsvariablen konfigurieren (optional)

```bash
cp .env.example .env
```

Die Standardwerte in `.env.example` sind für lokale Entwicklung ausgelegt.
Anpassbare Werte:

| Variable | Default | Beschreibung |
|:---------|:--------|:-------------|
| `API_PORT` | `8080` | Port des API-Gateways |
| `FRONTEND_PORT` | `5173` | Port des Frontend-Dev-Servers |
| `MAX_UPLOAD_MB` | `25` | Max. Upload-Größe in MB |
| `CORS_ORIGINS` | `["http://localhost:5173"]` | Erlaubte Frontend-Origins (JSON-Array) |
| `WORKER_BASE_URL` | `http://worker:8090` | Interne Worker-URL (nur Docker) |
| `STORAGE_DIR` | `/data/storage` | Temporäres Speicherverzeichnis |

### 2.3 Build & Start

```bash
docker compose up --build
```

Erster Start dauert **2–5 Minuten** (Downloads + Builds).

### 2.4 Verfügbarkeit prüfen

```bash
# API Health
curl http://localhost:8080/health

# Worker Health
curl http://localhost:8090/health

# Frontend im Browser
# → http://localhost:5173
```

### 2.5 Stoppen

```bash
docker compose down
# Mit Volume-Bereinigung:
docker compose down -v
```

---

## 3. Nutzung

### 3.1 Über das Frontend

1. Browser öffnen: **http://localhost:5173**
2. XML-Datei auswählen (z. B. `shared/test-fixtures/example-topic.xml`)
3. Optional DTD-Datei mitladen (z. B. `shared/test-fixtures/example-topic.dtd`)
4. Optional YAML-Mapping-Profil mitladen (z. B. `shared/mappings/simqin-default.yaml`)
5. **»Konvertieren«** klicken
6. Ergebnisse in Tabs erkunden:
   - **Canonical JSON** — interaktiver XML-Baum
   - **Domain JSON** — fachlich normalisiert (mit DITA-Map-Details)
   - **Assets** — extrahierte Bilder/Figures (falls vorhanden)
   - **Referenzen** — extrahierte XRefs/Links (falls vorhanden)
   - **Validierungsreport** — tabellarische DTD-Fehler (Download als JSON/Text)
   - **Schema** — Canonical/Domain JSON Schema laden

### 3.2 Über die REST-API

```bash
# Einfacher Upload
curl -F "file=@shared/test-fixtures/example-topic.xml" \
     -F "dtd=@shared/test-fixtures/example-topic.dtd" \
     http://localhost:8080/api/v1/documents

# Mit benutzerdefiniertem Mapping-Profil
curl -F "file=@shared/test-fixtures/example-topic.xml" \
     -F "mapping=@shared/mappings/simqin-default.yaml" \
     http://localhost:8080/api/v1/documents

# DITA Map verarbeiten
curl -F "file=@shared/test-fixtures/example-ditamap.ditamap" \
     http://localhost:8080/api/v1/documents

# Schema abrufen
curl http://localhost:8080/api/v1/schemas/canonical
curl http://localhost:8080/api/v1/schemas/domain
```

API-Dokumentation (Swagger UI): **http://localhost:8080/docs**

---

## 4. Entwicklung ohne Docker

### 4.1 Worker + API (Python)

**Voraussetzungen:** Python 3.12, virtualenv (optional)

```bash
# Worker
cd services/worker
python -m venv .venv
.venv\Scripts\activate   # Windows
source .venv/bin/activate  # Linux/macOS
pip install -r requirements.txt
uvicorn app.main:app --port 8090 --reload
```

```bash
# API (zweites Terminal)
cd services/api
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
uvicorn app.main:app --port 8080 --reload
```

> **Hinweis:** `WORKER_BASE_URL` muss auf `http://localhost:8090` zeigen (Standard).

### 4.2 Frontend (Node.js)

**Voraussetzungen:** Node.js 22.x

```bash
cd frontend
npm install
npm run dev -- --host
```

Der Dev-Server startet auf **http://localhost:5173** mit Hot-Module-Reload.

### 4.3 Tests ausführen (Worker)

```bash
cd services/worker
pip install -r requirements.txt   # enthält pytest
pytest tests/ -v
```

Aktuell: **30 Tests, alle grün.**

---

## 5. Projektstruktur (relevant für Installation)

```text
simqin-json-platform/
├── docker-compose.yml          # Orchestrierung
├── .env.example                # Umgebungsvariablen (Vorlage)
├── .env                        # Umgebungsvariablen (aktiv, nicht in Git)
│
├── services/
│   ├── api/                    # FastAPI Gateway
│   │   ├── Dockerfile
│   │   ├── requirements.txt
│   │   └── app/main.py
│   │
│   └── worker/                 # Parser + Mapper
│       ├── Dockerfile
│       ├── requirements.txt
│       ├── setup.cfg           # pytest-Konfiguration
│       ├── app/
│       │   ├── main.py          # FastAPI-Worker-Endpoint
│       │   ├── parser.py        # XML-Parser + Canonical JSON + DITA/Assets
│       │   └── mapper.py        # YAML-Mapping-Engine
│       └── tests/
│           ├── test_parser.py   # 19 Parser-Tests
│           └── test_mapper.py   # 11 Mapper-Tests
│
├── frontend/                   # React + Vite
│   ├── Dockerfile
│   ├── package.json
│   ├── tsconfig.json
│   ├── index.html
│   └── src/
│       ├── App.tsx             # Hauptkomponente (Tabs, TreeView, Schema)
│       └── style.css
│
└── shared/                     # Service-übergreifend
    ├── schemas/
    │   ├── canonical-json.schema.json
    │   └── domain-json.schema.json
    ├── mappings/
    │   └── simqin-default.yaml   # Mapping-Profil (v0.2.0)
    └── test-fixtures/
        ├── example-topic.xml
        ├── example-topic.dtd
        └── example-ditamap.ditamap
```

---

## 6. Fehlerbehebung

| Problem | Ursache | Lösung |
|:--------|:--------|:-------|
| `port already allocated` | Port bereits belegt | `.env`-Ports ändern oder anderen Dienst stoppen |
| `Cannot connect to Worker` | Worker noch nicht bereit | `docker compose up` hat noch nicht abgeschlossen; `docker compose logs worker` prüfen |
| `CORS error in Browser` | Frontend-Origin nicht erlaubt | `CORS_ORIGINS` in `.env` anpassen, z. B. `["http://localhost:5173"]` |
| `npm install` fehlgeschlagen | Node-Version zu alt | Node 22+ verwenden |
| XML wird nicht akzeptiert | Falscher MIME-Type | Endung muss `.xml`, `.dita` oder `.ditamap` sein |
| `No DTD supplied`-Warnung | DTD nicht mitgeladen | Nur relevant wenn DTD-Validierung gewünscht; Warnung ist harmlos |

### Logs anzeigen

```bash
# Alle Services
docker compose logs -f

# Einzelner Service
docker compose logs -f api
docker compose logs -f worker
docker compose logs -f frontend
```

---

## 7. Produktionshinweise

Für den Produktionseinsatz müssen vor Inbetriebnahme folgende Punkte adressiert werden
(siehe `Batch 6` in `TASKS.md`):

- [ ] **Authentifizierung** — API-Key oder JWT
- [ ] **Persistenz** — MinIO/S3 statt temporärem Speicher
- [ ] **Job-Queue** — Redis + ARQ für asynchrone Verarbeitung
- [ ] **Logging** — Strukturierte Logs (JSON, z. B. via structlog)
- [ ] **CI/CD** — Automatisierte Tests und Deployments
- [ ] **CORS** — Explizite Origins setzen
- [ ] **Frontend-Build** — `npm run build` + statischer Serve statt Vite-Dev-Server

---

## 8. API-Referenz (Kurzfassung)

| Methode | Pfad | Beschreibung |
|:--------|:-----|:-------------|
| `GET` | `/health` | Health-Check (API) |
| `GET` | `/health` | Health-Check (Worker) |
| `POST` | `/api/v1/documents` | XML + optional DTD + optional Mapping YAML hochladen |
| `POST` | `/api/v1/convert` | XML + optional DTD + optional Mapping an Worker senden |
| `GET` | `/api/v1/schemas/canonical` | Canonical JSON Schema abrufen |
| `GET` | `/api/v1/schemas/domain` | Domain JSON Schema abrufen |

Detaillierte API-Dokumentation: **http://localhost:8080/docs** (nach Start).