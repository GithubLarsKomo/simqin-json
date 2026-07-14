import React, { useState } from 'react';
import { createRoot } from 'react-dom/client';
import './style.css';
import NewDocument from './NewDocument';
import Workspace from './Workspace';

const API_BASE = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8080';

// ---------------------------------------------------------------------------
// Types (shared)
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
  domain_json: Record<string, unknown>;
};

type TabId = 'canonical' | 'domain' | 'assets' | 'references' | 'mapping' | 'validation' | 'schema';

type Page = 'converter' | 'new-document' | 'workspace';

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

function downloadText(name: string, value: string) {
  const blob = new Blob([value], { type: 'text/plain' });
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
// Assets / References list component
// ---------------------------------------------------------------------------

function ListView({ items }: { items: Record<string, unknown>[] }) {
  if (!items || items.length === 0) {
    return <p className="validation-ok">{statusIcon(true)} Keine Eintr\u00E4ge gefunden.</p>;
  }
  return (
    <table className="validation-table">
      <thead>
        <tr>
          {Object.keys(items[0]).map((k) => (
            <th key={k}>{k}</th>
          ))}
        </tr>
      </thead>
      <tbody>
        {items.map((item, i) => (
          <tr key={i} className="validation-row">
            {Object.keys(items[0]).map((k) => (
              <td key={k}>{String(item[k] ?? '\u2014')}</td>
            ))}
          </tr>
        ))}
      </tbody>
    </table>
  );
}

// ---------------------------------------------------------------------------
// ConverterPage
// ---------------------------------------------------------------------------

function ConverterPage() {
  const [xml, setXml] = useState<File | null>(null);
  const [dtd, setDtd] = useState<File | null>(null);
  const [mapping, setMapping] = useState<File | null>(null);
  const [mappingText, setMappingText] = useState<string>('');
  const [result, setResult] = useState<ConversionResult | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [tab, setTab] = useState<TabId>('canonical');
  const [schema, setSchema] = useState<Record<string, unknown> | null>(null);
  const [schemaKind, setSchemaKind] = useState<'canonical' | 'domain' | null>(null);
  const [schemaError, setSchemaError] = useState<string | null>(null);

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    if (!xml) return;
    setBusy(true);
    setError(null);
    setResult(null);
    setSchema(null);
    setSchemaError(null);
    const form = new FormData();
    form.append('file', xml);
    if (dtd) form.append('dtd', dtd);
    if (mapping) form.append('mapping', mapping);
    if (mappingText.trim()) form.append('mapping_text', mappingText);
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

  async function loadSchema(kind: 'canonical' | 'domain') {
    setSchemaError(null);
    setSchemaKind(kind);
    try {
      const res = await fetch(`${API_BASE}/api/v1/schemas/${kind}`);
      if (!res.ok) throw new Error(await res.text());
      setSchema(await res.json());
      setTab('schema');
    } catch (e) {
      setSchemaError(e instanceof Error ? e.message : String(e));
    }
  }

  const domainData = result?.domain_json;
  const assets = (domainData?.assets as Record<string, unknown>[] | undefined) ?? [];
  const references = (domainData?.references as Record<string, unknown>[] | undefined) ?? [];
  const ditaMap = domainData?.dita_map as Record<string, unknown> | undefined;
  const mappingMeta = domainData?._mapping as Record<string, unknown> | undefined;

  return (
    <main>
      <header>
        <h1>SIMQIN XML \u2192 JSON</h1>
        <p>XML/DTD einlesen, validieren, DITA-Maps erkennen und als JSON exportieren.</p>
      </header>
      <form onSubmit={submit} className="card">
        <label>XML-Datei<input type="file" accept=".xml,.dita,.ditamap" onChange={e => setXml(e.target.files?.[0] ?? null)} /></label>
        <label>DTD (optional)<input type="file" accept=".dtd" onChange={e => setDtd(e.target.files?.[0] ?? null)} /></label>
        <label>Mapping YAML (optional)<input type="file" accept=".yaml,.yml" onChange={e => setMapping(e.target.files?.[0] ?? null)} /></label>
        <details className="domain-section">
          <summary>Mapping YAML als Text (optional)</summary>
          <textarea rows={6} value={mappingText} onChange={e => setMappingText(e.target.value)} className="mapping-textarea" />
        </details>
        <button disabled={!xml || busy}>{busy ? '\u23F3 Konvertiere\u2026' : 'Konvertieren'}</button>
      </form>
      {error && (<section className="card error-card"><h2>{'\u274C'} Fehler</h2><pre>{error}</pre></section>)}
      {schemaError && (<section className="card error-card"><h2>{'\u274C'} Schema-Fehler</h2><pre>{schemaError}</pre></section>)}
      {result && (<>
        <div className={`summary-bar ${result.validation.valid ? 'summary-ok' : 'summary-fail'}`}>
          {statusIcon(result.validation.valid)}
          {result.validation.valid ? ' Validierung erfolgreich' : ` ${result.validation.errors.length} Validierungsfehler`}
          {result.validation.schema_type && ` (${result.validation.schema_type})`}
        </div>
        <div className="tabs">
          {(['canonical','domain','assets','references','validation','schema'] as const).map(t => (
            <button key={t} className={`tab ${tab===t?'tab-active':''}`} onClick={()=>setTab(t)}>
              {t==='canonical'?'Canonical JSON':t==='domain'?'Domain JSON':t==='assets'?`Assets (${assets.length})`:t==='references'?`Referenzen (${references.length})`:t==='validation'?'Validierung':'Schema'}
            </button>
          ))}
          {mappingMeta && <button className={`tab ${tab==='mapping'?'tab-active':''}`} onClick={()=>setTab('mapping')}>Mapping</button>}
        </div>
        <div className="card tab-content">
          {tab==='canonical'&&result.canonical_json&&(<><div className="tab-header"><h2>Canonical JSON</h2><button onClick={()=>downloadJson('canonical.json',result.canonical_json)}>{'\u2B07'} Download</button></div>
            <TreeView node={result.canonical_json.document.root} label={result.canonical_json.document.source_filename} /></>)}
          {tab==='domain'&&(<><div className="tab-header"><h2>Domain JSON</h2><button onClick={()=>downloadJson('domain.json',result.domain_json)}>{'\u2B07'} Download</button></div>
            {ditaMap&&<details><summary>DITA Map {ditaMap.title?`\u2014 ${String(ditaMap.title)}`:''}</summary><pre>{JSON.stringify(ditaMap,null,2)}</pre></details>}
            <pre>{JSON.stringify(result.domain_json,null,2)}</pre></>)}
          {tab==='assets'&&(<><div className="tab-header"><h2>Assets ({assets.length})</h2><button onClick={()=>downloadJson('assets.json',assets)}>{'\u2B07'} Download</button></div>
            {assets.length>0?<ListView items={assets}/>:<p>{statusIcon(true)} Keine Assets.</p>}</>)}
          {tab==='references'&&(<><div className="tab-header"><h2>Referenzen ({references.length})</h2><button onClick={()=>downloadJson('references.json',references)}>{'\u2B07'} Download</button></div>
            {references.length>0?<ListView items={references}/>:<p>{statusIcon(true)} Keine Referenzen.</p>}</>)}
          {tab==='mapping'&&mappingMeta&&(<><div className="tab-header"><h2>Mapping</h2></div>
            <table className="validation-table"><tbody>
              <tr><td><strong>Profil</strong></td><td>{String(mappingMeta.profile??'')}</td></tr>
              <tr><td><strong>Version</strong></td><td>{String(mappingMeta.version??'')}</td></tr>
              <tr><td><strong>Regeln</strong></td><td>{String(mappingMeta.rule_count??'')}</td></tr>
            </tbody></table>
            {Array.isArray(mappingMeta.warnings)&&mappingMeta.warnings.length>0&&(<><h3>Warnings</h3><ul>{(mappingMeta.warnings as string[]).map((w,i)=><li key={i} className="mapping-warning">{w}</li>)}</ul></>)}</>)}
          {tab==='validation'&&(<><div className="tab-header"><h2>Validierungsreport</h2>
            <button onClick={()=>downloadJson('validation-report.json',result.validation)}>{'\u2B07'} Download JSON</button>
            <button onClick={()=>downloadText('validation-report.txt',JSON.stringify(result.validation,null,2))}>{'\u2B07'} Download Text</button></div>
            <ValidationReportView report={result.validation}/></>)}
          {tab==='schema'&&(<><div className="tab-header"><h2>JSON Schema</h2>
            <div className="schema-buttons">
              <button onClick={()=>{setSchema(null);setSchemaKind('canonical');loadSchema('canonical');}}>Canonical Schema laden</button>
              <button onClick={()=>{setSchema(null);setSchemaKind('domain');loadSchema('domain');}}>Domain Schema laden</button>
            </div></div>
            {schema&&schemaKind&&<><button onClick={()=>downloadJson('schema.json',schema)}>{'\u2B07'} Download</button><pre>{JSON.stringify(schema,null,2)}</pre></>}</>)}
        </div>
      </>)}
    </main>
  );
}

// ---------------------------------------------------------------------------
// App (router only)
// ---------------------------------------------------------------------------

function App() {
  const [page, setPage] = useState<Page>('converter');

  return (
    <>
      <nav className="nav-bar">
        <div className="nav-inner">
          <span className="nav-brand" onClick={() => setPage('converter')} style={{cursor:'pointer'}}>SIMQIN</span>
          <div className="nav-links">
            <button className={`nav-btn ${page==='converter'?'nav-btn-active':''}`} onClick={() => setPage('converter')}>Konvertieren</button>
            <button className={`nav-btn ${page==='workspace'?'nav-btn-active':''}`} onClick={() => setPage('workspace')}>Workspace</button>
            <button className={`nav-btn ${page==='new-document'?'nav-btn-active':''}`} onClick={() => setPage('new-document')}>Neues Dokument</button>
          </div>
        </div>
      </nav>
      {page==='converter' && <ConverterPage />}
      {page==='workspace' && <Workspace onNavigateHome={() => setPage('converter')} />}
      {page==='new-document' && <NewDocument onNavigateHome={() => setPage('converter')} />}
    </>
  );
}

createRoot(document.getElementById('root')!).render(<App />);
