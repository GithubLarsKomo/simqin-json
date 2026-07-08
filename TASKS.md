# TASKS.md — Implementierungsbatches

## ✅ Batch 1 — Projektbasis (erledigt)

- [x] Repository anlegen
- [x] Docker Compose validieren
- [x] API Service starten
- [x] Frontend Service starten
- [x] Beispiel-Fixtures testen

## ✅ Batch 2 — Parser (erledigt)

- [x] XML Parser mit lxml implementieren
- [x] XXE-Schutz testen
- [x] Attribute erhalten
- [x] Textknoten erhalten
- [x] Elementreihenfolge erhalten
- [x] Namespaces extrahieren

## ✅ Batch 3 — Validierung (erledigt)

- [x] DTD Upload unterstützen
- [x] DTD-Validierung implementieren
- [x] Fehler mit Zeile, Spalte, Message ausgeben
- [x] Validation Report standardisieren

## ✅ Batch 4 — Mapping (erledigt)

- [x] Canonical JSON Serializer implementieren
- [x] Domain Mapper für Topic/Title/Section implementieren
- [x] Mapping YAML laden und anwenden
- [x] JSON Schema Validierung im Worker
- [x] Snapshot Tests (25 Tests, alle grün)

## ✅ Batch 5 — Frontend (erledigt)

- [x] Upload-Komponente
- [x] JSON Preview (TreeView, Tabs)
- [x] Validierungsreport (tabellarisch, farbcodiert)
- [x] Download Buttons
- [x] Strukturbaum (TreeView rekursiv)
- [x] Responsive Design

## ✅ Batch 5b — Phase 2 Erweiterungen (erledigt)

- [x] YAML-Mapping-Upload (API + Worker)
- [x] DITA Map Erkennung (map/bookmap)
- [x] TopicRef-Extraktion (href, navtitle, scope, format, keys)
- [x] Asset-Extraktion (image, fig, graphic)
- [x] Referenz-Extraktion (xref, link)
- [x] Verbesserte Tabellen (DITA + HTML)
- [x] JSON Schema Endpoints (canonical + domain)
- [x] Frontend: Assets/Referenzen/Schema-Tabs
- [x] Frontend: YAML-Upload-Feld
- [x] Frontend: Validierungsreport-Download (JSON + Text)
- [x] Frontend: Mapping-Diagnostik-Tab + YAML-Textarea
- [x] 51 Tests (alle grün)
- [x] Invalid XPath → MappingValidationError → HTTP 400
- [x] domain_json immer mit title/sections/assets/references/metadata
- [x] JSON Schema Validation mit jsonschema Draft 2020-12
- [x] Makefile robuster (Pfade, frontend-build)

## ✅ Phase 3 — Structured Authoring (erledigt)

- [x] Authoring JSON Modell (authoring.py)
- [x] Templates: DITA Topic, SOP, DITA Map (templates.py)
- [x] XML Writer (xml_writer.py) für DITA Topic + Map XML
- [x] Worker-Endpoints: GET /api/v1/templates, GET /api/v1/templates/{template_id}, POST /authoring/render-xml, /render-json, /validate
- [x] API-Gateway-Proxies inkl. Template-by-ID
- [x] Frontend: "Neues Dokument"-Seite mit Template-Auswahl
- [x] Frontend: Editor (Titel, Abschnitte, Absätze, Tabellen, Bilder, Links, TopicRefs)
- [x] Frontend: Live-Vorschau (WYSIWYG, XML, JSON)
- [x] Frontend: Export XML (.dita/.ditamap/.xml je nach Template)
- [x] Frontend: Validierung (Titel, Heading, IDs)
- [x] **Nested TopicRefs** im DITA Map Editor (rekursives UI + WYSIWYG)
- [x] Template-Abruf vom Backend statt hardcodierter Templates im Frontend
- [x] 84 Tests (alle grün)
- [x] Roundtrip: Authoring JSON → XML → convert_xml → domain_json

## ✅ Phase 3b — Structure-governed Authoring Editor (erledigt)

- [x] Authoring Profiles pro Dokumenttyp (dita-topic, sop, dita-map)
- [x] Jedes Profil definiert: allowed root fields, allowed children, required fields, allowed attributes, export extension
- [x] GET /api/v1/authoring/profiles
- [x] GET /api/v1/authoring/profiles/{profile_id}
- [x] POST /api/v1/authoring/allowed-actions
- [x] Profile-basierte Validierung (validate_with_profile)
- [x] Frontend: 3-Panel-Layout (Strukturbaum links, WYSIWYG mitte, Inspektor rechts)
- [x] Strukturbaum mit expandierbaren Knoten und Auswahl
- [x] Inspektor zeigt editierbare Attribute des selektierten Knotens
- [x] Action-Bar zeigt nur erlaubte "Add"-Aktionen (laut Profil)
- [x] Move up/down für Blöcke
- [x] Delete für selektierte Knoten
- [x] Live-Vorschau, XML, JSON, Validierungs-Tabs unten
- [x] 98 Tests (alle grün)

- [ ] Authentifizierung
- [ ] Persistenz (MinIO/S3)
- [ ] Job Queue (Redis + ARQ)
- [ ] Audit Log
- [ ] CI/CD
