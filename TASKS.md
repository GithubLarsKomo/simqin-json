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
- [x] 30 Tests (alle grün)

## ⬜ Batch 6 — Production Readiness (offen)

- [ ] Authentifizierung
- [ ] Persistenz (MinIO/S3)
- [ ] Job Queue (Redis + ARQ)
- [ ] Audit Log
- [ ] CI/CD
