import React from 'react';
import { createRoot } from 'react-dom/client';
import './style.css';
import Phase6Workspace from './Phase6Workspace';

createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <Phase6Workspace />
  </React.StrictMode>,
);
