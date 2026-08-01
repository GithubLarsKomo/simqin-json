# Phase 6 – Object-Oriented IFU Content Architecture

## Status

Phase 6 provides a deterministic, local foundation for reusable and revision-pinned IFU content families. It does not provide database persistence, authentication, productive LLM translation or automatic regulatory approval.

Implemented building blocks:

- revisioned `ContentObject` and `ContentObjectRevision` models
- single inheritance and recursive composition
- exact revision pinning without silent fallback
- deterministic graph-cycle detection
- approved multiplicity rules
- typed slots and placeholder rendering
- stable source segments and strict 1:1 translation validation
- revisioned configuration parameters
- immutable, checksum-verifiable language release snapshots
- additive BuildGraph and structured validation integration
- Phase 6 worker API and JSON Schemas
- frontend foundation for library, candidates, migrations and resolution preview
- realistic ELISA-family fixture

## Runtime entry point

The original worker remains available as `app.main:app`.

The Phase 6 API is mounted additively through:

```bash
cd services/worker
uvicorn app.phase6_main:app --reload
```

The following routes are then available:

| Method | Route | Purpose |
|---|---|---|
| GET | `/api/v1/content/schemas` | List Phase 6 schemas |
| GET | `/api/v1/content/schemas/{name}` | Return one Phase 6 schema |
| POST | `/api/v1/content/graph` | Build revision-aware content graph report |
| POST | `/api/v1/content/validate` | Validate objects, segments, slots and graph |
| POST | `/api/v1/content/resolve` | Resolve deterministic IFU blocks |
| POST | `/api/v1/translations/validate` | Validate strict 1:1 translation alignment |
| POST | `/api/v1/ifu/releases/verify` | Verify immutable release checksum |

## Revision resolution

Three modes are supported:

- `pinned`: every resolved object requires an explicit exact revision
- `working`: explicit pins win; otherwise the declared current revision is used
- `preview`: behaves like working mode but records warnings for unpinned revisions

A missing explicit pin never falls back to another revision. A missing current revision is blocking. Composition bindings use their own pinned child revision and conflicting global pins are rejected.

## Graph semantics

Content graph nodes are identified as `object_id@revision`.

Supported structural edges:

- `inherits-from`
- `composes`
- `alias-of`

The graph distinguishes:

- inheritance cycles
- composition cycles
- mixed inheritance/composition cycles
- alias cycles
- duplicate inclusion

A shared child in a diamond graph is not a cycle. Duplicate inclusion requires an approved `MultiplicityRule` and remains independent from cycle detection.

## Slots

The canonical placeholder syntax is:

```text
{{slot_id}}
```

Supported types include term, phrase, sentence, number, quantity, unit, range, percentage, temperature, duration, sample type, analyte, product name and conditional fragment.

Required unresolved slots are blocking. Quantity and range values are structurally validated. Percentage values default to a 0–100 range. Allowed values and allowed units are enforced when configured.

## Translation model

Translations maintain exact source-segment correspondence:

- same segment count
- same stable IDs
- same order
- no duplicate or missing IDs
- matching segment types
- no empty reviewed or approved segment
- all `{{slot}}` placeholders preserved
- approved translations only against approved canonical revisions

Multiple approved variants may coexist when applicability differs by market, country, product, technology, section or terminology profile. Ambiguous matching requires explicit selection.

No translation provider is invoked by Phase 6. `TranslationJobDefinition` only defines a future deterministic work package.

## Release snapshots

`IFULanguageReleaseSnapshot` freezes:

- product, language and release version
- exact content-object revisions
- exact translation-variant revisions
- configuration snapshot
- rendered blocks
- ruleset and terminology-profile revisions
- resolver provenance
- creation metadata

Checksum input excludes the checksum field itself. Identical snapshots yield identical checksums. Any pinned-content, configuration, translation or rendered-block change changes the checksum.

## Frontend foundation

`frontend/src/Phase6Workspace.tsx` contains four independent views:

1. **Content Library** – object status, language, revision, base template, composition and aliases
2. **Candidate Review** – proposed similarities, differences and suggested slots, never auto-approved
3. **Structure Migration Review** – original/proposed segments, impact, optional approval comment, mandatory reject/change comment and self-decision prevention
4. **IFU Resolution Preview** – ordered blocks, revision sources, paths, findings, configuration hash, checksum and provenance

The component is intentionally additive and is not yet wired into the monolithic frontend navigation. It can be imported into `frontend/src/main.tsx` or a future router without changing its API.

## ELISA fixture

The fixture is located at:

```text
services/worker/tests/fixtures/phase6_elisa_family.json
```

It includes:

- ten related ELISA products
- nine German-primary and one English-primary product
- shared intended-purpose and procedure templates
- analyte, sample material, incubation and unit differences
- recursively composed warnings
- one free variant
- one conditional block
- a valid diamond graph
- duplicate inclusion with approved multiplicity
- inheritance, composition, mixed and alias cycle examples
- two approved market-specific English variants
- one explicit translation selection
- pending, rejected and changes-requested migrations
- one immutable release reference

## Verification

Run:

```bash
cd services/worker
pytest tests/test_phase6c1_resolver.py -v
pytest tests/test_phase6c2a_configuration_release.py -v
pytest tests/test_phase6c2b_slots_translations_release.py -v
pytest tests/test_phase6c3a_integration.py -v
pytest tests/test_phase6c3b_api.py -v
pytest tests/test_phase6c4_fixture_contract.py -v
pytest tests -v

cd ../../frontend
npm run build
```

The GitHub connector cannot execute these commands. A green local or CI run is required before the implementation is considered release-ready.

## Known limitations

- no database persistence for Phase 6 entities
- no authenticated or role-backed privileged actions
- no automatic candidate acceptance or merge
- no production translation-provider execution
- no full WYSIWYG content-object editor
- Phase 6 API currently uses the dedicated `phase6_main` entry point
- frontend component is not yet connected to the main navigation
- only the first core Phase 6 schemas are exposed; the complete schema suite remains follow-up work
