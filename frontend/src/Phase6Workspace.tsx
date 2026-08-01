import React, { useMemo, useState } from 'react';

const API_BASE = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8080';

type ContentObjectSummary = {
  id: string;
  type: string;
  status: string;
  canonical_language: string;
  current_revision: number;
  base_template_id?: string;
  aliases?: string[];
  composed_children?: string[];
};

type Candidate = {
  candidate_id: string;
  section_type: string;
  similarity: number;
  source_references: string[];
  differing_spans: Array<[string, string]>;
  suggested_slots: string[];
  status: 'proposed';
};

type Migration = {
  migration_id: string;
  created_by: string;
  status: string;
  original_segments: string[];
  proposed_segments: string[];
  impact_summary: string;
};

type ResolutionBlock = {
  block_id: string;
  source_object_id: string;
  source_revision: number;
  rendered_content: string;
  inheritance_path: string[];
  composition_path: string[];
};

type ResolutionResult = {
  blocks: ResolutionBlock[];
  findings: Array<{ code: string; severity: string; message: string }>;
  config_hash: string;
  checksum: string;
  provenance: Record<string, unknown>;
};

type Phase6WorkspaceProps = {
  currentUser?: string;
  initialObjects?: ContentObjectSummary[];
  initialCandidates?: Candidate[];
  initialMigrations?: Migration[];
  resolvePayload?: Record<string, unknown>;
};

const DEMO_OBJECTS: ContentObjectSummary[] = [
  { id: 'tpl-intended-purpose', type: 'template', status: 'approved', canonical_language: 'de-DE', current_revision: 1, aliases: [] },
  { id: 'tpl-procedure', type: 'template', status: 'approved', canonical_language: 'de-DE', current_revision: 1, composed_children: ['warning-general'] },
  { id: 'warning-general', type: 'warning', status: 'approved', canonical_language: 'de-DE', current_revision: 1, aliases: ['old-warning-id'] },
  { id: 'free-ccp-purpose', type: 'paragraph', status: 'approved', canonical_language: 'de-DE', current_revision: 1, base_template_id: 'tpl-intended-purpose' },
];

const DEMO_CANDIDATES: Candidate[] = [
  {
    candidate_id: 'candidate-purpose-family',
    section_type: 'intended-purpose',
    similarity: 0.91,
    source_references: ['elisa-ana-igg@1', 'elisa-dsdna-igg@1', 'elisa-ena-profile@1'],
    differing_spans: [['ANA', 'dsDNA'], ['Serum', 'Serum/Plasma']],
    suggested_slots: ['analyte', 'sample_type'],
    status: 'proposed',
  },
];

const DEMO_MIGRATIONS: Migration[] = [
  {
    migration_id: 'mig-pending',
    created_by: 'author-a',
    status: 'pending_approval',
    original_segments: ['Alle Reagenzien vor Gebrauch auf Raumtemperatur bringen.'],
    proposed_segments: ['Alle Reagenzien vor Gebrauch auf Raumtemperatur bringen.', 'Vor Gebrauch vorsichtig mischen.'],
    impact_summary: '2 approved translation variants and 4 product working versions are affected.',
  },
];

function SectionTitle({ children }: { children: React.ReactNode }) {
  return <div className="section-header"><h2>{children}</h2></div>;
}

function ContentLibraryView({ objects }: { objects: ContentObjectSummary[] }) {
  return (
    <div className="card">
      <SectionTitle>Content Library</SectionTitle>
      <table className="validation-table">
        <thead><tr><th>ID</th><th>Typ</th><th>Status</th><th>Sprache</th><th>Revision</th><th>Basis / Composition</th><th>Aliase</th></tr></thead>
        <tbody>
          {objects.map((item) => (
            <tr key={item.id}>
              <td><code>{item.id}</code></td>
              <td>{item.type}</td>
              <td><span className={`badge badge-${item.status === 'approved' ? 'info' : 'warning'}`}>{item.status}</span></td>
              <td>{item.canonical_language}</td>
              <td>{item.current_revision}</td>
              <td>{item.base_template_id || item.composed_children?.join(', ') || '—'}</td>
              <td>{item.aliases?.join(', ') || '—'}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function CandidateReviewView({ candidates }: { candidates: Candidate[] }) {
  return (
    <div className="card">
      <SectionTitle>Candidate Review</SectionTitle>
      {candidates.map((candidate) => (
        <div key={candidate.candidate_id} className="card" style={{ marginBottom: 12 }}>
          <div className="section-header">
            <strong>{candidate.section_type}</strong>
            <span className="badge badge-warning">{candidate.status} · {(candidate.similarity * 100).toFixed(0)}%</span>
          </div>
          <p><strong>Quellen:</strong> {candidate.source_references.join(', ')}</p>
          <p><strong>Unterschiede:</strong> {candidate.differing_spans.map(([a, b]) => `${a} → ${b}`).join('; ')}</p>
          <p><strong>Vorgeschlagene Slots:</strong> {candidate.suggested_slots.join(', ')}</p>
          <div className="summary-bar summary-fail">Nicht freigegeben – kein automatischer Merge.</div>
        </div>
      ))}
    </div>
  );
}

function StructureMigrationReviewView({ migrations, currentUser }: { migrations: Migration[]; currentUser: string }) {
  const [comments, setComments] = useState<Record<string, string>>({});
  const [decisions, setDecisions] = useState<Record<string, string>>({});

  function decide(migration: Migration, decision: 'approved' | 'rejected' | 'changes_requested') {
    if (migration.created_by === currentUser) {
      setDecisions((old) => ({ ...old, [migration.migration_id]: 'Vier-Augen-Prinzip: Selbstentscheidung ist nicht erlaubt.' }));
      return;
    }
    if (decision !== 'approved' && !comments[migration.migration_id]?.trim()) {
      setDecisions((old) => ({ ...old, [migration.migration_id]: 'Kommentar ist für Ablehnung oder Änderungsanforderung erforderlich.' }));
      return;
    }
    setDecisions((old) => ({ ...old, [migration.migration_id]: decision }));
  }

  return (
    <div className="card">
      <SectionTitle>Structure Migration Review</SectionTitle>
      {migrations.map((migration) => (
        <div key={migration.migration_id} className="card" style={{ marginBottom: 12 }}>
          <p><strong>{migration.migration_id}</strong> · erstellt von {migration.created_by} · {migration.status}</p>
          <div className="three-panel-layout">
            <div className="panel"><div className="panel-header">Original</div>{migration.original_segments.map((text, index) => <p key={index}>{text}</p>)}</div>
            <div className="panel"><div className="panel-header">Vorschlag</div>{migration.proposed_segments.map((text, index) => <p key={index}>{text}</p>)}</div>
            <div className="panel"><div className="panel-header">Impact</div><p>{migration.impact_summary}</p></div>
          </div>
          <textarea
            aria-label={`Kommentar ${migration.migration_id}`}
            placeholder="Kommentar (optional bei Genehmigung, Pflicht bei Ablehnung/Änderungsanforderung)"
            value={comments[migration.migration_id] || ''}
            onChange={(event) => setComments((old) => ({ ...old, [migration.migration_id]: event.target.value }))}
            style={{ width: '100%', minHeight: 72, marginTop: 10 }}
          />
          <div className="panel-actions" style={{ display: 'flex', gap: 8 }}>
            <button className="btn-primary" onClick={() => decide(migration, 'approved')}>Genehmigen</button>
            <button className="btn-sm" onClick={() => decide(migration, 'changes_requested')}>Änderungen anfordern</button>
            <button className="btn-sm" onClick={() => decide(migration, 'rejected')}>Ablehnen</button>
          </div>
          {decisions[migration.migration_id] && <div className="summary-bar">{decisions[migration.migration_id]}</div>}
        </div>
      ))}
    </div>
  );
}

function IFUResolutionPreview({ payload }: { payload?: Record<string, unknown> }) {
  const [result, setResult] = useState<ResolutionResult | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');

  async function resolve() {
    if (!payload) {
      setError('Kein Resolver-Payload übergeben.');
      return;
    }
    setBusy(true); setError('');
    try {
      const response = await fetch(`${API_BASE}/api/v1/content/resolve`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload),
      });
      if (!response.ok) throw new Error(await response.text());
      setResult(await response.json() as ResolutionResult);
    } catch (reason) {
      setError(String(reason));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="card">
      <div className="section-header"><h2>IFU Resolution Preview</h2><button className="btn-primary" disabled={busy} onClick={resolve}>{busy ? 'Löse auf…' : 'Auflösen'}</button></div>
      {error && <div className="summary-bar summary-fail">{error}</div>}
      {result && (
        <>
          <div className={`summary-bar ${result.findings.some((item) => ['ERROR', 'FATAL'].includes(item.severity)) ? 'summary-fail' : 'summary-ok'}`}>
            {result.blocks.length} Blöcke · Config {result.config_hash.slice(0, 12)} · Checksum {result.checksum.slice(0, 12)}
          </div>
          {result.blocks.map((block) => (
            <div className="panel" key={block.block_id} style={{ marginBottom: 10 }}>
              <div className="panel-header">{block.block_id} · {block.source_object_id}@{block.source_revision}</div>
              <p>{block.rendered_content}</p>
              <small>Inheritance: {block.inheritance_path.join(' → ') || '—'} | Composition: {block.composition_path.join(' → ') || '—'}</small>
            </div>
          ))}
          {result.findings.length > 0 && (
            <table className="validation-table"><thead><tr><th>Level</th><th>Code</th><th>Meldung</th></tr></thead><tbody>
              {result.findings.map((finding, index) => <tr key={`${finding.code}-${index}`}><td>{finding.severity}</td><td>{finding.code}</td><td>{finding.message}</td></tr>)}
            </tbody></table>
          )}
          <details><summary>Provenienz</summary><pre>{JSON.stringify(result.provenance, null, 2)}</pre></details>
        </>
      )}
    </div>
  );
}

export default function Phase6Workspace({
  currentUser = 'reviewer-b',
  initialObjects = DEMO_OBJECTS,
  initialCandidates = DEMO_CANDIDATES,
  initialMigrations = DEMO_MIGRATIONS,
  resolvePayload,
}: Phase6WorkspaceProps) {
  const tabs = useMemo(() => ['library', 'candidates', 'migrations', 'resolution'] as const, []);
  const [tab, setTab] = useState<(typeof tabs)[number]>('library');

  return (
    <main style={{ maxWidth: 1400 }}>
      <div className="card">
        <div className="section-header"><h1>Phase 6 IFU Content Architecture</h1><span className="badge badge-info">deterministic foundation</span></div>
        <div className="nav-links" style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
          {tabs.map((name) => <button key={name} className={`nav-btn ${tab === name ? 'nav-btn-active' : ''}`} onClick={() => setTab(name)}>{name}</button>)}
        </div>
      </div>
      {tab === 'library' && <ContentLibraryView objects={initialObjects} />}
      {tab === 'candidates' && <CandidateReviewView candidates={initialCandidates} />}
      {tab === 'migrations' && <StructureMigrationReviewView migrations={initialMigrations} currentUser={currentUser} />}
      {tab === 'resolution' && <IFUResolutionPreview payload={resolvePayload} />}
    </main>
  );
}
