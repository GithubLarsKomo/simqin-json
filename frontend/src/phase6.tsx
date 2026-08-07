import React from 'react';
import { createRoot } from 'react-dom/client';
import './style.css';
import Phase6Workspace from './Phase6Workspace';
import Phase6ReleaseWorkflow from './Phase6ReleaseWorkflow';

const DEMO_RESOLVE_PAYLOAD = {
  root_object_ids: ['elisa-intended-purpose-demo'],
  revision_mode: 'pinned',
  pinned_revisions: {
    'elisa-intended-purpose-demo': 1,
  },
  aliases: {},
  multiplicity_rules: [],
  slot_values: {
    analyte: 'Anti-dsDNA IgG',
    sample_type: 'Serum oder Plasma',
  },
  translation_variants: [
    {
      id: 'tr-elisa-intended-purpose-demo-en',
      content_object_id: 'elisa-intended-purpose-demo',
      canonical_revision: 1,
      target_language: 'en-US',
      revision: 1,
      status: 'approved',
      applicability: {},
      segment_translations: [
        {
          segment_id: 'purpose-1',
          source_text: 'Der ELISA dient dem Nachweis von {{analyte}} in {{sample_type}}.',
          translated_text: 'The ELISA is intended for the detection of {{analyte}} in {{sample_type}}.',
          order: 0,
        },
      ],
      provider_metadata: { source: 'demo' },
      created_by: 'reviewer-b',
    },
  ],
  objects: [
    {
      id: 'elisa-intended-purpose-demo',
      type: 'paragraph',
      section_type: 'intended-use',
      canonical_language: 'de-DE',
      status: 'approved',
      current_revision: 1,
      revisions: [
        {
          object_id: 'elisa-intended-purpose-demo',
          revision: 1,
          canonical_content: 'Der ELISA dient dem Nachweis von {{analyte}} in {{sample_type}}.',
          sentence_segments: [
            {
              segment_id: 'purpose-1',
              segment_type: 'sentence',
              source_text: 'Der ELISA dient dem Nachweis von {{analyte}} in {{sample_type}}.',
              source_revision: 1,
              order: 0,
            },
          ],
          slots: [
            { slot_id: 'analyte', type: 'analyte', required: true },
            { slot_id: 'sample_type', type: 'sample-type', required: true },
          ],
          composed_objects: [],
          approval_status: 'approved',
        },
      ],
    },
  ],
};

createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <Phase6Workspace resolvePayload={DEMO_RESOLVE_PAYLOAD} />
    <main style={{ maxWidth: 1400 }}>
      <Phase6ReleaseWorkflow resolvePayload={DEMO_RESOLVE_PAYLOAD} />
    </main>
  </React.StrictMode>,
);
