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


## Optionales Langfristziel - Objektorientierte IFU-Familien und LLM-gestuetzte Uebersetzung

### Uebersicht

Dieser Abschnitt dokumentiert die Architektur fuer die zukuenftige Unterstuetzung
regulatorischer IFU-Dokumentationsfamilien (z.B. ELISA-Produkte), bei denen
wiederverwendbare Content Objects die Grundlage bilden.

### Kernkonzept

- **ContentObject** - Ein atomarer, versionierter Inhaltsbaustein (Template, Section, Paragraph, Warnhinweis)
- **Single Inheritance** - Jedes ContentObject hat maximal eine Basisvorlage
- **Recursive Composition** - ContentObjects koennen rekursiv andere ContentObjects komponieren
- **Typed Slots** - Definierte Austauschstellen fuer Terme, Zahlen, Einheiten, Analyten etc.
- **Configuration Catalog** - Gepruefte Konfigurationsparameter fuer steuernde Bedingungen

### Single Inheritance

- Jedes ContentObject hat null oder eine base_template_id
- Mehrfachvererbung ist verboten
- Maximale Vererbungstiefe: 20 (konfigurierbar)
- Validierung erkennt: Zyklen, fehlende Basen, Selbstreferenzen, uebermaessige Tiefe

### Recursive Composition

- ContentObjects koennen andere ContentObjects ueber CompositionBinding einbinden
- Unterstuetzte Platzierungen: before:<block-id>, after:<block-id>, first, last
- Deterministic ordering ueber order-Feld
- Validierung erkennt: Kompositionszyklen, Mixed-Zyklen, fehlende Child-Objekte, ungueltige Anker

### Standard Single Inclusion

- Gleiches ContentObject erscheint standardmaessig nur einmal pro aufgeloestem IFU
- MultiplicityRule mit Mode single/multiple erlaubt Ausnahmen
- Doppelte Inclusion ohne genehmigte Regel -> blockierender Validierungsfehler

### Binding Modes

- **derived** - Folgt genehmigter Basisvorlage, erhaelt Update-Vorschlaege
- **free** - Weicht bewusst ab, bleibt logisch verknuepft, wird nie automatisch ueberschrieben
- **proposed** - Automatisch erkannter Kandidat, nicht fuer Produktion freigegeben

### Typed Slots

Unterstuetzte Typen:
term, phrase, sentence-fragment, sentence, number, quantity, unit, range, percentage,
temperature, duration, sample-type, analyte, product-name, regulatory-market, conditional-fragment

Jeder Slot hat: ID, Typ, Required-Flag, Default-Wert, allowed_values, allowed_units.

### Declarative Conditions

- Erlaubte Operatoren: equals, not_equals, in, not_in, exists, and, or
- Kein Python, kein JavaScript, keine API-Calls, keine Laufzeit-LLM-Entscheidungen
- Steuern: Slot-Werte, Alternativ-Fragmente, komplette Block-Inclusion
- Variant Group Modes: zero_or_more, zero_or_one, exactly_one

### Configuration Parameter Catalog

- Parameter werden vor Nutzung erstellt und freigegeben
- Typen: string, boolean, integer, decimal, enum, string-list
- Werte werden in IFU Working Version auf Parameter-Revision gepinnt

### Sentence Segments

- Stabile Satz- und Segment-IDs
- Segmenttypen: sentence, heading, list-item, table-cell, caption, label
- immutable_boundary = true fuer Saetze
- 1:1-Beziehung zwischen Quell- und Uebersetzungssegmenten

### Structure Migration

- Vier-Augen-Prinzip: Ersteller und Genehmiger muessen verschieden sein
- Migrationstypen: split, merge, resegment
- Status: draft -> pending_approval -> approved/rejected
- Pflichtkommentar bei rejection, optional bei approval

### Translation Domain Model

- Kein LLM-Aufruf in dieser Phase, nur Datenmodell
- TranslationVariant mit ID, ContentObject, Zielsprache, Status, Segment-Uebersetzungen
- TranslationSegment mit 1:1-Beziehung zum Source-Segment
- Mehrere genehmigte Varianten pro Sprache erlaubt

### Content Merge

- Mehrere ContentObjects koennen in ein kanonisches Objekt gemergt werden
- Alte IDs bleiben als Aliase erhalten
- Historische Releases loesen weiterhin alte IDs auf

### Automatic Template Candidate Detection

- Nur Baseline-Detektor auf Basis von Token-Aehnlichkeit und Sequence-Matching
- Keine ML/LLM-Abhaengigkeiten
- Niemals automatische Freigabe oder Merge
- SuggestedTemplateCandidate mit Status proposed

### Known Limitations

- Der Baseline-Alignment-Algorithmus (Needleman-Wunsch-artig) verwendet nur Token-Oberflaechengleichheit
- Keine Lemmatisierung, keine Synonyme, kein n:m-Phrase-Matching
- Produktive LLM-Uebersetzung ist explizit NICHT Teil dieser Phase
- Keine Datenbank-Persistenz in dieser Phase
