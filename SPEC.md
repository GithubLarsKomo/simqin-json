# SPEC.md — SIMQIN XML to JSON Browser Microservice Platform

## 1. Ziel

Entwicklung einer browserbasierten Plattform, die SIMQIN-kompatible XML-Dokumente einliest, validiert, strukturell darstellt und als JSON exportiert.

Die Plattform soll XML nicht nur flach konvertieren, sondern Struktur, Attribute, Textreihenfolge, Namespaces, Referenzen und Validierungsbefunde nachvollziehbar erhalten.

## 2. Input

Unterstützte Eingaben:

- XML
- DTD
- XSD optional
- DITA Topic / DITA Map optional
- ZIP-Paket optional in späterer Phase
- XML Catalog optional in späterer Phase

## 3. Output

Die Plattform erzeugt zwei JSON-Sichten:

1. Canonical JSON
   - verlustarme technische Abbildung des XML-Baums
   - erhält Reihenfolge, Attribute, Namespaces und Textknoten

2. Domain JSON
   - fachlich normalisierte Darstellung
   - geeignet für RAG, API-Integration, Review und Migration

## 4. MVP Scope

MVP enthält:

- Browser Upload
- FastAPI Backend
- XML Parsing mit XXE-Schutz
- DTD-Validierung
- Canonical JSON Export
- Domain JSON Export
- Validierungsbericht
- einfache React UI
- Docker Compose
- Test-Fixtures

Nicht im MVP:

- vollwertiger WYSIWYG Editor
- kollaboratives Editing
- CMS-Anbindung
- komplexe DITA Map Resolution (Cross-Deliverable-Resolution)
- Benutzerverwaltung

## 4.1 Über den MVP hinaus (Phase 2)

In Phase 2 wurden folgende Erweiterungen realisiert:

- **YAML-Mapping-Upload** als Alternative zum Default-Profil
- **DITA Map Erkennung** für `<map>`/`<bookmap>`-Root-Elemente
- **TopicRef-Extraktion** mit href, navtitle, scope, format, keys (rekursiv)
- **Asset-Extraktion** für `<image>`, `<fig>`, `<graphic>`
- **Referenz-Extraktion** für `<xref>`, `<link>`
- **Verbesserte Tabellen** für DITA- und HTML-Formate
- **JSON Schema Endpoints** zum Abruf der Schemas

## 4.2 Phase 3 — Structured Authoring (abgeschlossen)

In Phase 3 wurden folgende Erweiterungen realisiert:

- **Authoring JSON Modell** als browser-edierbarer Dokumenten-Zwischenstand
- **Templates** für DITA Topic, SOP, DITA Map mit Default-Inhalten
- **REST-Endpoint** `GET /api/v1/templates/{template_id}` zum Abruf vollständiger Template-JSONs
- **XML Writer** zur Generierung von DITA Topic XML (`.dita`) und DITA Map XML (`.ditamap`)
- **Intelligenter Export**: DITA Maps werden als `.ditamap`, Topics als `.dita`, sonstige als `.xml` exportiert
- **WYSIWYG-Editor** mit Live-Vorschau (Vorschau/XML/JSON-Tabs)
- **Verschachtelte TopicRefs** im DITA Map Editor: rekursive Bearbeitung und Anzeige
- **Rückkanal**: Authoring JSON → XML → convert_xml → Domain JSON (Roundtrip getestet)
- **84 automatisierte Tests** (alle grün)

## 4.3 Phase 3b — Structure-governed Authoring Editor (abgeschlossen)

In Phase 3b wurde der strukturorientierte Editor realisiert:

- **Authoring Profiles** pro Dokumenttyp: definieren erlaubte Felder, Kind-Elemente, Attribute und Export-Regeln
- **REST-Endpoints**: `GET /api/v1/authoring/profiles`, `GET .../{profile_id}`, `POST /api/v1/authoring/allowed-actions`
- **Profil-basierte Validierung**: Fehler enthalten den Node-Path für die UI
- **3-Panel-Layout**:
  - Links: **Strukturbaum** mit expandierbaren Knoten, Auswahl und Label-Anzeige
  - Mitte: **WYSIWYG-Editor** mit selektierbaren Blöcken und Action-Bar
  - Rechts: **Inspektor** mit editierbaren Attributen des selektierten Knotens
- **Action-Bar**: zeigt nur die vom Profil erlaubten "Add"-Aktionen an
- **Move up/down** und **Delete** für Blöcke
- **Live-Vorschau** in XML, JSON und Validierung als Bottom-Tabs
- **98 automatisierte Tests** (alle grün)
- **Frontend-Build** (`npm run build`) erfolgreich

## 5. Architektur

```text
Browser UI
   |
   v
API Gateway / FastAPI
   |
   v
Worker Library
   |-- XML Parser
   |-- DTD Validator
   |-- Canonical Mapper
   |-- Domain Mapper
   |-- JSON Schema Checker
```

Für spätere Skalierung können Parser, Validator und Mapper in separate Services ausgelagert werden.

## 6. Services

### frontend-service

Aufgaben:

- Upload UI
- XML-/JSON-Vorschau
- Validierungsreport
- Download Buttons

### api-service

Aufgaben:

- REST API
- Dateiannahme
- Job-Erzeugung
- Aufruf des Workers
- Ergebnisbereitstellung

### worker-service

Aufgaben:

- sicheres XML Parsing
- Validierung
- Transformation nach JSON
- Berichtserzeugung

## 7. Canonical JSON Format

```json
{
  "document": {
    "source_filename": "example.xml",
    "root": {
      "type": "element",
      "name": "topic",
      "namespace": null,
      "attributes": {
        "id": "t1"
      },
      "children": []
    }
  },
  "metadata": {
    "parser_version": "0.1.0",
    "validated": true,
    "schema_type": "DTD",
    "errors": [],
    "warnings": []
  }
}
```

## 8. Domain JSON Format

```json
{
  "title": "Example Title",
  "sections": [
    {
      "heading": "Section 1",
      "body": "Text content",
      "tables": [],
      "figures": []
    }
  ],
  "assets": [
    { "type": "image", "href": "img/example.png", "alt": "Example" }
  ],
  "references": [
    { "type": "xref", "href": "#topic-id", "text": "siehe oben" }
  ],
  "dita_map": {
    "id": "my-map",
    "title": "Example DITA Map",
    "topicrefs": [
      {
        "href": "topics/overview.dita",
        "navtitle": "Overview",
        "scope": "local",
        "format": "dita"
      }
    ]
  },
  "metadata": {}
}
```

Das Domain JSON wird wahlweise über ein YAML-Mapping-Profil gesteuert (siehe `shared/mappings/simqin-default.yaml`). Assets (Bilder, Figures), Referenzen (XRefs, Links) und DITA-Map-Strukturen werden automatisch erkannt und angereichert.

### 8.1 JSON Schema Endpoints

Die Plattform stellt zwei Schema-Endpoints bereit:

- `GET /api/v1/schemas/canonical` — Schema für Canonical JSON
- `GET /api/v1/schemas/domain` — Schema für Domain JSON (inkl. assets, references, dita_map)

## 9. Security Anforderungen

Pflicht:

- keine ungeprüfte externe Entity-Auflösung
- Parser mit `resolve_entities=false`
- Dateigrößenlimit
- MIME-/Extension-Prüfung
- isolierter temporärer Speicher
- keine Ausführung von eingebettetem Code
- strukturierte Fehlerausgabe statt Stacktraces im Frontend

## 10. Akzeptanzkriterien

- Upload eines XML-Dokuments funktioniert.
- Optionales DTD kann mitgeladen werden.
- Valides XML erzeugt JSON.
- Ungültiges XML erzeugt verständlichen Fehlerbericht.
- Canonical JSON enthält alle Elemente, Attribute und Textknoten.
- Domain JSON enthält Titel und Sections.
- UI und API liefern konsistente Ergebnisse.
- Docker Compose startet Frontend und API reproduzierbar.
