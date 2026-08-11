import React, { useEffect, useMemo, useState } from 'react';

const API_BASE = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8080';

type Session = { user_id: string; role: 'author' | 'reviewer' | 'approver' };
type TranslationBinding = { content_object_id: string; target_language: string; variant_id: string; revision: number; canonical_revision: number };
type TranslationVariant = { id: string; content_object_id: string; canonical_revision: number; target_language: string; revision: number; status: string; created_by?: string; status_changed_by?: string };
type ContentObject = { id: string; canonical_language: string };
type ReleaseSummary = {
  release_id: string; product_id: string; language: string; version: number; created_at: string; created_by: string; release_checksum: string;
  translation_bindings?: TranslationBinding[];
  provenance?: { resolution_mode?: string; resolution_checksum?: string; release_candidate_id?: string; release_candidate_checksum?: string };
};
type ReleaseCandidate = {
  candidate_id: string; release_id: string; version: number; product_id: string; language: string; payload_checksum: string;
  created_at: string; created_by: string; status: 'candidate' | 'approved' | 'rejected' | 'released'; status_changed_by?: string;
};
type Props = { resolvePayload?: Record<string, unknown> };
type SelectionMap = Record<string, string>;
type TranslationSelectionRow = { content_object_id: string; variant_id: string; revision: number };

function errorDetail(raw: string): string {
  try {
    const parsed = JSON.parse(raw) as { detail?: string | { message?: string; findings?: Array<{ message?: string }> } };
    if (typeof parsed.detail === 'string') return parsed.detail;
    if (parsed.detail && typeof parsed.detail === 'object') {
      const findingText = parsed.detail.findings?.map((item) => item.message).filter(Boolean).join('; ');
      return findingText || parsed.detail.message || raw;
    }
  } catch {
    // Keep raw response text.
  }
  return raw;
}

function variantKey(variant: TranslationVariant): string { return `${variant.id}@@${variant.revision}`; }

export default function Phase6ReleaseWorkflow({ resolvePayload }: Props) {
  const [session, setSession] = useState<Session | null>(null);
  const [productId, setProductId] = useState('elisa-demo');
  const [language, setLanguage] = useState('de-DE');
  const [version, setVersion] = useState(1);
  const [candidateId, setCandidateId] = useState('');
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState('');
  const [releases, setReleases] = useState<ReleaseSummary[]>([]);
  const [candidates, setCandidates] = useState<ReleaseCandidate[]>([]);
  const [candidateComments, setCandidateComments] = useState<Record<string, string>>({});
  const [variants, setVariants] = useState<TranslationVariant[]>([]);
  const [translationSelections, setTranslationSelections] = useState<SelectionMap>({});
  const [variantsBusy, setVariantsBusy] = useState(false);

  const pinned = resolvePayload?.revision_mode === 'pinned';
  const objects = useMemo(() => (resolvePayload?.objects || []) as ContentObject[], [resolvePayload]);
  const pins = useMemo(() => (resolvePayload?.pinned_revisions || {}) as Record<string, number>, [resolvePayload]);
  const releaseId = useMemo(() => `${productId}-${language}-v${version}`.replace(/[^A-Za-z0-9_.-]+/g, '-'), [productId, language, version]);

  useEffect(() => { setCandidateId(`${releaseId}-candidate`); }, [releaseId]);

  const requiredTranslations = useMemo(() => objects
    .filter((item) => item.canonical_language && item.canonical_language !== language)
    .map((item) => ({ object: item, canonicalRevision: pins[item.id] }))
    .filter((item) => Number.isInteger(item.canonicalRevision) && item.canonicalRevision > 0), [objects, language, pins]);

  const missingTranslations = useMemo(() => requiredTranslations.filter(({ object, canonicalRevision }) => {
    const selected = translationSelections[object.id];
    if (!selected) return true;
    const candidate = variants.find((variant) => variantKey(variant) === selected);
    return !candidate || candidate.status !== 'approved' || candidate.target_language !== language || candidate.canonical_revision !== canonicalRevision;
  }), [requiredTranslations, translationSelections, variants, language]);

  const blockingHint = useMemo(() => {
    if (!resolvePayload) return 'Kein Resolver-Payload vorhanden.';
    if (!pinned) return 'Candidate gesperrt: Resolver muss im Modus pinned laufen.';
    if (variantsBusy && requiredTranslations.length > 0) return 'Freigegebene Übersetzungen werden geladen…';
    if (missingTranslations.length > 0) return `Candidate gesperrt: ${missingTranslations.length} persistierte Übersetzung(en) müssen explizit freigegeben und gepinnt werden.`;
    return '';
  }, [resolvePayload, pinned, variantsBusy, requiredTranslations.length, missingTranslations]);

  useEffect(() => {
    setTranslationSelections((current) => {
      const next: SelectionMap = {};
      for (const { object, canonicalRevision } of requiredTranslations) {
        const existing = current[object.id];
        const validExisting = variants.find((variant) => variantKey(variant) === existing
          && variant.status === 'approved' && variant.target_language === language && variant.canonical_revision === canonicalRevision);
        if (validExisting) next[object.id] = existing;
      }
      return next;
    });
  }, [language, requiredTranslations, variants]);

  async function loadSession() {
    const response = await fetch(`${API_BASE}/api/v1/session`);
    if (!response.ok) throw new Error(errorDetail(await response.text()));
    setSession(await response.json() as Session);
  }

  async function loadReleases() {
    const response = await fetch(`${API_BASE}/api/v1/ifu/releases`);
    if (!response.ok) throw new Error(errorDetail(await response.text()));
    const body = await response.json() as { releases?: ReleaseSummary[] };
    setReleases(body.releases || []);
  }

  async function loadCandidates() {
    const response = await fetch(`${API_BASE}/api/v1/ifu/release-candidates`);
    if (!response.ok) throw new Error(errorDetail(await response.text()));
    const body = await response.json() as { candidates?: ReleaseCandidate[] };
    setCandidates(body.candidates || []);
  }

  async function loadVariants(targetLanguage: string) {
    if (!targetLanguage.trim()) { setVariants([]); return; }
    setVariantsBusy(true);
    try {
      const params = new URLSearchParams({ target_language: targetLanguage, status: 'approved' });
      const response = await fetch(`${API_BASE}/api/v1/translations/variants?${params.toString()}`);
      if (!response.ok) throw new Error(errorDetail(await response.text()));
      const body = await response.json() as { variants?: TranslationVariant[] };
      setVariants(body.variants || []);
    } finally { setVariantsBusy(false); }
  }

  useEffect(() => {
    void Promise.all([loadSession(), loadReleases(), loadCandidates()]).catch((reason) => setMessage(String(reason)));
  }, []);
  useEffect(() => { void loadVariants(language).catch((reason) => setMessage(String(reason))); }, [language]);

  function selectedRows(): TranslationSelectionRow[] {
    const rows: TranslationSelectionRow[] = [];
    for (const { object } of requiredTranslations) {
      const selected = translationSelections[object.id];
      const variant = variants.find((item) => variantKey(item) === selected);
      if (variant) rows.push({ content_object_id: object.id, variant_id: variant.id, revision: variant.revision });
    }
    return rows;
  }

  async function validateContent() {
    const validation = await fetch(`${API_BASE}/api/v1/content/validate`, {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ objects: resolvePayload?.objects || [], pinned_revisions: resolvePayload?.pinned_revisions || {}, slot_values: resolvePayload?.slot_values || {} }),
    });
    if (!validation.ok) throw new Error(errorDetail(await validation.text()));
    const body = await validation.json() as { valid?: boolean; issues?: Array<{ message?: string }> };
    if (!body.valid) throw new Error(body.issues?.map((item) => item.message).filter(Boolean).join('; ') || 'Validierung fehlgeschlagen.');
  }

  async function createCandidate() {
    if (!resolvePayload || !pinned || variantsBusy || missingTranslations.length > 0) { setMessage(blockingHint); return; }
    setBusy(true); setMessage('');
    try {
      await validateContent();
      const response = await fetch(`${API_BASE}/api/v1/ifu/release-candidates`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          ...resolvePayload,
          candidate_id: candidateId,
          release_id: releaseId,
          product_id: productId,
          language,
          version,
          revision_mode: 'pinned',
          configuration_parameters: resolvePayload.configuration_parameters || [],
          configuration_values: resolvePayload.configuration_values || [],
          translation_selections: selectedRows(),
        }),
      });
      if (!response.ok) throw new Error(errorDetail(await response.text()));
      const candidate = await response.json() as ReleaseCandidate;
      setMessage(`Candidate gespeichert: ${candidate.candidate_id} · ${candidate.payload_checksum.slice(0, 16)}…`);
      await loadCandidates();
    } catch (reason) { setMessage(String(reason)); } finally { setBusy(false); }
  }

  async function decide(candidate: ReleaseCandidate, decision: 'approved' | 'rejected') {
    setBusy(true); setMessage('');
    try {
      const response = await fetch(`${API_BASE}/api/v1/ifu/release-candidates/${encodeURIComponent(candidate.candidate_id)}/decision`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ decision, comment: candidateComments[candidate.candidate_id] || '' }),
      });
      if (!response.ok) throw new Error(errorDetail(await response.text()));
      setCandidateComments((old) => ({ ...old, [candidate.candidate_id]: '' }));
      setMessage(`${candidate.candidate_id} → ${decision}`);
      await loadCandidates();
    } catch (reason) { setMessage(String(reason)); } finally { setBusy(false); }
  }

  async function publish(candidate: ReleaseCandidate) {
    setBusy(true); setMessage('');
    try {
      const response = await fetch(`${API_BASE}/api/v1/ifu/releases`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ candidate_id: candidate.candidate_id }),
      });
      if (!response.ok) throw new Error(errorDetail(await response.text()));
      const release = await response.json() as ReleaseSummary;
      setMessage(`Release publiziert: ${release.release_id} · ${release.release_checksum.slice(0, 16)}…`);
      await Promise.all([loadCandidates(), loadReleases()]);
    } catch (reason) { setMessage(String(reason)); } finally { setBusy(false); }
  }

  return (
    <div className="card" style={{ marginTop: 12 }}>
      <div className="section-header">
        <h2>Release Governance</h2>
        <span className="badge badge-info">{session ? `${session.user_id} · ${session.role}` : 'identity loading'}</span>
      </div>
      <p>Release-Daten werden zuerst als unveränderlicher Candidate eingefroren. Ein anderer Approver genehmigt exakt diesen Checksum-Stand; erst danach kann derselbe Candidate ohne weitere Inhaltsparameter publiziert werden.</p>

      <div className="three-panel-layout">
        <label className="panel">Produkt-ID<input value={productId} onChange={(event) => setProductId(event.target.value)} style={{ width: '100%' }} /></label>
        <label className="panel">Sprache<input value={language} onChange={(event) => setLanguage(event.target.value)} style={{ width: '100%' }} /></label>
        <label className="panel">Version<input type="number" min={1} value={version} onChange={(event) => setVersion(Math.max(1, Number(event.target.value) || 1))} style={{ width: '100%' }} /></label>
      </div>
      <label>Candidate-ID<input value={candidateId} onChange={(event) => setCandidateId(event.target.value)} style={{ width: '100%' }} /></label>
      <p><strong>Geplanter Release:</strong> <code>{releaseId}</code> · Version {version}</p>

      {requiredTranslations.length > 0 && (
        <div className="card" style={{ marginTop: 12 }}>
          <div className="section-header"><strong>Translation Pins</strong><span className="badge badge-info">persistenter Katalog</span></div>
          <table className="validation-table">
            <thead><tr><th>Content Object</th><th>Kanonisch</th><th>Zielsprache</th><th>Persistierte Translation Variant</th></tr></thead>
            <tbody>{requiredTranslations.map(({ object, canonicalRevision }) => {
              const available = variants.filter((variant) => variant.content_object_id === object.id && variant.target_language === language && variant.canonical_revision === canonicalRevision && variant.status === 'approved');
              return <tr key={object.id}><td><code>{object.id}</code></td><td>{object.canonical_language} @ {canonicalRevision}</td><td>{language}</td><td>
                <select value={translationSelections[object.id] || ''} onChange={(event) => setTranslationSelections((old) => ({ ...old, [object.id]: event.target.value }))} style={{ width: '100%' }} disabled={variantsBusy}>
                  <option value="">— explizit auswählen —</option>
                  {available.map((variant) => <option key={variantKey(variant)} value={variantKey(variant)}>{variant.id}@{variant.revision} · approved</option>)}
                </select>
                {!variantsBusy && available.length === 0 && <small>Keine freigegebene Variante vorhanden.</small>}
              </td></tr>;
            })}</tbody>
          </table>
        </div>
      )}

      {blockingHint && <div className="summary-bar summary-fail">{blockingHint}</div>}
      <div className="panel-actions" style={{ marginTop: 10 }}>
        <button className="btn-primary" disabled={busy || variantsBusy || !pinned || missingTranslations.length > 0 || !candidateId.trim() || !productId.trim() || !language.trim()} onClick={() => void createCandidate()}>
          {busy ? 'Verarbeite…' : 'Release Candidate einfrieren'}
        </button>
      </div>
      {message && <div className="summary-bar" style={{ marginTop: 10 }}>{message}</div>}

      <details open style={{ marginTop: 12 }}>
        <summary>Release Candidates ({candidates.length})</summary>
        {candidates.length === 0 ? <p>Noch keine Candidates gespeichert.</p> : <table className="validation-table">
          <thead><tr><th>Candidate</th><th>Release</th><th>Status</th><th>Ersteller</th><th>Checksum</th><th>Aktionen</th></tr></thead>
          <tbody>{candidates.map((candidate) => {
            const canDecide = session?.role === 'approver' && candidate.status === 'candidate' && candidate.created_by !== session.user_id;
            const canPublish = session?.role === 'approver' && candidate.status === 'approved';
            return <tr key={candidate.candidate_id}>
              <td><code>{candidate.candidate_id}</code></td>
              <td><code>{candidate.release_id}</code> · v{candidate.version}</td>
              <td><span className={`badge ${candidate.status === 'released' || candidate.status === 'approved' ? 'badge-info' : 'badge-warning'}`}>{candidate.status}</span></td>
              <td>{candidate.created_by}</td>
              <td><code>{candidate.payload_checksum.slice(0, 16)}…</code></td>
              <td>
                {canDecide && <><div className="panel-actions" style={{ display: 'flex', gap: 6 }}>
                  <button className="btn-primary" disabled={busy} onClick={() => void decide(candidate, 'approved')}>Genehmigen</button>
                  <button className="btn-sm" disabled={busy} onClick={() => void decide(candidate, 'rejected')}>Ablehnen</button>
                </div><input value={candidateComments[candidate.candidate_id] || ''} onChange={(event) => setCandidateComments((old) => ({ ...old, [candidate.candidate_id]: event.target.value }))} placeholder="Kommentar (Pflicht bei Ablehnung)" style={{ width: '100%', marginTop: 6 }} /></>}
                {canPublish && <button className="btn-primary" disabled={busy} onClick={() => void publish(candidate)}>Publizieren</button>}
                {!canDecide && !canPublish && '—'}
              </td>
            </tr>;
          })}</tbody>
        </table>}
      </details>

      <details style={{ marginTop: 12 }}>
        <summary>Release-Historie ({releases.length})</summary>
        {releases.length === 0 ? <p>Noch keine Releases gespeichert.</p> : <table className="validation-table">
          <thead><tr><th>Release</th><th>Produkt</th><th>Sprache</th><th>Version</th><th>Candidate</th><th>Erstellt von</th><th>Checksum</th></tr></thead>
          <tbody>{releases.map((release) => <tr key={release.release_id}>
            <td><code>{release.release_id}</code></td><td>{release.product_id}</td><td>{release.language}</td><td>{release.version}</td>
            <td><code>{release.provenance?.release_candidate_id || '—'}</code></td><td>{release.created_by}</td><td><code>{release.release_checksum.slice(0, 16)}…</code></td>
          </tr>)}</tbody>
        </table>}
      </details>
    </div>
  );
}
