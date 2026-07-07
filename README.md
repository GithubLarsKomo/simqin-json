# SIMQIN JSON Platform

Browsernahe Microservice-Plattform zum Einlesen von SIMQIN-/DTD-/DITA-nahen XML-Dateien und Export in JSON.

## Quick Start

```bash
cp .env.example .env
docker compose up --build
```

Danach:

- Frontend: http://localhost:5173
- API: http://localhost:8080/docs

## MVP-Funktionen

- XML Upload
- sichere XML-Verarbeitung gegen XXE
- DTD-Validierung, wenn DTD mitgeliefert wird
- kanonischer JSON-Export
- fachlicher Domain-JSON-Export
- Validierungsbericht
- React UI mit Upload, Strukturbaum und JSON Preview

## Projektstruktur

```text
frontend/                 Browser UI
services/api/             FastAPI API Gateway
services/worker/          Parser, Validator, Mapper
shared/schemas/           JSON Schemas
shared/mappings/          Mapping Profiles
shared/test-fixtures/     Beispiel XML/DTD
docs/                     Zusatzdokumentation
```

## Beispiel API

```bash
curl -F "file=@shared/test-fixtures/example-topic.xml" \
     -F "dtd=@shared/test-fixtures/example-topic.dtd" \
     http://localhost:8080/api/v1/documents
```

## Hinweis

Dieses Layout ist als belastbares Startprojekt gedacht. Für Produktion müssen Authentifizierung, Persistenz, Audit Logging, Mandantentrennung und Security-Hardening ergänzt werden.
