import React, { useState, useEffect, useCallback } from 'react';
import { useHistory, useUndoRedoKeys, saveDraft, loadDraft, clearDraft, hasDraft, useAutosave } from './useHistory';
import type { AutosaveStatus } from './useHistory';

const API_BASE = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8080';

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

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
type Profile = { id: string; name: string; description: string; root_fields: string[]; allowed_children: Record<string, string[]>; allowed_attributes: Record<string, string[]>; required_fields: Record<string, string[]>; export_extension: string };
type AllowedActions = { allowed_add: string[]; allowed_attributes: string[]; required_fields: string[]; can_delete: boolean; can_move_up: boolean; can_move_down: boolean };

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function dl(name: string, content: string) {
  const blob = new Blob([content], { type: 'text/plain' });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a'); a.href = url; a.download = name; a.click();
  URL.revokeObjectURL(url);
}

/** Get a value from a nested object using a dot-separated path like "sections.0.paragraphs.1" */
function getByPath(obj: any, path: string): any {
  const parts = path.split('.');
  let cur = obj;
  for (const p of parts) {
    if (cur == null) return undefined;
    const idx = parseInt(p, 10);
    cur = Number.isNaN(idx) ? cur[p] : cur[idx];
  }
  return cur;
}

/** Clone and set a value at a dot-separated path */
function setByPathCloned(obj: any, path: string, value: any): any {
  const parts = path.split('.');
  const result = JSON.parse(JSON.stringify(obj));
  let cur = result;
  for (let i = 0; i < parts.length - 1; i++) {
    const p = parts[i];
    const idx = parseInt(p, 10);
    cur = Number.isNaN(idx) ? cur[p] : cur[idx];
  }
  const last = parts[parts.length - 1];
  const lastIdx = parseInt(last, 10);
  if (Number.isNaN(lastIdx)) cur[last] = value;
  else cur[lastIdx] = value;
  return result;
}

/** Clone and remove item at dot-separated index path */
function removeByPathCloned(obj: any, path: string): any {
  const result = JSON.parse(JSON.stringify(obj));
  const parts = path.split('.');
  let cur = result;
  for (let i = 0; i < parts.length - 1; i++) {
    const p = parts[i];
    const idx = parseInt(p, 10);
    cur = Number.isNaN(idx) ? cur[p] : cur[idx];
  }
  const last = parts[parts.length - 1];
  const lastIdx = parseInt(last, 10);
  if (!Number.isNaN(lastIdx) && Array.isArray(cur)) cur.splice(lastIdx, 1);
  return result;
}

/** Clone and move item up/down */
function moveByPathCloned(obj: any, path: string, dir: 'up' | 'down'): any {
  const result = JSON.parse(JSON.stringify(obj));
  const parts = path.split('.');
  let cur = result;
  for (let i = 0; i < parts.length - 1; i++) {
    const p = parts[i];
    const idx = parseInt(p, 10);
    cur = Number.isNaN(idx) ? cur[p] : cur[idx];
  }
  const last = parts[parts.length - 1];
  const src = parseInt(last, 10);
  if (Number.isNaN(src) || !Array.isArray(cur)) return result;
  const dst = dir === 'up' ? src - 1 : src + 1;
  if (dst < 0 || dst >= cur.length) return result;
  [cur[src], cur[dst]] = [cur[dst], cur[src]];
  return result;
}

/** Human-readable label for a node path */
function nodeLabel(doc: AuthoringDoc, path: string): string {
  if (path === 'doc') return doc.title || '(Dokument)';
  const parts = path.split('.');
  const rawType = parts[parts.length - 1];
  const idx = parseInt(rawType, 10);
  if (Number.isNaN(idx)) return rawType;

  // Navigate along path to find context
  let refs: TopicRef[] | null = null;
  // sections
  if (parts.length >= 3 && parts[parts.length - 2] === 'paragraphs') {
    const si = parseInt(parts[parts.length - 3], 10);
    const pi = idx;
    const t = doc.sections[si]?.paragraphs[pi]?.text || '';
    return `Absatz: ${t.substring(0, 25)}${t.length > 25 ? '…' : ''}`;
  }
  if (parts.length >= 3 && parts[parts.length - 2] === 'tables') {
    const si = parseInt(parts[parts.length - 3], 10);
    const ti = idx;
    return doc.sections[si]?.tables[ti]?.caption || `Tabelle ${ti}`;
  }
  if (parts.length >= 3 && parts[parts.length - 2] === 'images') {
    const si = parseInt(parts[parts.length - 3], 10);
    const ii = idx;
    return doc.sections[si]?.images[ii]?.src || `Bild ${ii}`;
  }
  if (parts.length >= 3 && parts[parts.length - 2] === 'links') {
    const si = parseInt(parts[parts.length - 3], 10);
    const li = idx;
    return doc.sections[si]?.links[li]?.text || `Link ${li}`;
  }
  if (parts.some(p => p === 'sections') && parts.length >= 2) {
    const si = parseInt(parts[parts.length - 1], 10);
    return doc.sections[si]?.heading || `Abschnitt ${si}`;
  }
  if (parts.some(p => p === 'topicrefs')) {
    let trefs: TopicRef[] = doc.topicrefs;
    let label = '';
    for (const p of parts) {
      const pi = parseInt(p, 10);
      if (!Number.isNaN(pi) && trefs[pi]) {
        label = trefs[pi].navtitle || trefs[pi].href || `TopicRef ${pi}`;
        trefs = trefs[pi].children;
      }
    }
    return label;
  }
  if (parts.some(p => p === 'assets')) {
    const ai = idx;
    return doc.assets[ai]?.href || `Asset ${ai}`;
  }
  if (parts.some(p => p === 'references')) {
    const ri = idx;
    return doc.references[ri]?.href || `Referenz ${ri}`;
  }
  return rawType;
}

/** Determine block type from path */
function blockType(path: string): string {
  const p = path.split('.');
  const last = p[p.length - 1];
  if (path === 'doc') return 'doc';
  if (last === 'sections' || (!Number.isNaN(parseInt(last, 10)) && p.includes('sections') && !p.includes('paragraphs') && !p.includes('tables') && !p.includes('images') && !p.includes('links'))) return 'section';
  if (last === 'paragraphs' || (p.includes('paragraphs') && !Number.isNaN(parseInt(last, 10)))) return 'paragraph';
  if (last === 'tables' || (p.includes('tables') && !Number.isNaN(parseInt(last, 10)))) return 'table';
  if (last === 'images' || (p.includes('images') && !Number.isNaN(parseInt(last, 10)))) return 'image';
  if (last === 'links' || (p.includes('links') && !Number.isNaN(parseInt(last, 10)))) return 'link';
  if (last === 'topicrefs' || p.includes('topicrefs') || p.includes('children')) return 'topicref';
  if (last === 'assets' || (p.includes('assets') && !Number.isNaN(parseInt(last, 10)))) return 'asset';
  if (last === 'references' || (p.includes('references') && !Number.isNaN(parseInt(last, 10)))) return 'reference';
  return last;
}

/** Map a selected path to its semantic ``{ parentBlockType }`` for
 *  allowed-actions lookups.
 *
 *  - doc         → parent is doc
 *  - section     → parent is section (add section children)
 *  - paragraph / table / image / link → parent is section (add siblings)
 *  - topicref    → parent is topicref (add child topicref)
 *  - asset / reference → parent is the block type itself (no adds)
 */
function parentBlockTypeForAdd(path: string): string {
  if (path === 'doc') return 'doc';
  const bt = blockType(path);
  if (bt === 'section') return 'section';
  if (bt === 'topicref') return 'topicref';
  // paragraphs, tables, images, links inside a section → sibling add
  if (['paragraph', 'table', 'image', 'link'].includes(bt) && path.includes('sections')) return 'section';
  // assets, references → no add unless profile overrides (use own type)
  if (['asset', 'reference'].includes(bt)) return bt;
  return 'doc';
}

// ---------------------------------------------------------------------------
// Sub-components
// ---------------------------------------------------------------------------

function StructureTree({ doc, selectedPath, onSelect }: {
  doc: AuthoringDoc; selectedPath: string; onSelect: (path: string) => void;
}) {
  const [expanded, setExpanded] = useState<Set<string>>(new Set(['doc']));

  const toggle = (p: string) => setExpanded(prev => {
    const n = new Set(prev); if (n.has(p)) n.delete(p); else n.add(p); return n;
  });

  const tn = (path: string, label: string, hasCh: boolean, depth: number) => {
    const sel = selectedPath === path;
    const exp = expanded.has(path);
    return (
      <div key={path}>
        <div className={`tree-row ${sel ? 'tree-row-selected' : ''}`} style={{ paddingLeft: depth * 14 }} onClick={() => onSelect(path)}>
          <span className="tree-toggle" onClick={(e) => { e.stopPropagation(); if (hasCh) toggle(path); }} style={{ visibility: hasCh ? 'visible' : 'hidden' }}>
            {exp ? '\u25BC' : '\u25B6'}
          </span>
          <span className="tree-label">{label}</span>
        </div>
        {hasCh && exp && tc(path, depth + 1)}
      </div>
    );
  };

  const tc = (path: string, depth: number): React.ReactNode[] => {
    const kids: React.ReactNode[] = [];
    if (path === 'doc') {
      doc.sections.forEach((sec, i) => {
        const sp = `sections.${i}`;
        kids.push(tn(sp, sec.heading || `Abschnitt ${i}`, true, depth));
        if (expanded.has(sp)) {
          sec.paragraphs.forEach((_, pi) => kids.push(tn(`${sp}.paragraphs.${pi}`, `Absatz ${pi}`, false, depth + 1)));
          sec.tables.forEach((_, ti) => kids.push(tn(`${sp}.tables.${ti}`, `Tabelle ${ti}`, false, depth + 1)));
          sec.images.forEach((_, ii) => kids.push(tn(`${sp}.images.${ii}`, `Bild ${ii}`, false, depth + 1)));
          sec.links.forEach((_, li) => kids.push(tn(`${sp}.links.${li}`, `Link ${li}`, false, depth + 1)));
        }
      });
      if (doc.template === 'dita-map') renderTRTree(doc.topicrefs, 'topicrefs', depth, kids);
      doc.assets.forEach((_, i) => kids.push(tn(`assets.${i}`, `Asset ${i}`, false, depth)));
      doc.references.forEach((_, i) => kids.push(tn(`references.${i}`, `Referenz ${i}`, false, depth)));
    }
    return kids;
  };

  const renderTRTree = (refs: TopicRef[], base: string, depth: number, kids: React.ReactNode[]) => {
    refs.forEach((tr, i) => {
      const tp = `${base}.${i}`;
      kids.push(tn(tp, tr.navtitle || tr.href || `TR ${i}`, tr.children.length > 0, depth));
      if (expanded.has(tp) && tr.children.length > 0) renderTRTree(tr.children, `${tp}.children`, depth + 1, kids);
    });
  };

  return (
    <div className="panel structure-tree">
      <div className="panel-header">Struktur</div>
      {tn('doc', doc.title || '(Dokument)', true, 0)}
      {expanded.has('doc') && tc('doc', 1)}
    </div>
  );
}

function Inspector({ doc, selectedPath, profile, onUpdate }: {
  doc: AuthoringDoc; selectedPath: string; profile: Profile | null; onUpdate: (path: string, key: string, value: string) => void;
}) {
  const node = getByPath(doc, selectedPath);
  const bt = blockType(selectedPath);
  const attrs = profile?.allowed_attributes?.[bt] || [];

  if (!node || typeof node !== 'object' || selectedPath === 'doc') {
    return (
      <div className="panel inspector">
        <div className="panel-header">Inspektor</div>
        <div className="panel-empty">Kein Element ausgewählt</div>
      </div>
    );
  }

  return (
    <div className="panel inspector">
      <div className="panel-header">Inspektor: {bt}</div>
      <div className="inspector-fields">
        {attrs.map(attr => {
          if (attr === 'rows') return null;
          const val = (node as any)[attr] ?? '';
          if (attr === 'text' && bt === 'paragraph') {
            return (
              <div key={attr} className="inspector-field">
                <label>{attr}</label>
                <textarea rows={3} value={val} onChange={e => onUpdate(selectedPath, attr, e.target.value)} />
              </div>
            );
          }
          return (
            <div key={attr} className="inspector-field">
              <label>{attr}</label>
              <input type="text" value={val} onChange={e => onUpdate(selectedPath, attr, e.target.value)} />
            </div>
          );
        })}
      </div>
    </div>
  );
}

function ActionBar({ actions, selectedPath, onAdd, onDelete, onMoveUp, onMoveDown }: {
  actions: AllowedActions | null; selectedPath: string;
  onAdd: (type: string) => void; onDelete: () => void; onMoveUp: () => void; onMoveDown: () => void;
}) {
  if (!actions) return null;
  const isDoc = selectedPath === 'doc';
  return (
    <div className="action-bar">
      {actions.allowed_add.length > 0 && (
        <div className="action-group">
          <span className="action-label">+</span>
          {actions.allowed_add.map(t => (
            <button key={t} className="btn-sm" onClick={() => onAdd(t)}>{t}</button>
          ))}
        </div>
      )}
      {!isDoc && <div className="action-group">
        {actions.can_move_up && <button className="btn-sm" onClick={onMoveUp} title="Nach oben">{'\u25B2'}</button>}
        {actions.can_move_down && <button className="btn-sm" onClick={onMoveDown} title="Nach unten">{'\u25BC'}</button>}
        {actions.can_delete && <button className="btn-sm btn-danger-sm" onClick={onDelete}>{'\u2716'}</button>}
      </div>}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Main component
// ---------------------------------------------------------------------------

export default function NewDocument({ onNavigateHome }: { onNavigateHome: () => void }) {
  const [templates, setTemplates] = useState<TemplateInfo[]>([]);
  const [tid, setTid] = useState('');
  const { current: doc, setCurrent: setDoc, undo, redo, canUndo, canRedo } = useHistory<AuthoringDoc>(null);
  const [val, setVal] = useState<ValidationResult | null>(null);
  const [xmlP, setXmlP] = useState('');
  const [jsonP, setJsonP] = useState('');
  const [err, setErr] = useState<string | null>(null);
  const [ptab, setPtab] = useState<'xml' | 'json' | 'validation'>('xml');
  const [selectedPath, setSelectedPath] = useState<string>('doc');
  const [profile, setProfile] = useState<Profile | null>(null);
  const [actions, setActions] = useState<AllowedActions | null>(null);
  const [draftLoaded, setDraftLoaded] = useState(false);

  useUndoRedoKeys(undo, redo);
  const { status: autosaveStatus, lastSaved } = useAutosave(doc, tid);

  useEffect(() => {
    fetch(`${API_BASE}/api/v1/templates`).then(r => r.json()).then(setTemplates).catch(e => setErr(String(e)));
  }, []);

  const pick = useCallback(async (id: string) => {
    setTid(id); setVal(null); setXmlP(''); setJsonP(''); setErr(null); setSelectedPath('doc'); setDraftLoaded(false);
    try {
      // Check for draft first
      const draft = loadDraft(id);
      if (draft) {
        setDoc(draft.doc);
        setProfile(null);
        const pr = await fetch(`${API_BASE}/api/v1/authoring/profiles/${id}`);
        if (pr.ok) setProfile(await pr.json());
        setDraftLoaded(true);
        return;
      }
      const r = await fetch(`${API_BASE}/api/v1/templates/${id}`);
      if (!r.ok) { setErr(`Fehler: ${r.status}`); return; }
      const d: AuthoringDoc = await r.json(); setDoc(d);
      const pr = await fetch(`${API_BASE}/api/v1/authoring/profiles/${id}`);
      if (pr.ok) setProfile(await pr.json());
    } catch (ex: any) { setErr(String(ex)); }
  }, [setDoc]);

  // Fetch allowed-actions on selection change
  useEffect(() => {
    if (!doc || !profile) return;
    const bt = blockType(selectedPath);
    const addCtx = parentBlockTypeForAdd(selectedPath);
    fetch(`${API_BASE}/api/v1/authoring/allowed-actions`, {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        profile_id: profile.id,
        selected_path: selectedPath,
        block_type: bt,
        add_context_type: addCtx,
      }),
    }).then(r => r.ok ? r.json() : null).then(setActions).catch(() => {});
  }, [doc, profile, selectedPath]);

  const withDoc = (fn: (d: AuthoringDoc) => void) => {
    if (!doc) return;
    const n = JSON.parse(JSON.stringify(doc));
    fn(n);
    setDoc(n);
  };

  // Live preview/validation
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

  // --- Mutations ---
  const handleSetTitle = (v: string) => withDoc(d => { d.title = v; });

  const handleUpdateField = (path: string, key: string, value: string) => {
    if (!doc) return;
    setDoc(setByPathCloned(doc, `${path}.${key}`, value));
  };

  const handleAdd = (type: string) => {
    withDoc(d => {
      const bt = blockType(selectedPath);
      if (selectedPath === 'doc' || bt === 'doc') {
        // Add to document root
        if (type === 'section') d.sections.push({ heading: '', id: `s${d.sections.length + 1}`, paragraphs: [{ text: '', id: 'p1' }], tables: [], images: [], links: [] });
        else if (type === 'asset') d.assets.push({ type: 'image', href: '', alt: '' });
        else if (type === 'reference') d.references.push({ type: 'xref', href: '', text: '' });
        else if (type === 'topicref') d.topicrefs.push({ href: '', navtitle: '', id: `tr${d.topicrefs.length + 1}`, keys: '', children: [] });
      } else if (bt === 'section' || (['paragraph', 'table', 'image', 'link'].includes(bt) && selectedPath.includes('sections'))) {
        // Find the parent section index from the path
        const m = selectedPath.match(/sections\.(\d+)/);
        if (m) {
          const si = parseInt(m[1], 10);
          if (type === 'paragraph') d.sections[si].paragraphs.push({ text: '', id: `p${Date.now()}` });
          else if (type === 'table') d.sections[si].tables.push({ caption: '', id: `t${Date.now()}`, rows: [['A', 'B'], ['', '']] });
          else if (type === 'image') d.sections[si].images.push({ src: '', alt: '', id: `i${Date.now()}` });
          else if (type === 'link') d.sections[si].links.push({ href: '', text: '', id: `l${Date.now()}` });
        }
      } else if (bt === 'topicref') {
        // Add child topicref to the selected topicref
        const parts = selectedPath.split('.');
        let refs: TopicRef[] = d.topicrefs;
        for (const p of parts) {
          const pi = parseInt(p, 10);
          if (!Number.isNaN(pi) && refs[pi]) {
            if (p === parts[parts.length - 1]) {
              refs[pi].children.push({ href: '', navtitle: '', id: `tr${Date.now()}`, keys: '', children: [] });
              break;
            }
            refs = refs[pi].children;
          }
        }
      }
    });
  };

  const handleDelete = () => {
    if (selectedPath === 'doc') return;
    const nd = removeByPathCloned(doc, selectedPath);
    setDoc(nd); setSelectedPath('doc');
  };

  const handleMoveUp = () => {
    const nd = moveByPathCloned(doc, selectedPath, 'up');
    setDoc(nd);
  };

  const handleMoveDown = () => {
    const nd = moveByPathCloned(doc, selectedPath, 'down');
    setDoc(nd);
  };

  // Selection in WYSIWYG
  const selSection = (i: number) => setSelectedPath(`sections.${i}`);
  const selChild = (path: string, e: React.MouseEvent) => { e.stopPropagation(); setSelectedPath(path); };

  const expXml = async () => {
    if (!doc) return;
    const r = await fetch(`${API_BASE}/api/v1/authoring/render-xml`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ document: doc }) });
    if (!r.ok) return;
    const data = await r.json();
    const b = Uint8Array.from(atob(data.xml_base64), c => c.charCodeAt(0));
    const base = (doc.title || 'doc').replace(/[^a-zA-Z0-9]/g, '-');
    const ext = profile?.export_extension || (doc.template === 'dita-map' ? '.ditamap' : doc.template === 'dita-topic' ? '.dita' : '.xml');
    dl(base + ext, new TextDecoder('utf-8').decode(b));
  };
  const expJson = () => { if (doc) dl((doc.title || 'doc').replace(/[^a-zA-Z0-9]/g, '-') + '.json', JSON.stringify(doc, null, 2)); };
  const impJson = (e: React.ChangeEvent<HTMLInputElement>) => {
    const f = e.target.files?.[0]; if (!f) return;
    const reader = new FileReader();
    reader.onload = () => {
      try {
        const d = JSON.parse(reader.result as string); setDoc(d); setTid(d.template || ''); setSelectedPath('doc');
        fetch(`${API_BASE}/api/v1/authoring/profiles/${d.template}`).then(r => r.ok ? r.json() : null).then(setProfile).catch(() => {});
      } catch (ex) { setErr(String(ex)); }
    }; reader.readAsText(f); e.target.value = '';
  };

  // --- Template selection ---
  if (!doc) {
    return (<main><header><h1>Neues Dokument erstellen</h1><p><button className="link-btn" onClick={onNavigateHome}>{'\u2190'} Zurück</button></p></header>
      {err && <div className="card error-card"><pre>{err}</pre></div>}
      <div className="card"><div className="template-grid">
        {templates.map(t => (<div key={t.id} className={`template-card ${tid === t.id ? 'template-selected' : ''}`} onClick={() => pick(t.id)}>
          <h3>{t.name}</h3><p>{t.description}</p><button className="btn-primary">Auswählen</button></div>))}
      </div><hr />
        <p><input type="file" accept=".json" onChange={impJson} /> JSON importieren</p></div></main>);
  }

  // --- Main editor ---
  const bt = blockType(selectedPath);
  const btLabel = bt === 'doc' ? 'Dokument' : bt === 'section' ? 'Abschnitt' : bt === 'paragraph' ? 'Absatz' : bt;

  return (<main className="editor-main">
    <header className="editor-header">
      <div className="editor-header-left">
        <button className="link-btn" onClick={() => { setDoc(null); setTid(''); setProfile(null); }}>{'\u2190'} Vorlage</button>
        <h1>{profile?.name || doc.template}</h1>
      </div>
      <div className="editor-header-right">
        {/* Undo/Redo */}
        <button className="btn-sm" onClick={undo} disabled={!canUndo} title="Rückgängig (Ctrl+Z)">{'\u21A9'}</button>
        <button className="btn-sm" onClick={redo} disabled={!canRedo} title="Wiederholen (Ctrl+Y)">{'\u21AA'}</button>
        <span className="separator">|</span>
        {/* Autosave status */}
        <span className={`autosave-status autosave-${autosaveStatus}`}>
          {autosaveStatus === 'saved' ? '\u2705' : autosaveStatus === 'unsaved' ? '\u23F3' : '\u23F3'}
          {autosaveStatus === 'saved' ? 'Gespeichert' : 'Ungespeichert'}
          {lastSaved && <span className="autosave-time"> ({lastSaved})</span>}
        </span>
        <span className="separator">|</span>
        {/* Draft buttons */}
        <button className="btn-sm" onClick={() => { saveDraft(doc, tid); }} title="Zwischenspeichern">Draft speichern</button>
        <button className="btn-sm" onClick={() => { const d = loadDraft(tid); if (d && confirm('Aktuelles Dokument überschreiben?')) { setDoc(d.doc); setDraftLoaded(true); } }} disabled={!hasDraft(tid)}>Draft laden</button>
        <button className="btn-sm" onClick={() => { if (confirm('Draft löschen?')) { clearDraft(tid); } }}>Draft löschen</button>
        <span className="separator">|</span>
        <span className="sel-badge">{btLabel} ausgewählt</span>
        <div className="export-buttons">
          <button onClick={expXml} className="btn-primary">{'\u2B07'} XML</button>
          <button onClick={expJson} className="btn-primary">{'\u2B07'} JSON</button>
          <label className="btn-primary" style={{ cursor: 'pointer', padding: '10px 16px' }}>
            {'\u2B07'} Import <input type="file" accept=".json" onChange={impJson} style={{ display: 'none' }} /></label>
        </div>
      </div>
    </header>
    {err && <div className="card error-card"><pre>{err}</pre></div>}
    {val && <div className={`summary-bar ${val.valid ? 'summary-ok' : 'summary-fail'}`} style={{ cursor: 'pointer' }} onClick={() => setPtab('validation')}>
      {val.valid ? '\u2705 Gültig' : `\u274C ${val.errors.length} Fehler`}
    </div>}

    <div className="three-panel-layout">
      {/* LEFT: Structure Tree */}
      <div className="panel-left">
        <StructureTree doc={doc} selectedPath={selectedPath} onSelect={setSelectedPath} />
      </div>

      {/* CENTER: WYSIWYG */}
      <div className="panel-center">
        <ActionBar actions={actions} selectedPath={selectedPath} onAdd={handleAdd} onDelete={handleDelete} onMoveUp={handleMoveUp} onMoveDown={handleMoveDown} />
        <div className="card">
          <label className="field-label">Titel <input type="text" value={doc.title} onChange={e => handleSetTitle(e.target.value)} className="input-title" /></label>
        </div>
        <div className="card wysiwyg-editor-card">
          <div className="wysiwyg-canvas">
            <h3 contentEditable suppressContentEditableWarning onBlur={e => handleSetTitle(e.currentTarget.textContent || '')}>{doc.title || '(Titel)'}</h3>
            {doc.sections.map((sec, si) => (
              <div key={sec.id || si} className={`wysiwyg-block ${selectedPath === `sections.${si}` ? 'wysiwyg-block-selected' : ''}`} onClick={() => selSection(si)}>
                <h4 contentEditable suppressContentEditableWarning onBlur={e => { withDoc(d => { d.sections[si].heading = e.currentTarget.textContent || ''; }); }}>{sec.heading || '(Abschnitt)'}</h4>
                {sec.paragraphs.map((p, pi) => (
                  <p key={p.id || pi} className={`wysiwyg-inline ${selectedPath === `sections.${si}.paragraphs.${pi}` ? 'wysiwyg-inline-selected' : ''}`} onClick={(e) => selChild(`sections.${si}.paragraphs.${pi}`, e)}
                    contentEditable suppressContentEditableWarning onBlur={e => { withDoc(d => { d.sections[si].paragraphs[pi].text = e.currentTarget.textContent || ''; }); }}>
                    {p.text || '(leer)'}
                  </p>
                ))}
                {sec.tables.map((tbl, ti) => (
                  <div key={tbl.id || ti} className={`wysiwyg-table ${selectedPath === `sections.${si}.tables.${ti}` ? 'wysiwyg-block-selected' : ''}`} onClick={(e) => selChild(`sections.${si}.tables.${ti}`, e)}>
                    {tbl.caption && <p><strong>{tbl.caption}</strong></p>}
                    <table><tbody>{tbl.rows.map((row, ri) => <tr key={ri}>{row.map((cell, ci) => <td key={ci}>{cell || '\u00A0'}</td>)}</tr>)}</tbody></table>
                  </div>
                ))}
                {sec.images.map((img, ii) => (
                  <p key={img.id || ii} className={`wysiwyg-inline ${selectedPath === `sections.${si}.images.${ii}` ? 'wysiwyg-inline-selected' : ''}`} onClick={(e) => selChild(`sections.${si}.images.${ii}`, e)}>
                    [Bild: {img.src || '(leer)'}]
                  </p>
                ))}
                {sec.links.map((lnk, li) => (
                  <p key={lnk.id || li} className={`wysiwyg-inline ${selectedPath === `sections.${si}.links.${li}` ? 'wysiwyg-inline-selected' : ''}`} onClick={(e) => selChild(`sections.${si}.links.${li}`, e)}>
                    [Link: {lnk.text || '(leer)'} &rarr; {lnk.href}]
                  </p>
                ))}
              </div>
            ))}
            {doc.template === 'dita-map' && (
              <div className="wysiwyg-map">
                <h4>TopicRefs</h4>
                {renderNestedTR(doc.topicrefs, 'topicrefs', selectedPath, selChild)}
              </div>
            )}
          </div>
        </div>
      </div>

      {/* RIGHT: Inspector */}
      <div className="panel-right">
        <Inspector doc={doc} selectedPath={selectedPath} profile={profile} onUpdate={handleUpdateField} />
      </div>
    </div>

    {/* Bottom tabs */}
    <div className="bottom-tabs">
      <div className="tabs">
        <button className={`tab ${ptab === 'xml' ? 'tab-active' : ''}`} onClick={() => setPtab('xml')}>XML</button>
        <button className={`tab ${ptab === 'json' ? 'tab-active' : ''}`} onClick={() => setPtab('json')}>JSON</button>
        <button className={`tab ${ptab === 'validation' ? 'tab-active' : ''}`} onClick={() => setPtab('validation')}>
          Validierung {val && !val.valid ? `(${val.errors.length})` : ''}
        </button>
      </div>
      <div className="tab-content bottom-tab-content">
        {ptab === 'xml' && <pre className="code-preview">{xmlP || 'Generiere...'}</pre>}
        {ptab === 'json' && <pre className="code-preview">{jsonP || 'Generiere...'}</pre>}
        {ptab === 'validation' && (
          <div className="validation-panel">
            {val ? (val.valid
              ? <p className="validation-ok">{'\u2705'} Dokument ist gültig</p>
              : <ul className="validation-errors">{val.errors.map((e, i) => (
                <li key={i} className="validation-error-item" style={{cursor:'pointer'}} onClick={() => {
                  // Try to extract a path from error message (e.g. "sections[0]")
                  const m = e.match(/sections\[\d+\]/);
                  if (m) setSelectedPath(m[0].replace('[','.').replace(']',''));
                }}>{e}
                </li>
              ))}</ul>
            ) : <p>Validierung läuft...</p>}
          </div>
        )}
      </div>
    </div>
  </main>);
}

// ---------------------------------------------------------------------------
// Recursive topicref renderer
// ---------------------------------------------------------------------------

function renderNestedTR(refs: TopicRef[], basePath: string, selectedPath: string, onSelect: (path: string, e: React.MouseEvent) => void): React.ReactNode {
  return <ul style={{ paddingLeft: '1.5rem', margin: '4px 0' }}>
    {refs.map((tr, i) => {
      const tp = `${basePath}.${i}`;
      return (
        <li key={tr.id || i}
          className={`wysiwyg-inline ${selectedPath === tp ? 'wysiwyg-inline-selected' : ''}`}
          onClick={(e) => onSelect(tp, e)}
        >
          {tr.navtitle || tr.href || '(leer)'}
          {tr.children.length > 0 && renderNestedTR(tr.children, `${tp}.children`, selectedPath, onSelect)}
        </li>
      );
    })}
  </ul>;
}