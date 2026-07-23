import React, { useState } from 'react';

const API_BASE = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8080';

type BuildReport = {
  statistics: Record<string, number>;
  issues: Array<{
    type: string; severity: string; message: string; doc_id?: string; path?: string;
  }>;
  error_count: number;
  warning_count: number;
};

export default function BuildView({ projectId, onNavigate }: { projectId: string; onNavigate: (docId: string) => void }) {
  const [report, setReport] = useState<BuildReport | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function runBuild() {
    setBusy(true); setError(null);
    try {
      const res = await fetch(`${API_BASE}/api/v1/projects/publish`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ name: projectId }),
      });
      if (!res.ok) throw new Error(await res.text());
      const data = await res.json();
      setReport({
        statistics: data.statistics || {},
        issues: [...(data.errors || []), ...(data.warnings || [])],
        error_count: data.error_count || 0,
        warning_count: data.warning_count || 0,
      });
    } catch (e) { setError(String(e)); }
    finally { setBusy(false); }
  }

  return (
    <div className="card">
      <div className="section-header">
        <h2>Build Report</h2>
        <button onClick={runBuild} disabled={busy} className="btn-primary">
          {busy ? 'Analysiere...' : 'Build starten'}
        </button>
      </div>
      {error && <div className="card error-card"><pre>{error}</pre></div>}

      {report && (
        <>
          <div className={`summary-bar ${report.error_count > 0 ? 'summary-fail' : 'summary-ok'}`}>
            {report.error_count > 0 ? '\u274C' : '\u2705'} {report.error_count} Fehler, {report.warning_count} Warnungen
          </div>

          {/* Statistics */}
          <table className="validation-table">
            <thead><tr><th>Metrik</th><th>Wert</th></tr></thead>
            <tbody>
              {Object.entries(report.statistics).map(([k, v]) => (
                <tr key={k}><td>{k}</td><td>{String(v)}</td></tr>
              ))}
            </tbody>
          </table>

          {/* Issues */}
          {report.issues.length > 0 && (
            <>
              <h3>Issues ({report.issues.length})</h3>
              <table className="validation-table">
                <thead><tr><th>Level</th><th>Typ</th><th>Meldung</th></tr></thead>
                <tbody>
                  {report.issues.map((iss, i) => (
                    <tr key={i} className={`validation-row validation-${iss.severity?.toLowerCase()}`}
                      onClick={() => iss.doc_id && onNavigate(iss.doc_id)}
                      style={{ cursor: iss.doc_id ? 'pointer' : 'default' }}
                    >
                      <td><span className={`badge badge-${iss.severity?.toLowerCase()}`}>{iss.severity}</span></td>
                      <td>{iss.type}</td>
                      <td>{iss.message}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </>
          )}
        </>
      )}
      {!report && !busy && <p className="panel-empty">Build starten, um Ergebnisse zu sehen.</p>}
    </div>
  );
}