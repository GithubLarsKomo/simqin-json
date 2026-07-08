import React, { useState, useEffect, useCallback } from 'react';

const API_BASE = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8080';

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

type TemplateInfo = {
  id: string;
  name: string;
  description: string;
};

type AuthoringDoc = {
  template: string;
  title: string;
  id: string;
  sections: Section[];
  topicrefs: TopicRef[];
  assets: AssetRef[];
  references: ReferenceRef[];
};

type Section = {
  heading: string;
  id: string;
  paragraphs: Paragraph[];
  tables: TableBlock[];
  images: ImageRef[];
  links: LinkRef[];
};

type Paragraph = { text: string; id: string };
type TableBlock = { caption: string; id: string; rows: string[][] };
type ImageRef = { src: string; alt: string; id: string };
type LinkRef = { href: string; text: string; id: string };
type TopicRef = { href: string; navtitle: string; id: string; keys: string; children: TopicRef[] };
type AssetRef = { type: string; href: string; alt: string };
type ReferenceRef = { type: string; href: string; text: string };

type ValidationResult = { valid: boolean; errors: string[] };

// ---------------------------------------------------------------------------
// Icons
// ---------------------------------------------------------------------------

function IconPlus() { return <span className="icon">+</span>; }
function IconTrash() { return <span className="icon">\u2716</span>; }
function IconUp() { return <span className="icon">\u25B2</span>; }
function IconDown() { return <span className="icon">\u25BC</span>; }

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function downloadTextFile(name: string, content: string) {
  const blob = new Blob([content], { type: 'text/plain' });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = name;
  a.click();
  URL.revokeObjectURL(url);
}

// ---------------------------------------------------------------------------
// NewDocument component
// ---------------------------------------------------------------------------

export default function NewDocument({ onNavigateHome }: { onNavigateHome: () => void }) {
  const [templates, setTemplates] = useState<TemplateInfo[]>([]);
  const [doc, setDoc] = useState<AuthoringDoc | null>(null);
  const [templateId, setTemplateId] = useState<string>('');
  const [validation, setValidation] = useState<ValidationResult | null>(null);
  const [xmlPreview, setXmlPreview] = useState<string>('');
  const [jsonPreview, setJsonPreview] = useState<string>('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [previewTab, setPreviewTab] = useState<'wysiwyg' | 'xml' | 'json'>('wysiwyg');

  // Load templates on mount
  useEffect(() => {
    fetch(`${API_BASE}/api/v1/templates`)
      .then(r => r.json())
      .then(setTemplates)
      .catch(e => setError(String(e)));
  }, []);

  // Select template and create initial doc
  function selectTemplate(id: string) {
    setTemplateId(id);
    setValidation(null);
    setXmlPreview('');
    setJsonPreview('');
    setError(null);
    const t = templates.find(t => t.id === id);
    if (!t) return;
    let newDoc: AuthoringDoc;
    if (t.id === 'dita-topic') {
      newDoc = {
        template: 'dita-topic', title: 'Neues Thema', id: 'new-topic',
        sections: [{
          heading: 'Einleitung', id: 'new-topic-intro',
          paragraphs: [{ text: 'Dies ist der erste Absatz.', id: 'p1' }],
          tables: [], images: [], links: [],
        }],
        topicrefs: [], assets: [], references: [],
      };
    } else if (t.id === 'sop') {
      newDoc = {
        template: 'sop', title: 'Standard Operating Procedure', id: 'new-sop',
        sections: [
          { heading: 'Zweck', id: 'sop-purpose', paragraphs: [{ text: '', id: 'p1' }], tables: [], images: [], links: [] },
          { heading: 'Geltungsbereich', id: 'sop-scope', paragraphs: [{ text: '', id: 'p2' }], tables: [], images: [], links: [] },
          { heading: 'Durchführung', id: 'sop-procedure', paragraphs: [{ text: '', id: 'p3' }], tables: [{ caption: 'Schritte', id: 't1', rows: [['Schritt', 'Beschreibung'], ['1', ''], ['2', '']] }], images: [], links: [] },
        ],
        topicrefs: [], assets: [], references: [],
      };
    } else if (t.id === 'dita-map') {
      newDoc = {
        template: 'dita-map', title: 'Neue DITA Map', id: 'new-map',
        sections: [],
        topicrefs: [
          { href: 'topic1.dita', navtitle: 'Topic 1', id: 'ref1', keys: '', children: [] },
        ],
        assets: [], references: [],
      };
    } else {
      newDoc = { template: t.id, title: '', id: 'doc', sections: [], topicrefs: [], assets: [], references: [] };
    }
    setDoc(newDoc);
  }

  // Update doc and trigger preview/validation
  const updateDoc = useCallback((updater: (d: AuthoringDoc) => AuthoringDoc) => {
    setDoc(prev => {
      if (!prev) return prev;
      const next = updater(JSON.parse(JSON.stringify(prev)));
      return next;
    });
  }, []);

  // Debounced preview
  useEffect(() => {
    if (!doc) return;
    const timer = setTimeout(() => {
      renderPreviews(doc);
      validateDoc(doc);
    }, 400);
    return () => clearTimeout(timer);
  }, [doc]);

  async function renderPreviews(d: AuthoringDoc) {
    try {
      const [xmlRes, jsonRes] = await Promise.all([
        fetch(`${API_BASE}/api/v1/authoring/render-xml`, {
          method: 'POST', headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ document: d }),
        }),
        fetch(`${API_BASE}/api/v1/authoring/render-json`, {
          method: 'POST', headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ document: d }),
        }),
      ]);
      if (xmlRes.ok) {
        const data = await xmlRes.json();
        const bytes = Uint8Array.from(atob(data.xml_base64), c => c.charCodeAt(0));
        const decoder = new TextDecoder('utf-8');
        setXmlPreview(decoder.decode(bytes));
      }
      if (jsonRes.ok) {
        const data = await jsonRes.json();
        setJsonPreview(JSON.stringify(data.domain_json, null, 2));
      }
    } catch (e) {
      // ignore preview errors
    }
  }

  async function validateDoc(d: AuthoringDoc) {
    try {
      const res = await fetch(`${API_BASE}/api/v1/authoring/validate`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ document: d }),
      });
      if (res.ok) {
        setValidation(await res.json());
      }
    } catch { /* ignore */ }
  }

  // ---- Sub-components ----

  function updateTitle(title: string) {
    updateDoc(d => { d.title = title; return d; });
  }

  function addSection() {
    updateDoc(d => {
      const idx = d.sections.length + 1;
      d.sections.push({
        heading: '', id: `sec-${idx}`, paragraphs: [{ text: '', id: `p-${idx}` }],
        tables: [], images: [], links: [],
      });
      return d;
    });
  }

  function removeSection(idx: number) {
    updateDoc(d => { d.sections.splice(idx, 1); return d; });
  }

  function updateSectionHeading(idx: number, val: string) {
    updateDoc(d => { d.sections[idx].heading = val; return d; });
  }

  function addParagraph(sectionIdx: number) {
    updateDoc(d => {
      const count = d.sections[sectionIdx].paragraphs.length + 1;
      d.sections[sectionIdx].paragraphs.push({ text: '', id: `p-${sectionIdx}-${count}` });
      return d;
    });
  }

  function updateParagraph(sectionIdx: number, paraIdx: number, val: string) {
    updateDoc(d => { d.sections[sectionIdx].paragraphs[paraIdx].text = val; return d; });
  }

  function removeParagraph(sectionIdx: number, paraIdx: number) {
    updateDoc(d => {
      if (d.sections[sectionIdx].paragraphs.length > 1) {
        d.sections[sectionIdx].paragraphs.splice(paraIdx, 1);
      }
      return d;
    });
  }

  function addTable(sectionIdx: number) {
    updateDoc(d => {
      d.sections[sectionIdx].tables.push({
        caption: '', id: `tbl-${Date.now()}`, rows: [['Spalte 1', 'Spalte 2'], ['', '']],
      });
      return d;
    });
  }

  function updateTableCaption(sectionIdx: number, tblIdx: number, val: string) {
    updateDoc(d => { d.sections[sectionIdx].tables[tblIdx].caption = val; return d; });
  }

  function updateTableCell(sectionIdx: number, tblIdx: number, rowIdx: number, colIdx: number, val: string) {
    updateDoc(d => {
      d.sections[sectionIdx].tables[tblIdx].rows[rowIdx][colIdx] = val;
      return d;
    });
  }

  function addTableRow(sectionIdx: number, tblIdx: number) {
    updateDoc(d => {
      const cols = d.sections[sectionIdx].tables[tblIdx].rows[0].length;
      d.sections[sectionIdx].tables[tblIdx].rows.push(new Array(cols).fill(''));
      return d;
    });
  }

  function removeTable(sectionIdx: number, tblIdx: number) {
    updateDoc(d => {
      d.sections[sectionIdx].tables.splice(tblIdx, 1);
      return d;
    });
  }

  function addTopicref() {
    updateDoc(d => {
      d.topicrefs.push({ href: '', navtitle: '', id: `ref-${d.topicrefs.length + 1}`, keys: '', children: [] });
      return d;
    });
  }

  function updateTopicref(idx: number, field: string, val: string) {
    updateDoc(d => {
      (d.topicrefs[idx] as Record<string, string>)[field] = val;
      return d;
    });
  }

  function removeTopicref(idx: number) {
    updateDoc(d => { d.topicrefs.splice(idx, 1); return d; });
  }

  function addAsset() {
    updateDoc(d => { d.assets.push({ type: 'image', href: '', alt: '' }); return d; });
  }

  function updateAsset(idx: number, field: string, val: string) {
    updateDoc(d => { (d.assets[idx] as Record<string, string>)[field] = val; return d; });
  }

  function removeAsset(idx: number) {
    updateDoc(d => { d.assets.splice(idx, 1); return d; });
  }

  async function exportXml() {
    if (!doc) return;
    try {
      const res = await fetch(`${API_BASE}/api/v1/authoring/render-xml`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ document: doc }),
      });
      if (!res.ok) throw new Error(await res.text());
      const data = await res.json();
      const bytes = Uint8Array.from(atob(data.xml_base64), c => c.charCodeAt(0));
      const decoder = new TextDecoder('utf-8');
      const xmlStr = decoder.decode(bytes);
      const ext = doc.template === 'dita-map' ? '.ditamap' : '.xml';
      downloadTextFile((doc.title || 'document').replace(/[^a-zA-Z0-9]/g, '-') + ext, xmlStr);
    } catch (e) {
      setError(String(e));
    }
  }

  async function exportJson() {
    if (!doc) return;
    const jsonContent = JSON.stringify(doc, null, 2);
    downloadTextFile((doc.title || 'document').replace(/[^a-zA-Z0-9]/g, '-') + '.json', jsonContent);
  }

  // ---- Render ----

  if (!doc) {
    return (
      <main>
        <header>
          <h1>SIMQIN XML \u2192 JSON</h1>
          <p><button className="link-btn" onClick={onNavigateHome}>\u2190 Zur\u00FCck zur Konvertierung</button></p>
        </header>
        <div className="card">
          <h2>Neues Dokument erstellen</h2>
          {error && <div className="error-card card"><pre>{error}</pre></div>}
          {templates.length === 0 && <p>Lade Vorlagen...</p>}
          <div className="template-grid">
            {templates.map(t => (
              <div key={t.id} className={`template-card ${templateId === t.id ? 'template-selected' : ''}`}
                onClick={() => selectTemplate(t.id)}>
                <h3>{t.name}</h3>
                <p>{t.description}</p>
                <button className="btn-primary">Ausw\u00E4hlen</button>
              </div>
            ))}
          </div>
        </div>
      </main>
    );
  }

  return (
    <main>
      <header>
        <h1>Neues Dokument: {doc.template === 'dita-topic' ? 'DITA Topic' : doc.template === 'sop' ? 'SOP' : doc.template === 'dita-map' ? 'DITA Map' : doc.template}</h1>
        <p><button className="link-btn" onClick={() => { setDoc(null); setTemplateId(''); setXmlPreview(''); setJsonPreview(''); }}>\u2190 Andere Vorlage w\u00E4hlen</button></p>
      </header>

      {error && <div className="card error-card"><pre>{error}</pre></div>}

      {/* Validation summary */}
      {validation && (
        <div className={`summary-bar ${validation.valid ? 'summary-ok' : 'summary-fail'}`}>
          {validation.valid ? '\u2705 Keine Validierungsfehler' : `\u274C ${validation.errors.length} Fehler`}
        </div>
      )}

      {/* Two-column layout: editor left, preview right */}
      <div className="authoring-layout">
        {/* ---- Editor ---- */}
        <div className="authoring-editor">
          {/* Title */}
          <div className="card">
            <label>
              Titel
              <input type="text" value={doc.title} onChange={e => updateTitle(e.target.value)} className="input-title" />
            </label>
          </div>

          {doc.template !== 'dita-map' && (
            <>
              {/* Sections */}
              <div className="card">
                <div className="section-header">
                  <h2>Abschnitte</h2>
                  <button onClick={addSection} className="btn-icon"><IconPlus /> Abschnitt</button>
                </div>
                {doc.sections.map((sec, si) => (
                  <div key={sec.id || si} className="authoring-section">
                    <div className="section-header">
                      <input
                        type="text"
                        value={sec.heading}
                        onChange={e => updateSectionHeading(si, e.target.value)}
                        placeholder="Abschnitts-Überschrift"
                        className="input-section-heading"
                      />
                      <button onClick={() => removeSection(si)} className="btn-icon btn-danger"><IconTrash /></button>
                    </div>

                    {/* Paragraphs */}
                    <div className="paragraphs">
                      {sec.paragraphs.map((para, pi) => (
                        <div key={para.id || pi} className="paragraph-row">
                          <textarea
                            rows={3}
                            value={para.text}
                            onChange={e => updateParagraph(si, pi, e.target.value)}
                            placeholder="Absatztext eingeben..."
                            className="para-textarea"
                          />
                          <button onClick={() => removeParagraph(si, pi)} className="btn-icon btn-danger" disabled={sec.paragraphs.length <= 1}><IconTrash /></button>
                        </div>
                      ))}
                      <button onClick={() => addParagraph(si)} className="btn-link-sm"><IconPlus /> Absatz</button>
                    </div>

                    {/* Tables */}
                    {sec.tables.map((tbl, ti) => (
                      <div key={tbl.id || ti} className="authoring-table">
                        <div className="section-header">
                          <input type="text" value={tbl.caption} onChange={e => updateTableCaption(si, ti, e.target.value)} placeholder="Tabellen-Titel" className="input-table-caption" />
                          <button onClick={() => removeTable(si, ti)} className="btn-icon btn-danger"><IconTrash /></button>
                        </div>
                        <table className="authoring-table-grid">
                          <tbody>
                            {tbl.rows.map((row, ri) => (
                              <tr key={ri}>
                                {row.map((cell, ci) => (
                                  <td key={ci}>
                                    <input type="text" value={cell} onChange={e => updateTableCell(si, ti, ri, ci, e.target.value)}
                                      placeholder={ri === 0 ? `Spalte ${ci + 1}` : ''} className="input-table-cell" />
                                  </td>
                                ))}
                              </tr>
                            ))}
                          </tbody>
                        </table>
                        <button onClick={() => addTableRow(si, ti)} className="btn-link-sm"><IconPlus /> Zeile</button>
                      </div>
                    ))}
                    <button onClick={() => addTable(si)} className="btn-link-sm"><IconPlus /> Tabelle</button>
                  </div>
                ))}
              </div>
            </>
          )}

          {/* DITA Map: topicrefs */}
          {doc.template === 'dita-map' && (
            <div className="card">
              <div className="section-header">
                <h2>TopicRefs</h2>
                <button onClick={addTopicref} className="btn-icon"><IconPlus /> TopicRef</button>
              </div>
              {doc.topicrefs.map((tr, i) => (
                <div key={tr.id || i} className="authoring-section">
                  <div className="section-header">
                    <input type="text" value={tr.navtitle} onChange={e => updateTopicref(i, 'navtitle', e.target.value)} placeholder="Navtitle" className="input-section-heading" />
                    <button onClick={() => removeTopicref(i)} className="btn-icon btn-danger"><IconTrash /></button>
                  </div>
                  <div className="inline-fields">
                    <input type="text" value={tr.href} onChange={e => updateTopicref(i, 'href', e.target.value)} placeholder="href" className="input-half" />
                    <input type="text" value={tr.keys} onChange={e => updateTopicref(i, 'keys', e.target.value)} placeholder="keys" className="input-half" />
                  </div>
                </div>
              ))}
            </div>
          )}

          {/* Assets & References */}
          <div className="card">
            <div className="section-header">
              <h2>Assets / Referenzen</h2>
              <button onClick={addAsset} className="btn-icon"><IconPlus /> Asset</button>
            </div>
            {doc.assets.map((a, i) => (
              <div key={i} className="inline-fields">
                <input type="text" value={a.href} onChange={e => updateAsset(i, 'href', e.target.value)} placeholder="href (z.B. img/photo.png)" className="input-half" />
                <input type="text" value={a.alt} onChange={e => updateAsset(i, 'alt', e.target.value)} placeholder="alt-Text" className="input-half" />
                <button onClick={() => removeAsset(i)} className="btn-icon btn-danger"><IconTrash /></button>
              </div>
            ))}
          </div>

          {/* Export buttons */}
          <div className="card">
            <div className="export-buttons">
              <button onClick={exportXml} className="btn-primary">{'\u2B07'} XML exportieren</button>
              <button onClick={exportJson} className="btn-primary">{'\u2B07'} JSON exportieren</button>
            </div>
          </div>
        </div>

        {/* ---- Preview ---- */}
        <div className="authoring-preview">
          <div className="card">
            <div className="tabs">
              <button className={`tab ${previewTab === 'wysiwyg' ? 'tab-active' : ''}`} onClick={() => setPreviewTab('wysiwyg')}>Vorschau</button>
              <button className={`tab ${previewTab === 'xml' ? 'tab-active' : ''}`} onClick={() => setPreviewTab('xml')}>XML</button>
              <button className={`tab ${previewTab === 'json' ? 'tab-active' : ''}`} onClick={() => setPreviewTab('json')}>JSON</button>
            </div>
            <div className="tab-content preview-content">
              {previewTab === 'wysiwyg' && (
                <div className="wysiwyg-canvas">
                  <h3>{doc.title || '(Titel)'}</h3>
                  {doc.sections.map(sec => (
                    <div key={sec.id} className="wysiwyg-section">
                      <h4>{sec.heading || '(Abschnitt)'}</h4>
                      {sec.paragraphs.map((p, i) => <p key={p.id || i}>{p.text || '(leer)'}</p>)}
                      {sec.tables.map((tbl, ti) => (
                        <div key={tbl.id || ti} className="wysiwyg-table">
                          {tbl.caption && <p><strong>{tbl.caption}</strong></p>}
                          <table><tbody>
                            {tbl.rows.map((row, ri) => (
                              <tr key={ri}>{row.map((cell, ci) => <td key={ci}>{cell || '\u00A0'}</td>)}</tr>
                            ))}
                          </tbody></table>
                        </div>
                      ))}
                    </div>
                  ))}
                  {doc.template === 'dita-map' && (
                    <div className="wysiwyg-map">
                      <h4>TopicRefs</h4>
                      <ul>{doc.topicrefs.map((tr, i) => <li key={i}>{tr.navtitle || tr.href || '(leer)'}</li>)}</ul>
                    </div>
                  )}
                </div>
              )}
              {previewTab === 'xml' && (
                <pre className="code-preview">{xmlPreview || 'Generiere Vorschau...'}</pre>
              )}
              {previewTab === 'json' && (
                <pre className="code-preview">{jsonPreview || 'Generiere Vorschau...'}</pre>
              )}
            </div>
          </div>
        </div>
      </div>
    </main>
  );
}