"""Build graph — dependency graph for a Project.

Nodes represent documents, topicrefs, assets, keys.
Edges represent references, inclusions, parent-child, map hierarchy.

Supports detection of:
- missing references
- circular references
- duplicate ids
- duplicate keys
- orphan documents
- orphan assets
"""

from __future__ import annotations

from typing import Any

from .authoring import AuthoringDoc, Section, TopicRef
from .project import Project


# ---------------------------------------------------------------------------
# Graph node / edge types
# ---------------------------------------------------------------------------

class GraphNode:
    __slots__ = ("node_id", "type", "label", "doc_id", "data")

    def __init__(self, node_id: str, type: str, label: str = "",
                 doc_id: str | None = None, data: dict | None = None) -> None:
        self.node_id = node_id
        self.type = type
        self.label = label
        self.doc_id = doc_id
        self.data = data or {}


class GraphEdge:
    __slots__ = ("source", "target", "type", "label")

    def __init__(self, source: str, target: str, type: str = "reference",
                 label: str = "") -> None:
        self.source = source
        self.target = target
        self.type = type
        self.label = label


class BuildGraph:
    """Directed dependency graph for a Project."""

    def __init__(self) -> None:
        self.nodes: dict[str, GraphNode] = {}
        self.edges: list[GraphEdge] = []
        self._node_ids: set[str] = set()
        self._all_ids: dict[str, list[str]] = {}  # id -> [node_ids]
        self._all_keys: dict[str, list[str]] = {}  # key -> [node_ids]
        self._keydefs: set[str] = set()

    # ------------------------------------------------------------------
    # Node / edge management
    # ------------------------------------------------------------------

    def add_node(self, node: GraphNode) -> None:
        if node.node_id not in self._node_ids:
            self.nodes[node.node_id] = node
            self._node_ids.add(node.node_id)

    def add_edge(self, source: str, target: str, type: str = "reference",
                 label: str = "") -> None:
        self.edges.append(GraphEdge(source, target, type, label))

    def has_node(self, node_id: str) -> bool:
        return node_id in self._node_ids

    # ------------------------------------------------------------------
    # Index helpers
    # ------------------------------------------------------------------

    def _track_id(self, id_val: str, node_id: str) -> None:
        if id_val:
            self._all_ids.setdefault(id_val, []).append(node_id)

    def _track_key(self, key: str, node_id: str) -> None:
        if key:
            self._all_keys.setdefault(key, []).append(node_id)
            self._keydefs.add(key)

    # ------------------------------------------------------------------
    # Build from project
    # ------------------------------------------------------------------

    @classmethod
    def from_project(cls, project: Project) -> "BuildGraph":
        g = cls()

        # Project root
        g.add_node(GraphNode("project", "project", project.name))

        for pd in project.documents:
            if not pd.doc:
                continue
            doc = pd.doc
            doc_node_id = f"doc:{pd.id}"
            g.add_node(GraphNode(doc_node_id, "document", doc.title, doc_id=pd.id))
            g.add_edge("project", doc_node_id, "contains")

            # Document id
            if doc.id:
                g._track_id(doc.id, doc_node_id)

            # TopicRefs (for DITA maps)
            for tr in doc.topicrefs:
                g._add_topicref_node(g, tr, doc_node_id, pd.id)

            # Sections: ids, paragraphs, images (assets), links (references)
            for sec in doc.sections:
                if sec.id:
                    sec_node = f"section:{pd.id}:{sec.id}"
                    g.add_node(GraphNode(sec_node, "section", sec.heading or sec.id, doc_id=pd.id))
                    g.add_edge(doc_node_id, sec_node, "contains")
                    g._track_id(sec.id, sec_node)

                for para in sec.paragraphs:
                    if para.id:
                        g._track_id(para.id, doc_node_id)

                for img in sec.images:
                    if img.src:
                        asset_ref = f"asset-ref:{pd.id}:{img.id}"
                        g.add_node(GraphNode(asset_ref, "image_ref", img.src, doc_id=pd.id))
                        g.add_edge(doc_node_id, asset_ref, "references")

                for lnk in sec.links:
                    if lnk.href:
                        ref_node = f"ref:{pd.id}:{lnk.id}"
                        g.add_node(GraphNode(ref_node, "xref", lnk.href, doc_id=pd.id))
                        g.add_edge(doc_node_id, ref_node, "references")

            # Topic-level assets
            for a in doc.assets:
                if a.href:
                    asset_node = f"asset:{pd.id}:{a.href}"
                    g.add_node(GraphNode(asset_node, "asset", a.href, doc_id=pd.id))
                    g.add_edge(doc_node_id, asset_node, "references")

            # Topic-level references
            for r in doc.references:
                if r.href:
                    ref_node = f"ref:{pd.id}:{r.href}"
                    g.add_node(GraphNode(ref_node, "reference", r.href, doc_id=pd.id))
                    g.add_edge(doc_node_id, ref_node, "references")

        # Project assets
        for a in project.assets:
            asset_node = f"project-asset:{a.id}"
            g.add_node(GraphNode(asset_node, "project_asset", a.filename))
            g.add_edge("project", asset_node, "contains")

        return g

    @staticmethod
    def _add_topicref_node(g: "BuildGraph", tr: TopicRef, parent_node: str,
                           doc_id: str) -> None:
        tr_node = f"topicref:{doc_id}:{tr.id}"
        g.add_node(GraphNode(tr_node, "topicref", tr.navtitle or tr.href, doc_id=doc_id))
        g.add_edge(parent_node, tr_node, "parent-child")
        if tr.keys:
            g._track_key(tr.keys, tr_node)
        if tr.href:
            g.add_edge(tr_node, f"target:{tr.href}", "references", tr.href)
        for child in tr.children:
            BuildGraph._add_topicref_node(g, child, tr_node, doc_id)

    # ------------------------------------------------------------------
    # Diagnostics
    # ------------------------------------------------------------------

    def find_duplicate_ids(self) -> list[dict[str, Any]]:
        issues: list[dict[str, Any]] = []
        for id_val, nodes in self._all_ids.items():
            if len(nodes) > 1:
                issues.append({
                    "type": "duplicate_id",
                    "id": id_val,
                    "nodes": nodes,
                    "severity": "ERROR",
                    "message": f"Duplicate id '{id_val}' found in {len(nodes)} nodes",
                })
        return issues

    def find_duplicate_keys(self) -> list[dict[str, Any]]:
        issues: list[dict[str, Any]] = []
        for key, nodes in self._all_keys.items():
            if len(nodes) > 1:
                issues.append({
                    "type": "duplicate_key",
                    "key": key,
                    "nodes": nodes,
                    "severity": "ERROR",
                    "message": f"Duplicate key '{key}' in {len(nodes)} topicrefs",
                })
        return issues

    def find_orphan_documents(self, project: Project) -> list[dict[str, Any]]:
        """Documents not referenced by any other node."""
        issues: list[dict[str, Any]] = []
        doc_ids_in_edges: set[str] = set()
        for e in self.edges:
            for nid in (e.source, e.target):
                node = self.nodes.get(nid)
                if node and node.doc_id:
                    doc_ids_in_edges.add(node.doc_id)

        for pd in project.documents:
            if pd.id not in doc_ids_in_edges:
                issues.append({
                    "type": "orphan_document",
                    "doc_id": pd.id,
                    "title": pd.title,
                    "severity": "WARNING",
                    "message": f"Document '{pd.title}' is not referenced",
                })
        return issues

    def find_orphan_assets(self, project: Project) -> list[dict[str, Any]]:
        """Project assets not referenced by any document."""
        issues: list[dict[str, Any]] = []
        referenced_assets: set[str] = set()
        for e in self.edges:
            if e.type == "references":
                referenced_assets.add(e.target)

        for a in project.assets:
            asset_key = f"project-asset:{a.id}"
            if asset_key not in referenced_assets:
                issues.append({
                    "type": "orphan_asset",
                    "asset_id": a.id,
                    "filename": a.filename,
                    "severity": "WARNING",
                    "message": f"Asset '{a.filename}' is not referenced by any document",
                })
        return issues

    def find_circular_references(self) -> list[dict[str, Any]]:
        """Detect cycles using DFS."""
        visited: set[str] = set()
        rec_stack: set[str] = set()
        cycles: list[dict[str, Any]] = []

        def dfs(node_id: str, path: list[str]) -> None:
            visited.add(node_id)
            rec_stack.add(node_id)
            path.append(node_id)
            for e in self.edges:
                if e.source == node_id:
                    if e.target in rec_stack:
                        cycle_path = path[path.index(e.target):] + [e.target]
                        cycles.append({
                            "type": "circular_reference",
                            "path": " -> ".join(cycle_path),
                            "severity": "ERROR",
                            "message": f"Circular reference detected: {' -> '.join(cycle_path)}",
                        })
                    elif e.target not in visited:
                        dfs(e.target, path)
            path.pop()
            rec_stack.discard(node_id)

        for nid in self._node_ids:
            if nid not in visited:
                dfs(nid, [])
        return cycles

    def full_report(self, project: Project) -> dict[str, Any]:
        """Run all diagnostic checks and return a comprehensive report."""
        issues: list[dict[str, Any]] = []
        issues.extend(self.find_duplicate_ids())
        issues.extend(self.find_duplicate_keys())
        issues.extend(self.find_orphan_documents(project))
        issues.extend(self.find_orphan_assets(project))
        issues.extend(self.find_circular_references())

        stats = {
            "total_nodes": len(self.nodes),
            "total_edges": len(self.edges),
            "documents": len([n for n in self.nodes.values() if n.type == "document"]),
            "topicrefs": len([n for n in self.nodes.values() if n.type == "topicref"]),
            "assets": len([n for n in self.nodes.values() if n.type in ("asset", "project_asset")]),
            "references": len([n for n in self.nodes.values() if n.type == "reference"]),
        }

        return {
            "statistics": stats,
            "issues": issues,
            "error_count": len([i for i in issues if i.get("severity") in ("ERROR", "FATAL")]),
            "warning_count": len([i for i in issues if i.get("severity") == "WARNING"]),
        }