import React, { useEffect, useMemo, useState } from 'react';

const API_BASE = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8080';

type ReleaseSummary = {
  release_id: string;
  product_id: string;
  language: string;
  version: number;
  created_at: string;
  created_by: string;
  release_checksum: string;
  provenance?: { resolution_mode?: string; resolution_checksum?: string };
};

type Props = {
  resolvePayload?: Record<string, unknown>;
};

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

export default function Phase6ReleaseWorkflow({ resolvePayload }: Props) {
  const [productId, setProductId] = useState('elisa-demo');
  const [language, setLanguage] = useState('de-DE');
  const [version, setVersion] = useState(1);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState('');
  const [releases, setReleases] = useState<ReleaseSummary[]>([]);

  const pinned = resolvePayload?.revision_mode === 'pinned';
  const blockingHint = useMemo(() => {
    if (!resolvePayload) return 'Kein Resolver-Payload vorhanden.';
    if (!pinned) return 'Release gesperrt: Resolver muss im Modus pinned laufen.';
    return '';
  }, [resolvePayload, pinned]);

  async function loadReleases() {
    try {
      const response = await fetch(`${API_BASE}/api/v1/ifu/releases`);
      if (!response.ok) throw new Error(errorDetail(await response.text()));
      const body = await response.json() as { releases?: ReleaseSummary[] };
      setReleases(body.releases || []);
    } catch (reason) {
      setMessage(`Release-Historie konnte nicht geladen werden: ${String(reason)}`);
    }
  }

  useEffect(() => { void loadReleases(); }, []);

  async function validateAndRelease() {
    if (!resolvePayload || !pinned) {
      setMessage(blockingHint);
      return;
    }
    setBusy(true);
    setMessage('');
    try {
      const validation = await fetch(`${API_BASE}/api/v1/content/validate`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          objects: resolvePayload.objects || [],
          pinned_revisions: resolvePayload.pinned_revisions || {},
          slot_values: resolvePayload.slot_values || {},
        }),
      });
      if (!validation.ok) throw new Error(errorDetail(await validation.text()));
      const validationBody = await validation.json() as { valid?: boolean; issues?: Array<{ message?: string }> };
      if (!validationBody.valid) {
        const details = validationBody.issues?.map((item) => item.message).filter(Boolean).join('; ') || 'Validierung fehlgeschlagen.';
        throw new Error(details);
      }

      const releaseId = `${productId}-${language}-v${version}`.replace(/[^A-Za-z0-9_.-]+/g, '-');
      const response = await fetch(`${API_BASE}/api/v1/ifu/releases`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          ...resolvePayload,
          release_id: releaseId,
          product_id: productId,
          language,
          version,
          revision_mode: 'pinned',
          configuration_parameters: [],
          configuration_values: [],
        }),
      });
      if (!response.ok) throw new Error(errorDetail(await response.text()));
      const release = await response.json() as ReleaseSummary;
      setMessage(`Release gespeichert: ${release.release_id} · ${release.release_checksum.slice(0, 16)}…`);
      await loadReleases();
    } catch (reason) {
      setMessage(String(reason));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="card" style={{ marginTop: 12 }}>
      <div className="section-header">
        <h2>Release</h2>
        <span className={`badge ${pinned ? 'badge-info' : 'badge-warning'}`}>{pinned ? 'pinned' : 'not releasable'}</span>
      </div>
      <p>Der Server validiert erneut und erzeugt den immutable Snapshot nur für eine vertrauenswürdige Approver-Identität.</p>
      <div className="three-panel-layout">
        <label className="panel">Produkt-ID<input value={productId} onChange={(event) => setProductId(event.target.value)} style={{ width: '100%' }} /></label>
        <label className="panel">Sprache<input value={language} onChange={(event) => setLanguage(event.target.value)} style={{ width: '100%' }} /></label>
        <label className="panel">Version<input type="number" min={1} value={version} onChange={(event) => setVersion(Math.max(1, Number(event.target.value) || 1))} style={{ width: '100%' }} /></label>
      </div>
      {blockingHint && <div className="summary-bar summary-fail">{blockingHint}</div>}
      <div className="panel-actions" style={{ marginTop: 10 }}>
        <button className="btn-primary" disabled={busy || !pinned || !productId.trim() || !language.trim()} onClick={() => void validateAndRelease()}>
          {busy ? 'Validiere und erzeuge…' : 'Validieren & Release erzeugen'}
        </button>
      </div>
      {message && <div className="summary-bar" style={{ marginTop: 10 }}>{message}</div>}
      <details style={{ marginTop: 12 }}>
        <summary>Release-Historie ({releases.length})</summary>
        {releases.length === 0 ? <p>Noch keine Releases gespeichert.</p> : (
          <table className="validation-table">
            <thead><tr><th>Release</th><th>Produkt</th><th>Sprache</th><th>Version</th><th>Erstellt von</th><th>Checksum</th></tr></thead>
            <tbody>{releases.map((release) => (
              <tr key={release.release_id}>
                <td><code>{release.release_id}</code></td>
                <td>{release.product_id}</td>
                <td>{release.language}</td>
                <td>{release.version}</td>
                <td>{release.created_by}</td>
                <td><code>{release.release_checksum.slice(0, 16)}…</code></td>
              </tr>
            ))}</tbody>
          </table>
        )}
      </details>
    </div>
  );
}
