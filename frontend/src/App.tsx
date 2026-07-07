import React, { useState } from 'react';
import { createRoot } from 'react-dom/client';
import './style.css';

const API_BASE = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8080';

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

type ValidationEntry = {
  line: number | null;
  column: number | null;
  level: string;
  message: string;
};

type ValidationReport = {
  valid: boolean;
  schema_type: string | null;
  errors: ValidationEntry[];
  warnings: ValidationEntry[];
};

type CanonicalNode = {
  type: 'element' | 'text';
  name?: string | null;
  qualified_name?: string | null;
  namespace?: string | null;
  attributes?: Record<string, string>;
  children?: CanonicalNode[];
  text?: string;
};

type CanonicalDoc = {
  document: { source_filename: string; root: CanonicalNode };
  metadata: {
    parser_version: string;
    validated: boolean;
    schema_type: string | null;
    errors: ValidationEntry[];
    warnings: ValidationEntry[];
  };
};

type ConversionResult = {
  ok: boolean;
  validation: ValidationReport;
  canonical_json: CanonicalDoc | null;
  domain_json: unknown;
};

type TabId = 'canonical' | 'domain' | 'validation';

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function downloadJson(name: string, value: unknown) {
  const blob = new Blob([JSON.stringify(value, null, 2)], { type: 'application/json' });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = name;
  a.click();
  URL.revokeObjectURL(url);
}

function statusIcon(valid: boolean): string {
  return valid ? '\u2705' : '\u274C';
}

// ---------------------------------------------------------------------------
// TreeView component
// ---------------------------------------------------------------------------

function TreeView({ node, label }: { node: CanonicalNode; label?: string }) {
  const [open, setOpen] = useState(true);

  if (node.type === 'text') {
    return (
      <div className="tree-node tree-text">
        <span className="tree-label">{label ? `${label}: ` : ''}</span>
        <span className="tree-value">"{node.text}"</span>
      </div>
    );
  }

  const hasChildren = node.children && node.children.length > 0;
  const attrCount = node.attributes ? Object.keys(node.attributes).length : 0;

  return (
    <div className="tree-node tree-element">
      <div className="tree-header" onClick={() => setOpen(!open)}>
        {hasChildren ? (open ? '\u25BC' : '\u25B6') : '\u00A0\u00A0'}
        <span className="tree-label">{label ? `${label}: ` : ''}</span>
        <span className="tree-tag">&lt;{node.name}</span>
        {node.namespace && <span className="tree-ns"> ns="{node.namespace}"</span>}
        {attrCount > 0 && (
          <span className="tree-attrs">
            {Object.entries(node.attributes!).map(([k, v]) => (
              <span key={k} className="tree-attr"> {k}=&quot;{v}&quot;</span>
            ))}
          </span>
        )}
        <span className="tree-tag">&gt;</span>
      </div>
      {open && hasChildren && (
        <div className="tree-children">
          {node.children!.map((child, i) => (
            <TreeView key={i} node={child} />
          ))}
        </div>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// ValidationReport component
// ---------------------------------------------------------------------------

function ValidationReportView({ report }: { report: ValidationReport }) {
  const entries = [...report.errors, ...report.warnings];
  if (entries.length === 0) {
    return <p className="validation-ok">{statusIcon(true)} Keine Validierungsfehler.</p>;
  }
  return (
    <table className="validation-table">
      <thead>
        <tr>
          <th>Level</th>
          <th>Zeile</th>
          <th>Spalte</th>
          <th>Meldung</th>
        </tr>
      </thead>
      <tbody>
        {entries.map((e, i) => (
          <tr key={i} className={`validation-row validation-${e.level.toLowerCase()}`}>
            <td><span className={`badge badge-${e.level.toLowerCase()}`}>{e.level}</span></td>
            <td>{e.line ?? '\u2014'}</td>
            <td>{e.column ?? '\u2014'}</td>
            <td>{e.message}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

// ---------------------------------------------------------------------------
// App
// ---------------------------------------------------------------------------

function App() {
  const [xml, setXml] = useState<File | null>(null);
  const [dtd, setDtd] = useState<File | null>(null);
  const [result, setResult] = useState<ConversionResult | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [tab, setTab] = useState<TabId>('canonical');

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    if (!xml) return;
    setBusy(true);
    setError(null);
    setResult(null);
    const form = new FormData();
    form.append('file', xml);
    if (dtd) form.append('dtd', dtd);
    try {
      const res = await fetch(`${API_BASE}/api/v1/documents`, { method: 'POST', body: form });
      if (!res.ok) {
        const text = await res.text();
        let detail: string;
        try {
          detail = JSON.parse(text).detail || text;
        } catch {
          detail = text;
        }
        throw new Error(detail);
      }
      setResult(await res.json());
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  return (
    <main>
      <header>
        <h1>SIMQIN XML \u2192 JSON</h1>
        <p>XML/DTD einlesen, validieren und als Canonical JSON oder Domain JSON exportieren.</p>
      </header>

      {/* Upload form */}
      <form onSubmit={submit} className="card">
        <label>
          XML-Datei
          <input type="file" accept=".xml,.dita,.ditamap" onChange={e => setXml(e.target.files?.[0] ?? null)} />
        </label>
        <label>
          DTD (optional)
          <input type="file" accept=".dtd" onChange={e => setDtd(e.target.files?.[0] ?? null)} />
        </label>
        <button disabled={!xml || busy}>
          {busy ? '\u23F3 Konvertiere\u2026' : 'Konvertieren'}
        </button>
      </form>

      {/* Error display */}
      {error && (
        <section className="card error-card">
          <h2>{'\u274C'} Fehler</h2>
          <pre>{error}</pre>
        </section>
      )}

      {/* Results */}
      {result && (
        <>
          {/* Validation summary bar */}
          <div className={`summary-bar ${result.validation.valid ? 'summary-ok' : 'summary-fail'}`}>
            {statusIcon(result.validation.valid)}
            {result.validation.valid
              ? ' Validierung erfolgreich'
              : ` ${result.validation.errors.length} Validierungsfehler gefunden`}
            {result.validation.schema_type && ` (${result.validation.schema_type})`}
          </div>

          {/* Tabs */}
          <div className="tabs">
            <button
              className={`tab ${tab === 'canonical' ? 'tab-active' : ''}`}
              onClick={() => setTab('canonical')}
            >
              Canonical JSON
            </button>
            <button
              className={`tab ${tab === 'domain' ? 'tab-active' : ''}`}
              onClick={() => setTab('domain')}
            >
              Domain JSON
            </button>
            <button
              className={`tab ${tab === 'validation' ? 'tab-active' : ''}`}
              onClick={() => setTab('validation')}
            >
              Validierungsreport
            </button>
          </div>

          {/* Tab content */}
          <div className="card tab-content">
            {tab === 'canonical' && result.canonical_json && (
              <>
                <div className="tab-header">
                  <h2>Canonical JSON</h2>
                  <button onClick={() => downloadJson('canonical.json', result.canonical_json)}>
                    {'\u2B07'} Download
                  </button>
                </div>
                <TreeView node={result.canonical_json.document.root} label={result.canonical_json.document.source_filename} />
              </>
            )}
            {tab === 'domain' && (
              <>
                <div className="tab-header">
                  <h2>Domain JSON</h2>
                  <button onClick={() => downloadJson('domain.json', result.domain_json)}>
                    {'\u2B07'} Download
                  </button>
                </div>
                <pre>{JSON.stringify(result.domain_json, null, 2)}</pre>
              </>
            )}
            {tab === 'validation' && (
              <>
                <div className="tab-header">
                  <h2>Validierungsreport</h2>
                </div>
                <ValidationReportView report={result.validation} />
              </>
            )}
          </div>
        </>
      )}
    </main>
  );
}

createRoot(document.getElementById('root')!).render(<App />);
