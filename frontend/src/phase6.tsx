import React from 'react';
import { createRoot } from 'react-dom/client';
import './style.css';
import Phase6Workspace from './Phase6Workspace';

const DEMO_RESOLVE_PAYLOAD = {
  root_object_ids: ['elisa-intended-purpose-demo'],
  revision_mode: 'working',
  pinned_revisions: {},
  aliases: {},
  multiplicity_rules: [],
  slot_values: {
    analyte: 'Anti-dsDNA IgG',
    sample_type: 'Serum oder Plasma',
  },
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
  </React.StrictMode>,
);
