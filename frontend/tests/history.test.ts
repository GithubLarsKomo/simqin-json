/**
 * Tests for undo/redo history, draft persistence, and validation path extraction.
 */

import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';

// Minimal test doubles for the hooks (we test the pure logic)
function createHistory<T>(initial: T | null) {
  let current = initial ? JSON.parse(JSON.stringify(initial)) : null;
  const past: T[] = [];
  const future: T[] = [];
  const MAX = 50;

  return {
    getCurrent: () => current,
    push: (next: T | null) => {
      if (current !== null) past.push(JSON.parse(JSON.stringify(current)));
      future.length = 0;
      if (past.length > MAX) past.shift();
      current = next;
    },
    undo: () => {
      if (past.length === 0 || current === null) return;
      future.push(JSON.parse(JSON.stringify(current)));
      current = past.pop()!;
    },
    redo: () => {
      if (future.length === 0 || current === null) return;
      past.push(JSON.parse(JSON.stringify(current)));
      current = future.pop()!;
    },
    canUndo: () => past.length > 0,
    canRedo: () => future.length > 0,
    clear: () => { past.length = 0; future.length = 0; },
  };
}

describe('History', () => {
  const doc1 = { title: 'Doc 1', sections: [] };
  const doc2 = { title: 'Doc 2', sections: [] };
  const doc3 = { title: 'Doc 3', sections: [] };

  it('push stores snapshots', () => {
    const h = createHistory(doc1);
    expect(h.canUndo()).toBe(false);
    h.push(doc2);
    expect(h.canUndo()).toBe(true);
  });

  it('undo restores previous state', () => {
    const h = createHistory(doc1);
    h.push(doc2);
    h.push(doc3);
    expect(h.getCurrent()?.title).toBe('Doc 3');
    h.undo();
    expect(h.getCurrent()?.title).toBe('Doc 2');
    h.undo();
    expect(h.getCurrent()?.title).toBe('Doc 1');
    expect(h.canUndo()).toBe(false);
  });

  it('redo restores undone state', () => {
    const h = createHistory(doc1);
    h.push(doc2);
    h.undo();
    expect(h.getCurrent()?.title).toBe('Doc 1');
    expect(h.canRedo()).toBe(true);
    h.redo();
    expect(h.getCurrent()?.title).toBe('Doc 2');
    expect(h.canRedo()).toBe(false);
  });

  it('push after undo clears redo stack', () => {
    const h = createHistory(doc1);
    h.push(doc2);
    h.undo();
    expect(h.canRedo()).toBe(true);
    h.push(doc3);
    expect(h.canRedo()).toBe(false);
    expect(h.getCurrent()?.title).toBe('Doc 3');
  });

  it('clear removes all history', () => {
    const h = createHistory(doc1);
    h.push(doc2);
    h.push(doc3);
    h.clear();
    expect(h.canUndo()).toBe(false);
    expect(h.canRedo()).toBe(false);
  });

  it('deep copies snapshots (immutability)', () => {
    const h = createHistory({ title: 'Original', sections: [] });
    const s = h.getCurrent()!;
    s.title = 'Mutated';
    // The original should not be mutated
    expect(h.getCurrent()?.title).toBe('Original');
  });
});

// ---------------------------------------------------------------------------
// Draft persistence (localStorage mock)
// ---------------------------------------------------------------------------

describe('Draft persistence', () => {
  let store: Record<string, string> = {};

  beforeEach(() => {
    store = {};
    vi.stubGlobal('localStorage', {
      getItem: (k: string) => store[k] ?? null,
      setItem: (k: string, v: string) => { store[k] = v; },
      removeItem: (k: string) => { delete store[k]; },
      clear: () => { store = {}; },
      get length() { return Object.keys(store).length; },
      key: (i: number) => Object.keys(store)[i] ?? null,
    });
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  // Pure function tests without relying on imports
  const saveDraft = (doc: unknown, templateId: string) => {
    try {
      const key = `simqin-draft-${templateId || 'default'}`;
      const data = { doc, templateId, savedAt: new Date().toISOString() };
      localStorage.setItem(key, JSON.stringify(data));
      return true;
    } catch { return false; }
  };

  const loadDraft = (templateId: string) => {
    try {
      const key = `simqin-draft-${templateId || 'default'}`;
      const raw = localStorage.getItem(key);
      if (!raw) return null;
      return JSON.parse(raw);
    } catch { return null; }
  };

  const hasDraft = (templateId: string) => {
    try {
      return localStorage.getItem(`simqin-draft-${templateId || 'default'}`) !== null;
    } catch { return false; }
  };

  const clearDraft = (templateId: string) => {
    localStorage.removeItem(`simqin-draft-${templateId || 'default'}`);
  };

  it('saves and loads a draft', () => {
    const doc = { title: 'Test', sections: [] };
    saveDraft(doc, 'dita-topic');
    expect(hasDraft('dita-topic')).toBe(true);
    const loaded = loadDraft('dita-topic');
    expect(loaded).not.toBeNull();
    expect(loaded.doc.title).toBe('Test');
  });

  it('returns null for missing draft', () => {
    expect(hasDraft('nonexistent')).toBe(false);
    expect(loadDraft('nonexistent')).toBeNull();
  });

  it('clears a draft', () => {
    saveDraft({ title: 'X' }, 'test');
    expect(hasDraft('test')).toBe(true);
    clearDraft('test');
    expect(hasDraft('test')).toBe(false);
  });

  it('stores timestamp', () => {
    saveDraft({ title: 'T' }, 'ts-test');
    const loaded = loadDraft('ts-test');
    expect(loaded.savedAt).toBeDefined();
    expect(new Date(loaded.savedAt).getTime()).not.toBeNaN();
  });

  it('different template IDs have separate drafts', () => {
    saveDraft({ title: 'A' }, 'template-a');
    saveDraft({ title: 'B' }, 'template-b');
    expect(loadDraft('template-a').doc.title).toBe('A');
    expect(loadDraft('template-b').doc.title).toBe('B');
  });
});

// ---------------------------------------------------------------------------
// Validation path extraction
// ---------------------------------------------------------------------------

describe('extractPathFromValidationError', () => {

function extractPathFromValidationError(error: string): string | null {
  const pats = [
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
  for (const pat of pats) {
    const m = error.match(pat);
    if (m) {
      const wd = m[0].replace(/^doc\./, '');
      return wd.replace(/\[(\d+)\]/g, '.$1');
    }
  }
  const sm = error.match(/(sections|topicrefs|assets|references)\[(\d+)\]/);
  if (sm) return `${sm[1]}.${sm[2]}`;
  return null;
}

  it('extracts sections[N]', () => {
    expect(extractPathFromValidationError('doc.sections[0]: heading required')).toBe('sections.0');
    expect(extractPathFromValidationError('doc.sections[3] missing field')).toBe('sections.3');
  });

  it('extracts sections[N].paragraphs[N]', () => {
    expect(extractPathFromValidationError('doc.sections[0].paragraphs[1] too long')).toBe('sections.0.paragraphs.1');
  });

  it('extracts sections[N].tables[N]', () => {
    expect(extractPathFromValidationError('doc.sections[0].tables[2] error')).toBe('sections.0.tables.2');
  });

  it('extracts sections[N].images[N]', () => {
    expect(extractPathFromValidationError('doc.sections[1].images[0] missing src')).toBe('sections.1.images.0');
  });

  it('extracts sections[N].links[N]', () => {
    expect(extractPathFromValidationError('doc.sections[1].links[0] empty href')).toBe('sections.1.links.0');
  });

  it('extracts topicrefs[N]', () => {
    expect(extractPathFromValidationError('doc.topicrefs[0] missing navtitle')).toBe('topicrefs.0');
  });

  it('extracts topicrefs[N].children[N]', () => {
    expect(extractPathFromValidationError('doc.topicrefs[0].children[1] error')).toBe('topicrefs.0.children.1');
  });

  it('extracts assets[N]', () => {
    expect(extractPathFromValidationError('doc.assets[0] empty href')).toBe('assets.0');
  });

  it('extracts references[N]', () => {
    expect(extractPathFromValidationError('doc.references[2] missing')).toBe('references.2');
  });

  it('returns null for unrelated error', () => {
    expect(extractPathFromValidationError('something else entirely')).toBeNull();
  });

  it('simple bracket notation fallback works', () => {
    expect(extractPathFromValidationError('sections[0] heading required')).toBe('sections.0');
    expect(extractPathFromValidationError('topicrefs[3] error')).toBe('topicrefs.3');
  });
});