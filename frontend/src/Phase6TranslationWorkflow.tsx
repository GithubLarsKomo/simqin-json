import React, { useEffect, useMemo, useState } from 'react';

const API_BASE = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8080';

type Session = { user_id: string; role: 'author' | 'reviewer' | 'approver' };
type Segment = { segment_id: string; source_text: string; order: number; segment_type?: string };
type ContentRevision = { revision: number; sentence_segments?: Segment[] };
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
type HistoryEvent = { event_id: number; status: string; changed_at: string; changed_by: string; comment: string };
type Props = { resolvePayload?: Record<string, unknown> };

function detail(raw: string): string {
  try {
    const parsed = JSON.parse(raw) as { detail?: string | { message?: string } };
    if (typeof parsed.detail === 'string') return parsed.detail;
    if (parsed.detail && typeof parsed.detail === 'object') return parsed.detail.message || raw;
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

  useEffect(() => {
    void Promise.all([loadSession(), loadVariants()]).catch((reason) => setMessage(String(reason)));
  }, []);

  async function createVariant() {
    if (!selectedObject || !canonicalRevision || sourceSegments.length === 0) {
      setMessage('Für die gewählte gepinnte Revision sind keine Source-Segmente verfügbar.');
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

  async function transition(variant: TranslationVariant, status: 'reviewed' | 'approved' | 'rejected' | 'superseded') {
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

  function allowedActions(variant: TranslationVariant) {
    if (!session) return [] as Array<'reviewed' | 'approved' | 'rejected' | 'superseded'>;
    if (variant.status === 'generated' && ['reviewer', 'approver'].includes(session.role)) return ['reviewed', 'rejected'];
    if (variant.status === 'reviewed' && session.role === 'approver') return ['approved', 'rejected'];
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
        <p>Translation-Inhalte sind revisionsfest gespeichert; Statusänderungen werden append-only protokolliert. Die UI blendet nur rollenkompatible Aktionen ein, der Server erzwingt die Policy zusätzlich.</p>

        {session?.role === 'author' && (
          <div className="card" style={{ marginBottom: 12 }}>
            <div className="section-header"><strong>Neue Translation Revision</strong><span className="badge badge-warning">generated</span></div>
            <div className="three-panel-layout">
              <label className="panel">Content Object
                <select value={selectedObjectId} onChange={(event) => setSelectedObjectId(event.target.value)} style={{ width: '100%' }}>
                  {objects.map((item) => <option key={item.id} value={item.id}>{item.id}</option>)}
                </select>
              </label>
              <label className="panel">Zielsprache<input value={targetLanguage} onChange={(event) => setTargetLanguage(event.target.value)} style={{ width: '100%' }} /></label>
              <label className="panel">Translation Revision<input type="number" min={1} value={translationRevision} onChange={(event) => setTranslationRevision(Math.max(1, Number(event.target.value) || 1))} style={{ width: '100%' }} /></label>
            </div>
            <label>Variant-ID<input value={variantId} onChange={(event) => setVariantId(event.target.value)} style={{ width: '100%' }} /></label>
            <p><strong>Kanonische Revision:</strong> {canonicalRevision || 'nicht gepinnt'}</p>
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
            <button className="btn-primary" disabled={busy || !variantId.trim() || !targetLanguage.trim() || sourceSegments.length === 0} onClick={() => void createVariant()}>
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
