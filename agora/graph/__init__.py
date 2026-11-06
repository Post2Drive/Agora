"""Knowledge graph: upload documents, extract entities and relations, explore, retrieve."""
from .store import GraphStore

GRAPH_FILE = "graph.db"

__all__ = ["GraphStore", "GRAPH_FILE"]
