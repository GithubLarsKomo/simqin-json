import React, { useEffect, useMemo, useState } from 'react';

const API_BASE = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8080';

type TranslationBinding = {
  content_object_id: string;
  target_language: string;
  variant_id: string;
  revision: number;
  canonical_revision: number;
};

type TranslationVariant = {
  id: string;
  content_object_id: string;
  canonical_revision: number;
  target_language: string;
  revision: number;
  status: string;
  created_by?: string;
  status_changed_by?: string;
};

type ContentObject = {
  id: string;
  canonical_language: string;
};

type ReleaseSummary = {
  release_id: string;
  product_id: string;
  language: string;
  version: number;
  created_at: string;
  created_by: string;
  release_checksum: string;
  translation_bindings?: TranslationBinding[];
  provenance?: { resolution_mode?: string; resolution_checksum?: string };
};

type Props = {
  resolvePayload?: Record<string, unknown>;
};

type SelectionMap = Record<string, string>;

type TranslationSelectionRow = {
  content_object_id: string;
  variant_id: string;
  revision: number;
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

function variantKey(variant: TranslationVariant): string {
  return `${variant.id}@@${variant.revision}`;
}

export default function Phase6ReleaseWorkflow({ resolvePayload }: Props) {
  const [productId, setProductId] = useState('elisa-demo');
  const [language, setLanguage] = useState('de-DE');
  const [version, setVersion] = useState(1);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState('');
  const [releases, setReleases] = useState<ReleaseSummary[]>([]);
  const [variants, setVariants] = useState<TranslationVariant[]>([]);
  const [translationSelections, setTranslationSelections] = useState<SelectionMap>({});
  const [variantsBusy, setVariantsBusy] = useState(false);

  const pinned = resolvePayload?.revision_mode === 'pinned';
  const objects = useMemo(() => (resolvePayload?.objects || []) as ContentObject[], [resolvePayload]);
  const pins = useMemo(() => (resolvePayload?.pinned_revisions || {}) as Record<string, number>, [resolvePayload]);

  const requiredTranslations = useMemo(() => objects
    .filter((item) => item.canonical_language && item.canonical_language !== language)
    .map((item) => ({ object: item, canonicalRevision: pins[item.id] }))
    .filter((item) => Number.isInteger(item.canonicalRevision) && item.canonicalRevision > 0), [objects, language, pins]);

  const missingTranslations = useMemo(() => requiredTranslations.filter(({ object, canonicalRevision }) => {
    const selected = translationSelections[object.id];
    if (!selected) return true;
    const candidate = variants.find((variant) => variantKey(variant) === selected);
    return !candidate
      || candidate.status !== 'approved'
      || candidate.target_language !== language
      || candidate.canonical_revision !== canonicalRevision;
  }), [requiredTranslations, translationSelections, variants, language]);

  const blockingHint = useMemo(() => {
    if (!resolvePayload) return 'Kein Resolver-Payload vorhanden.';
    if (!pinned) return 'Release gesperrt: Resolver muss im Modus pinned laufen.';
    if (variantsBusy && requiredTranslations.length > 0) return 'Freigegebene Übersetzungen werden geladen…';
    if (missingTranslations.length > 0) return `Release gesperrt: ${missingTranslations.length} persistierte Übersetzung(en) müssen explizit freigegeben und gepinnt werden.`;
    return '';
  }, [resolvePayload, pinned, variantsBusy, requiredTranslations.length, missingTranslations]);

  useEffect(() => {
    setTranslationSelections((current) => {
      const next: SelectionMap = {};
      for (const { object, canonicalRevision } of requiredTranslations) {
        const existing = current[object.id];
        const validExisting = variants.find((variant) => variantKey(variant) === existing
          && variant.status === 'approved'
          && variant.target_language === language
          && variant.canonical_revision === canonicalRevision);
        if (validExisting) next[object.id] = existing;
      }
      return next;
    });
  }, [language, requiredTranslations, variants]);

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

  async function loadVariants(targetLanguage: string) {
    if (!targetLanguage.trim()) {
      setVariants([]);
      return;
    }
    setVariantsBusy(true);
    try {
      const params = new URLSearchParams({ target_language: targetLanguage, status: 'approved' });
      const response = await fetch(`${API_BASE}/api/v1/translations/variants?${params.toString()}`);
      if (!response.ok) throw new Error(errorDetail(await response.text()));
      const body = await response.json() as { variants?: TranslationVariant[] };
      setVariants(body.variants || []);
    } catch (reason) {
      setVariants([]);
      setMessage(`Translation-Katalog konnte nicht geladen werden: ${String(reason)}`);
    } finally {
      setVariantsBusy(false);
    }
  }

  useEffect(() => { void loadReleases(); }, []);
  useEffect(() => { void loadVariants(language); }, [language]);

  function selectedRows(): TranslationSelectionRow[] {
    const rows: TranslationSelectionRow[] = [];
    for (const { object } of requiredTranslations) {
      const selected = translationSelections[object.id];
      const variant = variants.find((item) => variantKey(item) === selected);
      if (variant) {
        rows.push({
          content_object_id: object.id,
          variant_id: variant.id,
          revision: variant.revision,
        });
      }
    }
    return rows;
  }

  async function validateAndRelease() {
    if (!resolvePayload || !pinned || variantsBusy || missingTranslations.length > 0) {
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
          configuration_parameters: resolvePayload.configuration_parameters || [],
          configuration_values: resolvePayload.configuration_values || [],
          translation_variants: [],
          translation_selections: selectedRows(),
        }),
      });
      if (!response.ok) throw new Error(errorDetail(await response.text()));
      const release = await response.json() as ReleaseSummary;
      const translationText = release.translation_bindings?.length
        ? ` · ${release.translation_bindings.length} Übersetzungs-Pin(s)`
        : '';
      setMessage(`Release gespeichert: ${release.release_id} · ${release.release_checksum.slice(0, 16)}…${translationText}`);
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
        <span className={`badge ${pinned && !variantsBusy && missingTranslations.length === 0 ? 'badge-info' : 'badge-warning'}`}>
          {pinned && !variantsBusy && missingTranslations.length === 0 ? 'releasable' : 'not releasable'}
        </span>
      </div>
      <p>Der Server validiert erneut und erzeugt den immutable Snapshot nur für eine vertrauenswürdige Approver-Identität. Fremdsprachen-Releases verwenden ausschließlich persistierte, freigegebene Translation-Revisionsstände.</p>
      <div className="three-panel-layout">
        <label className="panel">Produkt-ID<input value={productId} onChange={(event) => setProductId(event.target.value)} style={{ width: '100%' }} /></label>
        <label className="panel">Sprache<input value={language} onChange={(event) => setLanguage(event.target.value)} style={{ width: '100%' }} /></label>
        <label className="panel">Version<input type="number" min={1} value={version} onChange={(event) => setVersion(Math.max(1, Number(event.target.value) || 1))} style={{ width: '100%' }} /></label>
      </div>

      {requiredTranslations.length > 0 && (
        <div className="card" style={{ marginTop: 12 }}>
          <div className="section-header"><strong>Translation Pins</strong><span className="badge badge-info">persistenter Katalog</span></div>
          <table className="validation-table">
            <thead><tr><th>Content Object</th><th>Kanonisch</th><th>Zielsprache</th><th>Persistierte Translation Variant</th></tr></thead>
            <tbody>{requiredTranslations.map(({ object, canonicalRevision }) => {
              const candidates = variants.filter((variant) => variant.content_object_id === object.id
                && variant.target_language === language
                && variant.canonical_revision === canonicalRevision
                && variant.status === 'approved');
              return (
                <tr key={object.id}>
                  <td><code>{object.id}</code></td>
                  <td>{object.canonical_language} @ {canonicalRevision}</td>
                  <td>{language}</td>
                  <td>
                    <select
                      aria-label={`Translation ${object.id}`}
                      value={translationSelections[object.id] || ''}
                      onChange={(event) => setTranslationSelections((current) => ({ ...current, [object.id]: event.target.value }))}
                      style={{ width: '100%' }}
                      disabled={variantsBusy}
                    >
                      <option value="">— explizit auswählen —</option>
                      {candidates.map((variant) => (
                        <option key={variantKey(variant)} value={variantKey(variant)}>
                          {variant.id}@{variant.revision} · approved{variant.status_changed_by ? ` · ${variant.status_changed_by}` : ''}
                        </option>
                      ))}
                    </select>
                    {!variantsBusy && candidates.length === 0 && <small>Keine freigegebene persistierte Variante für diese gepinnte Revision vorhanden.</small>}
                    {variantsBusy && <small>Katalog wird geladen…</small>}
                  </td>
                </tr>
              );
            })}</tbody>
          </table>
        </div>
      )}

      {blockingHint && <div className="summary-bar summary-fail">{blockingHint}</div>}
      <div className="panel-actions" style={{ marginTop: 10 }}>
        <button className="btn-primary" disabled={busy || variantsBusy || !pinned || missingTranslations.length > 0 || !productId.trim() || !language.trim()} onClick={() => void validateAndRelease()}>
          {busy ? 'Validiere und erzeuge…' : 'Validieren & Release erzeugen'}
        </button>
      </div>
      {message && <div className="summary-bar" style={{ marginTop: 10 }}>{message}</div>}
      <details style={{ marginTop: 12 }}>
        <summary>Release-Historie ({releases.length})</summary>
        {releases.length === 0 ? <p>Noch keine Releases gespeichert.</p> : (
          <table className="validation-table">
            <thead><tr><th>Release</th><th>Produkt</th><th>Sprache</th><th>Version</th><th>Übersetzungen</th><th>Erstellt von</th><th>Checksum</th></tr></thead>
            <tbody>{releases.map((release) => (
              <tr key={release.release_id}>
                <td><code>{release.release_id}</code></td>
                <td>{release.product_id}</td>
                <td>{release.language}</td>
                <td>{release.version}</td>
                <td title={(release.translation_bindings || []).map((item) => `${item.content_object_id}: ${item.variant_id}@${item.revision} ← canonical@${item.canonical_revision}`).join('\n')}>
                  {release.translation_bindings?.length || 0}
                </td>
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
