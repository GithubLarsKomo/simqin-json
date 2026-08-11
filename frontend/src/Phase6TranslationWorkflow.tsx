import React, { useEffect, useMemo, useState } from 'react';

const API_BASE = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8080';

type Session = { user_id: string; role: 'author' | 'reviewer' | 'approver' };
type Segment = { segment_id: string; source_text: string; order: number; segment_type?: string };
type ContentRevision = {
  revision: number;
  canonical_content?: string;
  sentence_segments?: Segment[];
  approval_status?: string;
  [key: string]: unknown;
};
type ContentObject = { id: string; canonical_language: string; revisions?: ContentRevision[] };
type TranslationSegment = { segment_id: string; source_text?: string; translated_text: string; order: number };
type TranslationVariant = {
  id: string;
  content_object_id: string;
  canonical_revision: number;
  target_language: string;
  revision: number;
  status: string;
  created_by?: string;
  status_changed_by?: string;
  segment_translations?: TranslationSegment[];
};
type CanonicalSnapshot = {
  object_id: string;
  revision: number;
  canonical_language: string;
  approval_status: string;
  payload_checksum: string;
  registered_by: string;
  registered_at: string;
};
type HistoryEvent = { event_id: number; status: string; changed_at: string; changed_by: string; comment: string };
type Props = { resolvePayload?: Record<string, unknown> };
type TranslationAction = 'reviewed' | 'approved' | 'rejected' | 'superseded';

function detail(raw: string): string {
  try {
    const parsed = JSON.parse(raw) as { detail?: string | { message?: string; findings?: Array<{ message?: string }> } };
    if (typeof parsed.detail === 'string') return parsed.detail;
    if (parsed.detail && typeof parsed.detail === 'object') {
      const findings = parsed.detail.findings?.map((item) => item.message).filter(Boolean).join('; ');
      return findings || parsed.detail.message || raw;
    }
  } catch {
    // Keep raw text.
  }
  return raw;
}

export default function Phase6TranslationWorkflow({ resolvePayload }: Props) {
  const objects = useMemo(() => (resolvePayload?.objects || []) as ContentObject[], [resolvePayload]);
  const pins = useMemo(() => (resolvePayload?.pinned_revisions || {}) as Record<string, number>, [resolvePayload]);
  const [session, setSession] = useState<Session | null>(null);
  const [variants, setVariants] = useState<TranslationVariant[]>([]);
  const [snapshots, setSnapshots] = useState<CanonicalSnapshot[]>([]);
  const [selectedObjectId, setSelectedObjectId] = useState(objects[0]?.id || '');
  const [targetLanguage, setTargetLanguage] = useState('en-US');
  const [variantId, setVariantId] = useState('');
  const [translationRevision, setTranslationRevision] = useState(1);
  const [translations, setTranslations] = useState<Record<string, string>>({});
  const [comments, setComments] = useState<Record<string, string>>({});
  const [history, setHistory] = useState<Record<string, HistoryEvent[]>>({});
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState('');

  const selectedObject = objects.find((item) => item.id === selectedObjectId);
  const canonicalRevision = selectedObjectId ? pins[selectedObjectId] : undefined;
  const sourceRevision = selectedObject?.revisions?.find((item) => item.revision === canonicalRevision);
  const sourceSegments = sourceRevision?.sentence_segments || [];
  const trustedSnapshot = snapshots.find((item) => item.object_id === selectedObjectId && item.revision === canonicalRevision);

  useEffect(() => {
    if (!selectedObjectId && objects[0]) setSelectedObjectId(objects[0].id);
  }, [objects, selectedObjectId]);

  useEffect(() => {
    if (selectedObjectId && targetLanguage) {
      const normalized = `${selectedObjectId}-${targetLanguage}`.replace(/[^A-Za-z0-9_.-]+/g, '-');
      setVariantId(`tr-${normalized}`);
    }
  }, [selectedObjectId, targetLanguage]);

  async function loadSession() {
    const response = await fetch(`${API_BASE}/api/v1/session`);
    if (!response.ok) throw new Error(detail(await response.text()));
    setSession(await response.json() as Session);
  }

  async function loadVariants() {
    const response = await fetch(`${API_BASE}/api/v1/translations/variants`);
    if (!response.ok) throw new Error(detail(await response.text()));
    const body = await response.json() as { variants?: TranslationVariant[] };
    setVariants(body.variants || []);
  }

  async function loadSnapshots() {
    const response = await fetch(`${API_BASE}/api/v1/content/canonical-snapshots`);
    if (!response.ok) throw new Error(detail(await response.text()));
    const body = await response.json() as { snapshots?: CanonicalSnapshot[] };
    setSnapshots(body.snapshots || []);
  }

  useEffect(() => {
    void Promise.all([loadSession(), loadVariants(), loadSnapshots()]).catch((reason) => setMessage(String(reason)));
  }, []);

  async function registerCanonicalSource() {
    if (!selectedObject || !canonicalRevision || !sourceRevision) {
      setMessage('Für das gewählte Content Object ist keine gepinnte Source-Revision verfügbar.');
      return;
    }
    if (sourceRevision.approval_status !== 'approved') {
      setMessage('Nur eine bereits freigegebene kanonische Revision kann als Source-Snapshot registriert werden.');
      return;
    }
    setBusy(true); setMessage('');
    try {
      const response = await fetch(`${API_BASE}/api/v1/content/canonical-snapshots`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          object_id: selectedObject.id,
          canonical_language: selectedObject.canonical_language,
          revision: sourceRevision,
        }),
      });
      if (!response.ok) throw new Error(detail(await response.text()));
      const created = await response.json() as CanonicalSnapshot;
      setMessage(`Trusted Source registriert: ${created.object_id}@${created.revision} · ${created.payload_checksum.slice(0, 16)}…`);
      await loadSnapshots();
    } catch (reason) {
      setMessage(String(reason));
    } finally {
      setBusy(false);
    }
  }

  async function createVariant() {
    if (!selectedObject || !canonicalRevision || sourceSegments.length === 0) {
      setMessage('Für die gewählte gepinnte Revision sind keine Source-Segmente verfügbar.');
      return;
    }
    if (!trustedSnapshot) {
      setMessage('Die kanonische Source-Revision muss zuerst durch einen Approver als trusted Snapshot registriert werden.');
      return;
    }
    setBusy(true); setMessage('');
    try {
      const response = await fetch(`${API_BASE}/api/v1/translations/variants`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ variant: {
          id: variantId,
          content_object_id: selectedObject.id,
          canonical_revision: canonicalRevision,
          target_language: targetLanguage,
          revision: translationRevision,
          status: 'generated',
          segment_translations: sourceSegments.map((segment, index) => ({
            segment_id: segment.segment_id,
            source_text: segment.source_text,
            translated_text: translations[segment.segment_id] || '',
            order: segment.order ?? index,
          })),
        } }),
      });
      if (!response.ok) throw new Error(detail(await response.text()));
      const created = await response.json() as TranslationVariant;
      setMessage(`Translation gespeichert: ${created.id}@${created.revision} · generated`);
      await loadVariants();
    } catch (reason) {
      setMessage(String(reason));
    } finally {
      setBusy(false);
    }
  }

  function keyOf(variant: TranslationVariant) { return `${variant.id}@${variant.revision}`; }

  async function loadHistory(variant: TranslationVariant) {
    const key = keyOf(variant);
    try {
      const response = await fetch(`${API_BASE}/api/v1/translations/variants/${encodeURIComponent(variant.id)}/${variant.revision}/history`);
      if (!response.ok) throw new Error(detail(await response.text()));
      const body = await response.json() as { events?: HistoryEvent[] };
      setHistory((current) => ({ ...current, [key]: body.events || [] }));
    } catch (reason) {
      setMessage(String(reason));
    }
  }

  async function transition(variant: TranslationVariant, status: TranslationAction) {
    const key = keyOf(variant);
    setBusy(true); setMessage('');
    try {
      const response = await fetch(`${API_BASE}/api/v1/translations/variants/${encodeURIComponent(variant.id)}/${variant.revision}/status`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ status, comment: comments[key] || '' }),
      });
      if (!response.ok) throw new Error(detail(await response.text()));
      const updated = await response.json() as TranslationVariant;
      setMessage(`${updated.id}@${updated.revision} → ${updated.status}`);
      setComments((current) => ({ ...current, [key]: '' }));
      await loadVariants();
      await loadHistory(updated);
    } catch (reason) {
      setMessage(String(reason));
    } finally {
      setBusy(false);
    }
  }

  function allowedActions(variant: TranslationVariant): TranslationAction[] {
    if (!session) return [];
    const isCreator = variant.created_by === session.user_id;
    const isLastReviewer = variant.status === 'reviewed' && variant.status_changed_by === session.user_id;
    if (variant.status === 'generated' && !isCreator && ['reviewer', 'approver'].includes(session.role)) {
      return ['reviewed', 'rejected'];
    }
    if (variant.status === 'reviewed' && session.role === 'approver' && !isCreator && !isLastReviewer) {
      return ['approved', 'rejected'];
    }
    if (variant.status === 'approved' && session.role === 'approver') return ['superseded'];
    return [];
  }

  return (
    <main style={{ maxWidth: 1400 }}>
      <div className="card" style={{ marginTop: 12 }}>
        <div className="section-header">
          <h2>Translation Workflow</h2>
          <span className="badge badge-info">{session ? `${session.user_id} · ${session.role}` : 'identity loading'}</span>
        </div>
        <p>Translation-Inhalte sind revisionsfest gespeichert und werden bei Review sowie Freigabe erneut gegen einen immutable, serverseitig registrierten kanonischen Source-Snapshot validiert.</p>

        <div className="card" style={{ marginBottom: 12 }}>
          <div className="section-header">
            <strong>Canonical Source Trust</strong>
            <span className={`badge ${trustedSnapshot ? 'badge-info' : 'badge-warning'}`}>
              {trustedSnapshot ? 'trusted snapshot' : 'not registered'}
            </span>
          </div>
          <div className="three-panel-layout">
            <label className="panel">Content Object
              <select value={selectedObjectId} onChange={(event) => setSelectedObjectId(event.target.value)} style={{ width: '100%' }}>
                {objects.map((item) => <option key={item.id} value={item.id}>{item.id}</option>)}
              </select>
            </label>
            <div className="panel"><strong>Kanonisch</strong><p>{selectedObject?.canonical_language || '—'} @ {canonicalRevision || '—'}</p></div>
            <div className="panel"><strong>Source-Status</strong><p>{sourceRevision?.approval_status || '—'}</p></div>
          </div>
          {trustedSnapshot ? (
            <small>Registriert von {trustedSnapshot.registered_by} · Checksum <code>{trustedSnapshot.payload_checksum.slice(0, 16)}…</code></small>
          ) : session?.role === 'approver' ? (
            <button className="btn-primary" disabled={busy || !sourceRevision || sourceRevision.approval_status !== 'approved'} onClick={() => void registerCanonicalSource()}>
              Gepinnte Revision als trusted Source registrieren
            </button>
          ) : (
            <div className="summary-bar summary-fail">Ein Approver muss diese gepinnte kanonische Revision zuerst registrieren.</div>
          )}
        </div>

        {session?.role === 'author' && (
          <div className="card" style={{ marginBottom: 12 }}>
            <div className="section-header"><strong>Neue Translation Revision</strong><span className="badge badge-warning">generated</span></div>
            <div className="three-panel-layout">
              <label className="panel">Zielsprache<input value={targetLanguage} onChange={(event) => setTargetLanguage(event.target.value)} style={{ width: '100%' }} /></label>
              <label className="panel">Translation Revision<input type="number" min={1} value={translationRevision} onChange={(event) => setTranslationRevision(Math.max(1, Number(event.target.value) || 1))} style={{ width: '100%' }} /></label>
              <div className="panel"><strong>Trusted Source</strong><p>{trustedSnapshot ? 'ja' : 'nein'}</p></div>
            </div>
            <label>Variant-ID<input value={variantId} onChange={(event) => setVariantId(event.target.value)} style={{ width: '100%' }} /></label>
            {sourceSegments.map((segment) => (
              <div className="panel" key={segment.segment_id} style={{ marginBottom: 8 }}>
                <div className="panel-header"><code>{segment.segment_id}</code></div>
                <p>{segment.source_text}</p>
                <textarea
                  aria-label={`Übersetzung ${segment.segment_id}`}
                  value={translations[segment.segment_id] || ''}
                  onChange={(event) => setTranslations((current) => ({ ...current, [segment.segment_id]: event.target.value }))}
                  placeholder="Übersetzung"
                  style={{ width: '100%', minHeight: 72 }}
                />
              </div>
            ))}
            <button className="btn-primary" disabled={busy || !trustedSnapshot || !variantId.trim() || !targetLanguage.trim() || sourceSegments.length === 0} onClick={() => void createVariant()}>
              Translation Revision speichern
            </button>
          </div>
        )}

        {message && <div className="summary-bar" style={{ marginBottom: 10 }}>{message}</div>}

        <table className="validation-table">
          <thead><tr><th>Variant</th><th>Content</th><th>Sprache</th><th>Status</th><th>Creator</th><th>Aktionen</th></tr></thead>
          <tbody>{variants.map((variant) => {
            const key = keyOf(variant);
            const actions = allowedActions(variant);
            return (
              <React.Fragment key={key}>
                <tr>
                  <td><code>{key}</code></td>
                  <td><code>{variant.content_object_id}@{variant.canonical_revision}</code></td>
                  <td>{variant.target_language}</td>
                  <td><span className={`badge ${variant.status === 'approved' ? 'badge-info' : 'badge-warning'}`}>{variant.status}</span></td>
                  <td>{variant.created_by || '—'}</td>
                  <td>
                    <div className="panel-actions" style={{ display: 'flex', gap: 6, flexWrap: 'wrap' }}>
                      {actions.includes('reviewed') && <button className="btn-sm" disabled={busy} onClick={() => void transition(variant, 'reviewed')}>Review abschließen</button>}
                      {actions.includes('approved') && <button className="btn-primary" disabled={busy} onClick={() => void transition(variant, 'approved')}>Freigeben</button>}
                      {actions.includes('rejected') && <button className="btn-sm" disabled={busy} onClick={() => void transition(variant, 'rejected')}>Ablehnen</button>}
                      {actions.includes('superseded') && <button className="btn-sm" disabled={busy} onClick={() => void transition(variant, 'superseded')}>Ersetzen</button>}
                      <button className="btn-sm" onClick={() => void loadHistory(variant)}>Historie</button>
                    </div>
                    {(actions.includes('rejected') || actions.includes('superseded')) && (
                      <input
                        value={comments[key] || ''}
                        onChange={(event) => setComments((current) => ({ ...current, [key]: event.target.value }))}
                        placeholder="Kommentar für Ablehnung/Ersetzen"
                        style={{ width: '100%', marginTop: 6 }}
                      />
                    )}
                  </td>
                </tr>
                {history[key] && (
                  <tr><td colSpan={6}>
                    <strong>Statushistorie</strong>
                    <ul>{history[key].map((event) => <li key={event.event_id}>{event.changed_at} · {event.changed_by} · {event.status}{event.comment ? ` · ${event.comment}` : ''}</li>)}</ul>
                  </td></tr>
                )}
              </React.Fragment>
            );
          })}</tbody>
        </table>
      </div>
    </main>
  );
}
