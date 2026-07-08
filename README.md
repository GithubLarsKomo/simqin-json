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

## Features

- **XML Upload** mit optionalem DTD und YAML-Mapping-Profil
- **XXE-sicheres XML-Parsing** via lxml (`resolve_entities=false`)
- **DTD-Validierung** mit Zeilen-/Spaltenangabe
- **Canonical JSON** — verlustarme technische Abbildung des XML-Baums (Strukturbaum-Ansicht)
- **Domain JSON** — fachlich normalisierte Darstellung (YAML-Mapping-gesteuert)
- **DITA Map Erkennung** — extrahiert TopicRefs mit href, navtitle, scope, format, keys
- **Asset-/Referenz-Extraktion** — Bilder, Figures, XRefs, Links
- **Verbesserte Tabellen-Extraktion** — DITA (`row/entry`) und HTML (`tr/td/th`)
- **JSON Schema Endpoints** — Canonical und Domain Schema via API abrufbar
- **Validierungsbericht** — tabellarisch, farbcodiert, als JSON/Text downloadbar
- **React UI** mit Strukturbaum, Tabs (Canonical/Domain/Assets/Referenzen/Validierung/Schema)
- **30 Snapshot-Tests** (pytest, alle grün)

## Projektstruktur

```text
frontend/                 Browser UI
services/api/             FastAPI API Gateway (mit Schema-Endpoints)
services/worker/          Parser, Validator, Mapper (DITA, Assets, Tables)
shared/schemas/           JSON Schemas (canonical + domain)
shared/mappings/          Mapping Profiles (YAML)
shared/test-fixtures/     Beispiel XML/DTD/DITA-Map
docs/                     Zusatzdokumentation
```

## Beispiel API

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

## Hinweis

Dieses Layout ist als belastbares Startprojekt gedacht. Für Produktion müssen Authentifizierung, Persistenz, Audit Logging, Mandantentrennung und Security-Hardening ergänzt werden.
