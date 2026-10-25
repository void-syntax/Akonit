"""GraphRAG Local Knowledge Graph Extraction & Entity Resolution Module (`backend/app/core/graph_rag.py`).
Extracts entities and relationships from incoming signal text and builds an in-memory knowledge graph
to power multi-hop reasoning and connected entity retrieval.
"""

from __future__ import annotations

import re
from typing import Any
from app.core.logging import get_logger

logger = get_logger("app.core.graph_rag")


class KnowledgeGraphNode:
    def __init__(self, name: str, entity_type: str) -> None:
        self.name = name.strip().title()
        self.entity_type = entity_type.upper()
        self.connections: set[str] = set()
        self.mention_count = 1


class SignalKnowledgeGraph:
    """In-memory Entity-Relationship Knowledge Graph for Signal Radar cross-signal reasoning."""

    def __init__(self) -> None:
        self.nodes: dict[str, KnowledgeGraphNode] = {}
        self.edges: dict[tuple[str, str], int] = {}

    def ingest_signal(self, title: str, content: str) -> None:
        text = f"{title} {content}"
        # Extract potential entities using heuristic capitalization and tech keywords
        # e.g., AI models, companies, protocols, ticker symbols
        raw_entities = re.findall(r'\b([A-Z][a-zA-Z0-9_\-\.]{2,})\b', text)
        
        # Filter noise words
        stopwords = {"The", "And", "For", "With", "This", "That", "From", "Into", "New", "Our", "All"}
        entities = [e for e in raw_entities if e not in stopwords]

        # Add nodes and edges (co-occurrences)
        unique_ents = list(dict.fromkeys(entities))[:10]  # cap per signal
        for ent in unique_ents:
            if ent not in self.nodes:
                self.nodes[ent] = KnowledgeGraphNode(ent, "CONCEPT")
            else:
                self.nodes[ent].mention_count += 1

        # Create co-occurrence edges
        for i in range(len(unique_ents)):
            for j in range(i + 1, len(unique_ents)):
                u, v = sorted([unique_ents[i], unique_ents[j]])
                self.nodes[u].connections.add(v)
                self.nodes[v].connections.add(u)
                edge_key = (u, v)
                self.edges[edge_key] = self.edges.get(edge_key, 0) + 1

    def get_related_entities(self, entity: str, depth: int = 1) -> list[str]:
        entity = entity.strip().title()
        if entity not in self.nodes:
            return []
        
        visited = {entity}
        queue = [(entity, 0)]
        related = []

        while queue:
            curr, d = queue.pop(0)
            if d >= depth:
                continue
            node = self.nodes.get(curr)
            if node:
                for neighbor in node.connections:
                    if neighbor not in visited:
                        visited.add(neighbor)
                        related.append(neighbor)
                        queue.append((neighbor, d + 1))
        return related

    def stats(self) -> dict[str, int]:
        return {
            "total_entities": len(self.nodes),
            "total_relationships": len(self.edges),
        }


# Global GraphRAG Singleton
_graph_rag_instance = SignalKnowledgeGraph()

def get_graph_rag() -> SignalKnowledgeGraph:
    return _graph_rag_instance
