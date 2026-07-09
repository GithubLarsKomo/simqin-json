/**
 * Undo/Redo history hook for AuthoringDoc.
 * Maintains a stack of snapshots and supports Ctrl+Z / Ctrl+Y / Ctrl+Shift+Z.
 *
 * Uses a state version counter so canUndo / canRedo trigger reliable re-renders.
 */

import { useState, useCallback, useEffect, useRef } from 'react';

const MAX_HISTORY = 50;

export function useHistory<T>(initial: T | null) {
  const [current, setCurrent] = useState<T | null>(initial);
  // Store stacks as state so length changes force re-render
  const [past, setPast] = useState<T[]>([]);
  const [future, setFuture] = useState<T[]>([]);

  const push = useCallback((next: T | null) => {
    if (current !== null) {
      setPast(p => [...p.slice(-(MAX_HISTORY - 1)), JSON.parse(JSON.stringify(current))]);
    }
    setFuture([]);
    setCurrent(next);
  }, [current]);

  const undo = useCallback(() => {
    setPast(p => {
      if (p.length === 0 || current === null) return p;
      const prev = p[p.length - 1];
      setFuture(f => [...f, JSON.parse(JSON.stringify(current))]);
      setCurrent(prev);
      return p.slice(0, -1);
    });
  }, [current]);

  const redo = useCallback(() => {
    setFuture(f => {
      if (f.length === 0 || current === null) return f;
      const next = f[f.length - 1];
      setPast(p => [...p, JSON.parse(JSON.stringify(current))]);
      setCurrent(next);
      return f.slice(0, -1);
    });
  }, [current]);

  const canUndo = past.length > 0;
  const canRedo = future.length > 0;

  const clear = useCallback(() => {
    setPast([]);
    setFuture([]);
  }, []);

  return { current, setCurrent: push, undo, redo, canUndo, canRedo, clear };
}

export function useUndoRedoKeys(undo: () => void, redo: () => void) {
  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if ((e.ctrlKey || e.metaKey) && e.key === 'z') {
        if (e.shiftKey) { e.preventDefault(); redo(); }
        else { e.preventDefault(); undo(); }
      }
      if ((e.ctrlKey || e.metaKey) && e.key === 'y') {
        e.preventDefault(); redo();
      }
    };
    window.addEventListener('keydown', handler);
    return () => window.removeEventListener('keydown', handler);
  }, [undo, redo]);
}

// ---------------------------------------------------------------------------
// Validation path extraction
// ---------------------------------------------------------------------------

/**
 * Convert a validation error string like "sections[0]" or
 * "doc.sections[0].paragraphs[1]" into a frontend dot path
 * like "sections.0" or "sections.0.paragraphs.1".
 *
 * Supports all paths listed in the spec:
 *   doc
 *   doc.sections[0]
 *   doc.sections[0].paragraphs[1]
 *   doc.sections[0].tables[0]
 *   doc.sections[0].images[0]
 *   doc.sections[0].links[0]
 *   doc.topicrefs[0]
 *   doc.topicrefs[0].children[0]
 *   doc.assets[0]
 *   doc.references[0]
 *
 * Returns null if nothing matches.
 */
export function extractPathFromValidationError(error: string): string | null {
  // Try to find patterns like sections[0], topicrefs[0], assets[0] etc.
  const patterns = [
    /docs\.sections\[(\d+)\]\.paragraphs\[(\d+)\]/,
    /docs\.sections\[(\d+)\]\.tables\[(\d+)\]/,
    /docs\.sections\[(\d+)\]\.images\[(\d+)\]/,
    /docs\.sections\[(\d+)\]\.links\[(\d+)\]/,
    /docs\.topicrefs\[(\d+)\]\.children\[(\d+)\]/,
    /docs\.sections\[(\d+)\]/,
    /docs\.topicrefs\[(\d+)\]/,
    /docs\.assets\[(\d+)\]/,
    /docs\.references\[(\d+)\]/,
  ];

  for (const pat of patterns) {
    const m = error.match(pat);
    if (m) {
      const parts: string[] = [];
      // m[0] is the full match like "doc.sections[0].paragraphs[1]"
      // We strip "doc." prefix and convert bracket to dot
      const withoutDoc = m[0].replace(/^doc\./, '');
      return withoutDoc.replace(/\[(\d+)\]/g, '.$1');
    }
  }

  // Simpler: just find sections[N], topicrefs[N], assets[N], references[N] patterns
  const simpleMatch = error.match(/(sections|topicrefs|assets|references)\[(\d+)\]/);
  if (simpleMatch) {
    return `${simpleMatch[1]}.${simpleMatch[2]}`;
  }

  return null;
}

// ---------------------------------------------------------------------------
// Draft persistence (localStorage)
// ---------------------------------------------------------------------------

const DRAFT_KEY_PREFIX = 'simqin-draft-';

export interface DraftMeta {
  savedAt: string;
  templateId: string;
}

export function saveDraft(doc: unknown, templateId: string): void {
  try {
    const key = DRAFT_KEY_PREFIX + (templateId || 'default');
    const data = { doc, templateId, savedAt: new Date().toISOString() };
    localStorage.setItem(key, JSON.stringify(data));
  } catch { /* storage full */ }
}

export function loadDraft(templateId: string): { doc: any; meta: DraftMeta } | null {
  try {
    const key = DRAFT_KEY_PREFIX + (templateId || 'default');
    const raw = localStorage.getItem(key);
    if (!raw) return null;
    const parsed = JSON.parse(raw);
    return { doc: parsed.doc, meta: { savedAt: parsed.savedAt, templateId: parsed.templateId } };
  } catch { return null; }
}

export function clearDraft(templateId: string): void {
  try {
    localStorage.removeItem(DRAFT_KEY_PREFIX + (templateId || 'default'));
  } catch { /* ignore */ }
}

export function hasDraft(templateId: string): boolean {
  try {
    return localStorage.getItem(DRAFT_KEY_PREFIX + (templateId || 'default')) !== null;
  } catch { return false; }
}

// ---------------------------------------------------------------------------
// Autosave hook
// ---------------------------------------------------------------------------

export type AutosaveStatus = 'saved' | 'unsaved' | 'saving';

export function useAutosave(doc: unknown, templateId: string, intervalMs = 5000) {
  const [status, setStatus] = useState<AutosaveStatus>('saved');
  const [lastSaved, setLastSaved] = useState<string | null>(null);
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const docRef = useRef(doc);
  docRef.current = doc;

  useEffect(() => {
    if (!doc || !templateId) return;
    setStatus('unsaved');

    if (timerRef.current) clearTimeout(timerRef.current);
    timerRef.current = setTimeout(() => {
      saveDraft(docRef.current, templateId);
      setStatus('saved');
      setLastSaved(new Date().toLocaleTimeString());
    }, intervalMs);

    return () => {
      if (timerRef.current) clearTimeout(timerRef.current);
    };
  }, [doc, templateId, intervalMs]);

  return { status, lastSaved };
}