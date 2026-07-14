import React, { useState, useEffect } from 'react';
import NewDocument from './NewDocument';

const API_BASE = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8080';

type Page = 'workspace' | 'new-document';

export default function Workspace({ onNavigateHome }: { onNavigateHome: () => void }) {
  const [project, setProject] = useState<any>(null);
  const [activeTab, setActiveTab] = useState<string | null>(null);
  const [openTabs, setOpenTabs] = useState<string[]>([]);

  useEffect(() => {
    // Create a default project on mount
    fetch(`${API_BASE}/api/v1/projects/new?name=Default%20Project`)
      .then(r => r.json())
      .then(data => {
        if (data.ok) setProject(data.project);
      })
      .catch(() => {});
  }, []);

  function openDocument(docId: string) {
    if (!openTabs.includes(docId)) {
      setOpenTabs(prev => [...prev, docId]);
    }
    setActiveTab(docId);
  }

  function closeTab(docId: string, e: React.MouseEvent) {
    e.stopPropagation();
    setOpenTabs(prev => prev.filter(id => id !== docId));
    if (activeTab === docId) {
      setActiveTab(openTabs.length > 1 ? openTabs[openTabs.length - 2] : null);
    }
  }

  // Simple explorer view
  const documents = project?.documents || [];
  const assets = project?.assets || [];

  return (
    <main style={{ maxWidth: '100%', padding: 0 }}>
      <div className="workspace-layout">
        {/* Explorer sidebar */}
        <div className="workspace-sidebar">
          <div className="panel">
            <div className="panel-header">Projekt: {project?.name || 'Laden...'}</div>
            <div className="panel-section">
              <div className="panel-subheader">Dokumente ({documents.length})</div>
              {documents.length === 0 && <div className="panel-empty">Keine Dokumente</div>}
              {documents.map((d: any) => (
                <div key={d.id}
                  className={`tree-row ${activeTab === d.id ? 'tree-row-selected' : ''}`}
                  onClick={() => openDocument(d.id)}
                >
                  {d.title || d.filename || d.id}
                </div>
              ))}
            </div>
            <div className="panel-section">
              <div className="panel-subheader">Assets ({assets.length})</div>
              {assets.length === 0 && <div className="panel-empty">Keine Assets</div>}
              {assets.map((a: any) => (
                <div key={a.id} className="tree-row">{a.filename}</div>
              ))}
            </div>
          </div>
          <div className="panel-actions">
            <button className="btn-sm" onClick={onNavigateHome}>{'\u2190'} Zurück</button>
          </div>
        </div>

        {/* Main content area */}
        <div className="workspace-main">
          {/* Tabs */}
          <div className="workspace-tabs">
            {openTabs.map(tabId => {
              const doc = documents.find((d: any) => d.id === tabId);
              return (
                <div key={tabId}
                  className={`workspace-tab ${activeTab === tabId ? 'workspace-tab-active' : ''}`}
                  onClick={() => setActiveTab(tabId)}
                >
                  {doc?.title || tabId}
                  <button className="tab-close" onClick={(e) => closeTab(tabId, e)}>{'\u2716'}</button>
                </div>
              );
            })}
            {openTabs.length === 0 && <div className="workspace-tab-placeholder">Kein Dokument geöffnet</div>}
          </div>

          {/* Tab content */}
          <div className="workspace-content">
            {activeTab && documents.length > 0 ? (
              <div className="workspace-editor-placeholder">
                <p>Dokument geöffnet. Hier wird der Editor erscheinen.</p>
              </div>
            ) : (
              <div className="workspace-empty">
                <h2>Willkommen im Project Workspace</h2>
                <p>Öffnen oder erstellen Sie ein Dokument, um mit der Bearbeitung zu beginnen.</p>
              </div>
            )}
          </div>
        </div>
      </div>
    </main>
  );
}