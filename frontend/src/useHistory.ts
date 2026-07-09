/**
 * Undo/Redo history hook for AuthoringDoc.
 * Maintains a stack of snapshots and supports Ctrl+Z / Ctrl+Y / Ctrl+Shift+Z.
 */

import { useState, useCallback, useRef, useEffect } from 'react';

const MAX_HISTORY = 50;

export function useHistory<T>(initial: T | null) {
  const [current, setCurrent] = useState<T | null>(initial);
  const pastRef = useRef<T[]>([]);
  const futureRef = useRef<T[]>([]);
  const skipRef = useRef(false);

  const push = useCallback((next: T | null) => {
    if (skipRef.current) {
      skipRef.current = false;
      return;
    }
    if (current !== null) {
      pastRef.current = [...pastRef.current.slice(-(MAX_HISTORY - 1)), JSON.parse(JSON.stringify(current))];
    }
    futureRef.current = [];
    setCurrent(next);
  }, [current]);

  const undo = useCallback(() => {
    if (pastRef.current.length === 0 || current === null) return;
    const prev = pastRef.current.pop()!;
    futureRef.current = [...futureRef.current, JSON.parse(JSON.stringify(current))];
    skipRef.current = true;
    setCurrent(prev);
  }, [current]);

  const redo = useCallback(() => {
    if (futureRef.current.length === 0 || current === null) return;
    const next = futureRef.current.pop()!;
    pastRef.current = [...pastRef.current, JSON.parse(JSON.stringify(current))];
    skipRef.current = true;
    setCurrent(next);
  }, [current]);

  const canUndo = pastRef.current.length > 0;
  const canRedo = futureRef.current.length > 0;

  const clear = useCallback(() => {
    pastRef.current = [];
    futureRef.current = [];
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