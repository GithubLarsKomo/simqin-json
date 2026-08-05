# SIMQIN JSON – Phase 6 Beta Readiness

## Status

Phase 6 has reached a reproducible beta baseline for the content architecture, resolver, validation API, standalone frontend workspace, and Docker wiring.

This document distinguishes **verified evidence** from **remaining limitations**. It does not claim production readiness.

## Verified beta gates

The following checks have been executed successfully on the current Phase 6 line:

- Worker test suite: **223 passed** before the final beta delta.
- Frontend dependency audit: **0 vulnerabilities** after upgrading to Vite 6.4.3 and applying the non-breaking PostCSS remediation.
- Frontend production build succeeds.
- Multi-page output includes:
  - `dist/index.html`
  - `dist/phase6.html`
- Docker Compose starts all three services:
  - `simqin-json-worker`
  - `simqin-json-api`
  - `simqin-json-frontend`

The final beta delta adds composition-placement validation, standalone resolver demo wiring, gateway Phase 6 proxy routes, and Docker entrypoint changes. Re-run the complete worker suite after pulling the latest `master` to establish the new exact test count.

## Phase 6 beta capabilities

### Content model

- Revision-aware `ContentObject` / `ContentObjectRevision` model.
- `ContentBinding` modes: `derived`, `free`, `proposed`.
- Exact revision pinning for content and composition references.
- Reusable slots with typed definitions and configuration values.
- Sentence/content segments.
- Applicability / visibility rules.
- Multiplicity rules.
- Aliases after merge operations.

### Resolver

- `pinned`, `working`, and `preview` revision modes.
- Deterministic inheritance merge.
- Deterministic composition ordering.
- Alias resolution.
- Required-slot detection and template rendering.
- Multiplicity enforcement.
- Inheritance/composition/mixed cycle detection.
- Provenance capture.
- Stable content/graph checksums.
- Structured findings with severity and codes.

### Validation

The central Phase 6 validation gate checks, among other things:

- invalid current revisions;
- graph cycles;
- segment structure;
- duplicate slot identifiers;
- slot definitions and supplied values;
- unresolved required slots;
- missing composed objects/revisions;
- translation constraints;
- invalid, missing, or ambiguous composition anchors;
- cyclic composition-placement constraints.

### Translation and release foundation

- Revision-aware translation variants.
- Segment-aware translation validation.
- Placeholder preservation checks.
- Immutable IFU language release snapshots.
- Canonical checksum verification.

### API

Worker Phase 6 routes are available below `/api/v1`:

- `GET /content/schemas`
- `GET /content/schemas/{schema_name}`
- `POST /content/graph`
- `POST /content/validate`
- `POST /content/resolve`
- `POST /translations/validate`
- `POST /ifu/releases/verify`

The API gateway proxies the Phase 6 routes to the worker so the browser can continue to use the normal API base URL on port 8080.

### Frontend

The standalone Phase 6 workspace is available at:

```text
http://localhost:5173/phase6.html
```

It currently provides:

- Content Library
- Candidate Review
- Structure Migration Review
- IFU Resolution Preview

The standalone entry contains a minimal ELISA resolver payload so the Resolution Preview can exercise the real Phase 6 API path instead of rendering an empty demo shell.

## Reproducible start

From the repository root:

```powershell
git pull origin master
docker compose up -d
docker compose ps
```

Expected running services:

```text
simqin-json-worker
simqin-json-api
simqin-json-frontend
```

## Local verification

### Worker

```powershell
cd services\worker
python -m pip install -r requirements.txt
python -m compileall app
pytest tests -q
```

### Frontend

```powershell
cd frontend
npm ci
npm audit --audit-level=moderate
npm run build
```

Expected build artifacts:

```text
dist/index.html
dist/phase6.html
```

## Phase 6 smoke test

With Docker Compose running:

```powershell
Invoke-RestMethod http://localhost:8080/health
Invoke-RestMethod http://localhost:8080/api/v1/content/schemas
```

Then open:

```text
http://localhost:5173/phase6.html
```

In **resolution**, use **Auflösen**. A successful beta smoke test returns at least one resolved block, a checksum, a graph checksum/provenance structure, and no unexpected `ERROR`/`FATAL` finding for the built-in demo payload.

## Known limitations – not beta blockers

- Candidate Review remains presentational; there is no persisted candidate approval workflow yet.
- Structure Migration Review enforces the four-eyes rule in the UI but decisions are not persisted to backend storage yet.
- Phase 6 storage is still largely in-memory/domain-model oriented; production persistence and authorization are intentionally outside this beta baseline.
- No claim of productive automatic translation approval is made.
- No claim of productive LLM-driven migration/merge decisions is made.
- The standalone Phase 6 workspace is still a separate page rather than fully integrated into the legacy monolithic navigation.
- GitHub status visibility through the current ChatGPT connector is incomplete; local verification remains the authoritative evidence until Actions results are independently visible.

## Beta exit criteria for the next phase

The current Phase 6 beta is suitable for functional evaluation of the architecture and deterministic resolution pipeline. Before a production-oriented release, add at minimum:

1. persistent repository/storage services for content, review decisions, translations, and releases;
2. authentication/authorization and reviewer identity enforcement server-side;
3. persisted migration and candidate approval APIs;
4. end-to-end browser tests against the Docker stack;
5. release/export packaging from an approved pinned configuration;
6. operational backup, migration, and audit-log strategy.

## Current assessment

**Phase 6 beta: READY for controlled functional evaluation.**

This means the deterministic content model/resolver/validation foundation and the browser/API execution path are sufficiently complete to evaluate real ELISA/IFU family scenarios. It does **not** mean the system is production-ready or ready for regulated use without the remaining persistence, authorization, audit, and release-governance work above.
