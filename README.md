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

- **XML Upload** mit optionalem DTD und YAML-Mapping-Profil (Datei oder Textarea)
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
- **50 Snapshot-Tests** (pytest, alle grün)

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

## Phase 2 Capabilities

### DITA Map Support
Erkennt `<map>`/`<bookmap>`-Root-Elemente und extrahiert rekursiv:
- **TopicRefs** — `topicref`, `mapref`, `chapter`, `appendix`, `frontmatter`, `backmatter`
- **Attribute** — `href`, `navtitle`, `keys`, `keyref`, `format`, `scope`, `processing-role`, `toc`
- **Verschachtelung** — TopicRefs bleiben in ihrer Baumstruktur erhalten

### Asset Extraction
Extrahiert automatisch Bilder und grafische Elemente aus dem Dokument:
- **Tags** — `image`, `fig`, `graphic`
- **URI-Attribute** — `href`, `src`, `fileref`, `data`, `xlink:href`
- **Metadaten** — `alt`, `title`, `id`, `format`, `scope`, `_source` (XPath-Pfad)
- **Deduplizierung** — nach (URI normalisiert + Elementtyp)

### Reference Extraction
Extrahiert Querverweise und Links:
- **Tags** — `xref`, `link`
- **Attribute** — `href`, `format`, `scope`, `id`, `_source`
- **Text** — Link-Text wird extrahiert

### Verbesserte Tabellen
Unterstützt mehrere Formate:
- **DITA** — `<table>/<tgroup>/<thead>/<tbody>/<row>/<entry>`
- **Simpletable** — `<simpletable>/<strow>/<stentry>`
- **HTML** — `<table>/<tr>/<td>/<th>`
- **Caption** — `<caption>` oder `<title>` innerhalb der Tabelle
- **Scoping** — Tabellen erscheinen global und in der umgebenden Section

### Mapping Diagnostics
Bei Verwendung eines Mapping-Profils enthält `domain_json`:
- `_mapping.profile` — Name des Profils
- `_mapping.version` — Version
- `_mapping.rule_count` — Anzahl der Regeln
- `_mapping.warnings` — Warnungen (z. B. ungematchte XPath-Regeln)

### Fehlerbehandlung
- **Ungültiges Mapping-YAML** → HTTP 400 mit klarer Fehlermeldung
- **Ungültiger XPath in Mapping-Regel** → Regel wird übersprungen, Warning wird erzeugt
- **Kein stummer Fallback** — fehlerhaftes User-Mapping wird nicht durch Default ersetzt

### JSON Schema Endpoints
- `GET /api/v1/schemas/canonical` — Canonical JSON Schema (mit rekursivem `$defs/node`)
- `GET /api/v1/schemas/domain` — Domain JSON Schema (mit `$defs` für asset, reference, table, topicref)

## Entwicklung

### Makefile

```bash
make test      # Tests ausführen
make up        # Docker Compose starten
make down      # Docker Compose stoppen
make lint      # Python-Syntax-Prüfung
```

## Publishing Engine (Phase 5)

Die Publishing Engine ermöglicht Cross-Document-Analyse, Referenz-Auflösung und Build-Reports.

### Dependency Graph

Der **BuildGraph** erstellt einen gerichteten Abhängigkeitsgraphen aus einem Project mit Knoten für Dokumente, TopicRefs, Assets, Keys und Referenzen.

Erkannte Probleme:
- **Duplicate IDs** — gleiche ID in mehreren Elementen
- **Duplicate Keys** — gleicher Key in mehreren TopicRefs
- **Orphan Documents** — Dokumente ohne Referenzen
- **Orphan Assets** — Projekt-Assets ohne Verwendung
- **Circular References** — zyklische Abhängigkeiten (DFS-basiert)

### Project Index

Der **ProjectIndex** indiziert Titel, IDs, Keys, Absätze, Sections, Assets, TopicRefs und Metadaten. Durchsuchbar via `POST /api/v1/projects/index`.

### Reference Resolver

Der **ReferenceResolver** löst auf:
- `resolve_href(href)` — Dokument-Pfade, IDs, externe URLs
- `resolve_keyref(keyref)` — DITA-Key-Referenzen
- `resolve_conref(conref)` — (vorbereitet, noch nicht implementiert)
- `resolve_topicref(href)` — TopicRef-Auflösung

### Validation Engine

Vier Level: `INFO`, `WARNING`, `ERROR`, `FATAL`. Prüft:
- Duplikate (IDs, Keys)
- Broken Links
- Fehlende Assets
- Ungültige Referenzen
- Profilverletzungen

### Build Report

`POST /api/v1/projects/publish` erzeugt einen vollständigen Build-Report:
- Statistiken (Knoten, Kanten, Dokumente, TopicRefs, Assets)
- Aufgelöste Referenzen
- Ungenutzte Assets
- Verwaiste Dokumente
- Warnungen und Fehler

### Package Manifest

Das **PackageManifest** fasst alle Dokumente und Assets mit Versionsinformationen zusammen — Grundlage für spätere ZIP-Paketierung.

### API Endpoints (Phase 5)

| Methode | Pfad | Beschreibung |
|:--------|:-----|:-------------|
| `POST` | `/api/v1/projects/graph` | Abhängigkeitsgraph + Diagnose |
| `POST` | `/api/v1/projects/index` | Durchsuchbarer Projekt-Index |
| `POST` | `/api/v1/projects/resolve` | Referenz-Auflösung |
| `POST` | `/api/v1/projects/validate` | Vollständige Projekt-Validierung |
| `POST` | `/api/v1/projects/publish` | Build-Report (Publishing Pipeline) |
| `POST` | `/api/v1/projects/package-manifest` | Package-Manifest erzeugen |

### Frontend

Die **BuildView**-Komponente zeigt Build-Reports mit Statistiken, Fehlern und Warnungen an. Klickbare Warnungen navigieren zum betroffenen Dokument.

### Test Suite

```bash
cd services/worker && pytest tests/ -v
# → 147 Tests, alle grün
```

### Project Model

- **Projekt** — Name, ID, Erstellungs-/Änderungsdatum, Sammlung von Dokumenten und Assets
- **Document** — Ein `AuthoringDoc` innerhalb eines Projekts
- **Asset** — Datei-Referenz (image, svg, pdf, csv, xlsx, video) mit Metadaten (id, filename, mime, size, refs)
- **Manifest** — Leichtgewichtige Projekt-Zusammenfassung (schema-versioniert)

### API Endpoints

| Methode | Pfad | Beschreibung |
|:--------|:-----|:-------------|
| `GET` | `/api/v1/projects/new` | Neues leeres Projekt anlegen |
| `POST` | `/api/v1/projects/open` | Projekt öffnen / neu laden |
| `POST` | `/api/v1/projects/save` | Projekt-Manifest speichern |
| `POST` | `/api/v1/projects/add-document` | Dokument hinzufügen |
| `POST` | `/api/v1/projects/remove-document` | Dokument entfernen |
| `POST` | `/api/v1/projects/rename-document` | Dokument umbenennen |
| `POST` | `/api/v1/projects/add-asset` | Asset hinzufügen |
| `POST` | `/api/v1/projects/remove-asset` | Asset entfernen |
| `POST` | `/api/v1/projects/update-metadata` | Metadaten aktualisieren |
| `POST` | `/api/v1/projects/set-root` | Root-DITA-Map setzen |
| `GET` | `/api/v1/projects/manifest` | Projekt-Manifest abrufen |
| `POST` | `/api/v1/projects/search` | Volltext-Suche (Titel, Absätze, IDs, TopicRefs, Assets) |
| `POST` | `/api/v1/projects/build` | Build-Report (Dokument-/Asset-Zählung, Prüfung) |

### Frontend

Der **Workspace**-Tab zeigt eine Explorer-Seitenleiste mit Projektdokumenten und Assets. Geöffnete Dokumente erscheinen als Tabs.

### Test Suite

```bash
cd services/worker && pytest tests/ -v
# → 129 Tests, alle grün
```

Test-Abdeckung:
- Project creation + serialization (roundtrip, JSON)
- Manifest generation + schema validation
- Document add/remove/rename
- Asset add/remove
- Search (title, paragraph, topicref)
- Build check (empty, populated)
- JSON Schema validation (project, manifest)
- DTD-Validierung (valid, invalid)
- XXE-Sicherheit
- Canonical JSON (attributes, text, namespaces)
- Domain JSON (title, sections, custom mapping)
- DITA Maps (topicrefs, navtitle, scope, format, keys, full types, processing-role, toc)
- Asset/Reference Extraction (href, alt, fig, dedup, _source)
- Mapping Validation (invalid YAML, missing rules, missing match, invalid type)
- Table Extraction (DITA tgroup, simpletable)
- Domain Schema Validation
