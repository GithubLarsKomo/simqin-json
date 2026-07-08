import React, { useState, useEffect, useCallback, useRef } from 'react';

const API_BASE = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8080';

type TemplateInfo = { id: string; name: string; description: string };
type Section = { heading: string; id: string; paragraphs: Paragraph[]; tables: TableBlock[]; images: ImageRef[]; links: LinkRef[] };
type Paragraph = { text: string; id: string };
type TableBlock = { caption: string; id: string; rows: string[][] };
type ImageRef = { src: string; alt: string; id: string };
type LinkRef = { href: string; text: string; id: string };
type TopicRef = { href: string; navtitle: string; id: string; keys: string; children: TopicRef[] };
type AssetRef = { type: string; href: string; alt: string };
type ReferenceRef = { type: string; href: string; text: string };
type AuthoringDoc = { template: string; title: string; id: string; sections: Section[]; topicrefs: TopicRef[]; assets: AssetRef[]; references: ReferenceRef[] };
type ValidationResult = { valid: boolean; errors: string[] };

function dl(name: string, content: string) {
  const blob = new Blob([content], { type: 'text/plain' });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a'); a.href = url; a.download = name; a.click();
  URL.revokeObjectURL(url);
}

export default function NewDocument({ onNavigateHome }: { onNavigateHome: () => void }) {
  const [templates, setTemplates] = useState<TemplateInfo[]>([]);
  const [tid, setTid] = useState('');
  const [doc, setDoc] = useState<AuthoringDoc | null>(null);
  const [val, setVal] = useState<ValidationResult | null>(null);
  const [xmlP, setXmlP] = useState('');
  const [jsonP, setJsonP] = useState('');
  const [err, setErr] = useState<string | null>(null);
  const [ptab, setPtab] = useState<'wysiwyg' | 'xml' | 'json'>('wysiwyg');

  useEffect(() => {
    fetch(`${API_BASE}/api/v1/templates`).then(r => r.json()).then(setTemplates).catch(e => setErr(String(e)));
  }, []);

  const pick = useCallback((id: string) => {
    setTid(id); setVal(null); setXmlP(''); setJsonP(''); setErr(null);
    const t = templates.find(x => x.id === id);
    if (!t) return;
    let d: AuthoringDoc;
    if (t.id === 'dita-topic') {
      d = { template: 'dita-topic', title: 'Neues Thema', id: 'new-topic',
        sections: [{ heading: 'Einleitung', id: 'new-topic-intro', paragraphs: [{ text: '', id: 'p1' }], tables: [], images: [], links: [] }],
        topicrefs: [], assets: [], references: [] };
    } else if (t.id === 'sop') {
      d = { template: 'sop', title: 'Standard Operating Procedure', id: 'new-sop',
        sections: [
          { heading: 'Zweck', id: 'sop-purpose', paragraphs: [{ text: '', id: 'p1' }], tables: [], images: [], links: [] },
          { heading: 'Geltungsbereich', id: 'sop-scope', paragraphs: [{ text: '', id: 'p2' }], tables: [], images: [], links: [] },
          { heading: 'Durchführung', id: 'sop-procedure', paragraphs: [{ text: '', id: 'p3' }], tables: [{ caption: 'Schritte', id: 't1', rows: [['Schritt', 'Beschreibung'], ['1', ''], ['2', '']] }], images: [], links: [] },
        ], topicrefs: [], assets: [], references: [] };
    } else if (t.id === 'dita-map') {
      d = { template: 'dita-map', title: 'Neue DITA Map', id: 'new-map',
        sections: [], topicrefs: [{ href: 'topic1.dita', navtitle: 'Topic 1', id: 'ref1', keys: '', children: [] }],
        assets: [], references: [] };
    } else {
      d = { template: t.id, title: t.name, id: 'doc', sections: [], topicrefs: [], assets: [], references: [] };
    }
    setDoc(d);
  }, [templates]);

  const upd = useCallback((fn: (d: AuthoringDoc) => void) => {
    setDoc(prev => { if (!prev) return prev; const n = JSON.parse(JSON.stringify(prev)); fn(n); return n; });
  }, []);

  useEffect(() => {
    if (!doc) return;
    const t = setTimeout(() => {
      fetch(`${API_BASE}/api/v1/authoring/render-xml`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ document: doc }) })
        .then(r => r.ok ? r.json() : null).then(d => { if (d) { const b = Uint8Array.from(atob(d.xml_base64), c => c.charCodeAt(0)); setXmlP(new TextDecoder('utf-8').decode(b)); } }).catch(() => {});
      fetch(`${API_BASE}/api/v1/authoring/render-json`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ document: doc }) })
        .then(r => r.ok ? r.json() : null).then(d => { if (d) setJsonP(JSON.stringify(d.domain_json, null, 2)); }).catch(() => {});
      fetch(`${API_BASE}/api/v1/authoring/validate`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ document: doc }) })
        .then(r => r.ok ? r.json() : null).then(setVal).catch(() => {});
    }, 400);
    return () => clearTimeout(t);
  }, [doc]);

  const setTitle = (v: string) => upd(d => { d.title = v; });
  const addSec = () => upd(d => { d.sections.push({ heading: '', id: `s${d.sections.length+1}`, paragraphs: [{ text: '', id: `p${d.sections.length+1}` }], tables: [], images: [], links: [] }); });
  const rmSec = (i: number) => upd(d => { d.sections.splice(i, 1); });
  const setSH = (i: number, v: string) => upd(d => { d.sections[i].heading = v; });
  const addP = (si: number) => upd(d => { d.sections[si].paragraphs.push({ text: '', id: `p${si}-${d.sections[si].paragraphs.length+1}` }); });
  const setP = (si: number, pi: number, v: string) => upd(d => { d.sections[si].paragraphs[pi].text = v; });
  const rmP = (si: number, pi: number) => upd(d => { if (d.sections[si].paragraphs.length > 1) d.sections[si].paragraphs.splice(pi, 1); });
  const addT = (si: number) => upd(d => { d.sections[si].tables.push({ caption: '', id: `t${Date.now()}`, rows: [['A','B'],['','']] }); });
  const setTC = (si: number, ti: number, v: string) => upd(d => { d.sections[si].tables[ti].caption = v; });
  const setTCell = (si: number, ti: number, ri: number, ci: number, v: string) => upd(d => { d.sections[si].tables[ti].rows[ri][ci] = v; });
  const addTR = (si: number, ti: number) => upd(d => { const c = d.sections[si].tables[ti].rows[0].length; d.sections[si].tables[ti].rows.push(new Array(c).fill('')); });
  const rmT = (si: number, ti: number) => upd(d => { d.sections[si].tables.splice(ti, 1); });
  const addImg = (si: number) => upd(d => { d.sections[si].images.push({ src: '', alt: '', id: `i${Date.now()}` }); });
  const setImg = (si: number, ii: number, k: string, v: string) => upd(d => { (d.sections[si].images[ii] as any)[k] = v; });
  const rmImg = (si: number, ii: number) => upd(d => { d.sections[si].images.splice(ii, 1); });
  const addLnk = (si: number) => upd(d => { d.sections[si].links.push({ href: '', text: '', id: `l${Date.now()}` }); });
  const setLnk = (si: number, li: number, k: string, v: string) => upd(d => { (d.sections[si].links[li] as any)[k] = v; });
  const rmLnk = (si: number, li: number) => upd(d => { d.sections[si].links.splice(li, 1); });
  const addTr = () => upd(d => { d.topicrefs.push({ href: '', navtitle: '', id: `tr${d.topicrefs.length+1}`, keys: '', children: [] }); });
  const setTr = (i: number, k: string, v: string) => upd(d => { (d.topicrefs[i] as any)[k] = v; });
  const rmTr = (i: number) => upd(d => { d.topicrefs.splice(i, 1); });
  const addAs = () => upd(d => { d.assets.push({ type: 'image', href: '', alt: '' }); });
  const setAs = (i: number, k: string, v: string) => upd(d => { (d.assets[i] as any)[k] = v; });
  const rmAs = (i: number) => upd(d => { d.assets.splice(i, 1); });

  const expXml = async () => {
    if (!doc) return;
    const r = await fetch(`${API_BASE}/api/v1/authoring/render-xml`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ document: doc }) });
    if (!r.ok) return;
    const data = await r.json();
    const b = Uint8Array.from(atob(data.xml_base64), c => c.charCodeAt(0));
    dl((doc.title||'doc').replace(/[^a-zA-Z0-9]/g,'-')+'.xml', new TextDecoder('utf-8').decode(b));
  };
  const expJson = () => { if (doc) dl((doc.title||'doc').replace(/[^a-zA-Z0-9]/g,'-')+'.json', JSON.stringify(doc, null, 2)); };
  const impJson = (e: React.ChangeEvent<HTMLInputElement>) => {
    const f = e.target.files?.[0]; if (!f) return;
    const reader = new FileReader();
    reader.onload = () => { try { const d = JSON.parse(reader.result as string); setDoc(d); setTid(d.template||''); } catch (ex) { setErr(String(ex)); } };
    reader.readAsText(f);
    e.target.value = '';
  };

  if (!doc) {
    return (<main><header><h1>Neues Dokument erstellen</h1><p><button className="link-btn" onClick={onNavigateHome}>{'\u2190'} Zurück</button></p></header>
      {err && <div className="card error-card"><pre>{err}</pre></div>}
      <div className="card"><div className="template-grid">
        {templates.map(t => (<div key={t.id} className={`template-card ${tid===t.id?'template-selected':''}`} onClick={() => pick(t.id)}>
          <h3>{t.name}</h3><p>{t.description}</p><button className="btn-primary">Auswählen</button></div>))}
      </div><hr/>
      <p><input type="file" accept=".json" onChange={impJson} /> JSON importieren</p></div></main>);
  }

  return (<main><header><h1>{doc.template==='dita-topic'?'DITA Topic':doc.template==='sop'?'SOP':doc.template==='dita-map'?'DITA Map':doc.template}</h1>
    <p><button className="link-btn" onClick={()=>{setDoc(null);setTid('');}}>{'\u2190'} Andere Vorlage</button></p></header>
    {err && <div className="card error-card"><pre>{err}</pre></div>}
    {val && <div className={`summary-bar ${val.valid?'summary-ok':'summary-fail'}`}>{val.valid?'\u2705 Gültig':`\u274C ${val.errors.length} Fehler`}</div>}
    <div className="authoring-layout">
      <div className="authoring-editor">
        <div className="card"><label>Titel <input type="text" value={doc.title} onChange={e=>setTitle(e.target.value)} className="input-title" /></label></div>
        <div className="card">
          <div className="section-header"><h2>Sections</h2><button onClick={addSec} className="btn-icon"><span className="icon">+</span></button></div>
          {doc.sections.map((sec, si) => (<div key={sec.id||si} className="authoring-section">
            <div className="section-header"><input type="text" value={sec.heading} onChange={e=>setSH(si,e.target.value)} placeholder="Überschrift" className="input-section-heading" />
              <button onClick={()=>rmSec(si)} className="btn-icon btn-danger"><span className="icon">{'\u2716'}</span></button></div>
            {sec.paragraphs.map((p, pi) => (<div key={p.id||pi} className="paragraph-row">
              <textarea rows={2} value={p.text} onChange={e=>setP(si,pi,e.target.value)} placeholder="Absatz" className="para-textarea" />
              <button onClick={()=>rmP(si,pi)} className="btn-icon btn-danger" disabled={sec.paragraphs.length<=1}><span className="icon">{'\u2716'}</span></button></div>))}
            <button onClick={()=>addP(si)} className="btn-link-sm"><span className="icon">+</span> Absatz</button>
            {sec.tables.map((tbl, ti) => (<div key={tbl.id||ti} className="authoring-table">
              <div className="section-header"><input type="text" value={tbl.caption} onChange={e=>setTC(si,ti,e.target.value)} placeholder="Tabellen-Titel" className="input-table-caption" />
                <button onClick={()=>rmT(si,ti)} className="btn-icon btn-danger"><span className="icon">{'\u2716'}</span></button></div>
              <table className="authoring-table-grid"><tbody>{tbl.rows.map((row, ri) => (<tr key={ri}>{row.map((cell, ci) => (<td key={ci}><input type="text" value={cell} onChange={e=>setTCell(si,ti,ri,ci,e.target.value)} className="input-table-cell" /></td>))}</tr>))}</tbody></table>
              <button onClick={()=>addTR(si,ti)} className="btn-link-sm"><span className="icon">+</span> Zeile</button></div>))}
            <button onClick={()=>addT(si)} className="btn-link-sm"><span className="icon">+</span> Tabelle</button>
            {sec.images.map((img, ii) => (<div key={img.id||ii} className="inline-fields">
              <input type="text" value={img.src} onChange={e=>setImg(si,ii,'src',e.target.value)} placeholder="Bild-URL" className="input-half" />
              <input type="text" value={img.alt} onChange={e=>setImg(si,ii,'alt',e.target.value)} placeholder="alt" className="input-half" />
              <button onClick={()=>rmImg(si,ii)} className="btn-icon btn-danger"><span className="icon">{'\u2716'}</span></button></div>))}
            <button onClick={()=>addImg(si)} className="btn-link-sm"><span className="icon">+</span> Bild</button>
            {sec.links.map((lnk, li) => (<div key={lnk.id||li} className="inline-fields">
              <input type="text" value={lnk.href} onChange={e=>setLnk(si,li,'href',e.target.value)} placeholder="href" className="input-half" />
              <input type="text" value={lnk.text} onChange={e=>setLnk(si,li,'text',e.target.value)} placeholder="Text" className="input-half" />
              <button onClick={()=>rmLnk(si,li)} className="btn-icon btn-danger"><span className="icon">{'\u2716'}</span></button></div>))}
            <button onClick={()=>addLnk(si)} className="btn-link-sm"><span className="icon">+</span> Link</button></div>))}
        </div>
        {doc.template==='dita-map' && <div className="card">
          <div className="section-header"><h2>TopicRefs</h2><button onClick={addTr} className="btn-icon"><span className="icon">+</span></button></div>
          {doc.topicrefs.map((tr, i) => (<div key={tr.id||i} className="authoring-section">
            <div className="section-header"><input type="text" value={tr.navtitle} onChange={e=>setTr(i,'navtitle',e.target.value)} placeholder="Navtitle" className="input-section-heading" />
              <button onClick={()=>rmTr(i)} className="btn-icon btn-danger"><span className="icon">{'\u2716'}</span></button></div>
            <div className="inline-fields"><input type="text" value={tr.href} onChange={e=>setTr(i,'href',e.target.value)} placeholder="href" className="input-half" />
              <input type="text" value={tr.keys} onChange={e=>setTr(i,'keys',e.target.value)} placeholder="keys" className="input-half" /></div></div>))}
        </div>}
        <div className="card"><div className="section-header"><h2>Assets</h2><button onClick={addAs} className="btn-icon"><span className="icon">+</span></button></div>
          {doc.assets.map((a, i) => (<div key={i} className="inline-fields">
            <input type="text" value={a.href} onChange={e=>setAs(i,'href',e.target.value)} placeholder="href" className="input-half" />
            <input type="text" value={a.alt} onChange={e=>setAs(i,'alt',e.target.value)} placeholder="alt" className="input-half" />
            <button onClick={()=>rmAs(i)} className="btn-icon btn-danger"><span className="icon">{'\u2716'}</span></button></div>))}</div>
        <div className="card"><div className="export-buttons">
          <button onClick={expXml} className="btn-primary">{'\u2B07'} XML</button>
          <button onClick={expJson} className="btn-primary">{'\u2B07'} JSON</button>
          <label className="btn-primary" style={{cursor:'pointer',padding:'10px 16px'}}>
            {'\u2B07'} Import <input type="file" accept=".json" onChange={impJson} style={{display:'none'}} /></label>
        </div></div>
      </div>
      <div className="authoring-preview"><div className="card">
        <div className="tabs">
          <button className={`tab ${ptab==='wysiwyg'?'tab-active':''}`} onClick={()=>setPtab('wysiwyg')}>Vorschau</button>
          <button className={`tab ${ptab==='xml'?'tab-active':''}`} onClick={()=>setPtab('xml')}>XML</button>
          <button className={`tab ${ptab==='json'?'tab-active':''}`} onClick={()=>setPtab('json')}>JSON</button>
        </div>
        <div className="tab-content preview-content">
          {ptab==='wysiwyg' && <div className="wysiwyg-canvas"><h3>{doc.title||'(Titel)'}</h3>
            {doc.sections.map(sec => <div key={sec.id}><h4>{sec.heading||'(Abschnitt)'}</h4>
              {sec.paragraphs.map((p,i) => <p key={p.id||i}>{p.text||'(leer)'}</p>)}
              {sec.tables.map(tbl => <div key={tbl.id} className="wysiwyg-table">{tbl.caption&&<p><strong>{tbl.caption}</strong></p>}
                <table><tbody>{tbl.rows.map((row,ri) => <tr key={ri}>{row.map((cell,ci) => <td key={ci}>{cell||'\u00A0'}</td>)}</tr>)}</tbody></table></div>)}
              {sec.images.map(img => <p key={img.id}>[Bild: {img.src||'(leer)'}]</p>)}
              {sec.links.map(lnk => <p key={lnk.id}>[Link: {lnk.text||'(leer)'} &rarr; {lnk.href}]</p>)}
            </div>)}
            {doc.template==='dita-map'&&<div><h4>TopicRefs</h4><ul>{doc.topicrefs.map((tr,i)=><li key={i}>{tr.navtitle||tr.href||'(leer)'}</li>)}</ul></div>}
          </div>}
          {ptab==='xml' && <pre className="code-preview">{xmlP||'Generiere...'}</pre>}
          {ptab==='json' && <pre className="code-preview">{jsonP||'Generiere...'}</pre>}
        </div>
      </div></div>
    </div></main>);
}