"""
Graph utilities – build, cache, and query a directed graph of Node objects.

Uses a **single global cache key** (`node_graph`) for the entire Node graph.
Cache invalidation is lazy by default (Option A): signal handlers delete the
cache key; the next read rebuilds it.  Switch to eager (Option B) by passing
``rebuild=True`` to ``invalidate_graph()``.

The cache backend must support pickling (LocMemCache, Redis via django-redis,
etc.).  Django's default LocMemCache works but does not share state across
processes — fine for development and single-worker deployments.
"""

import networkx as nx
from django.core.cache import cache

from .models import Node

# ---------------------------------------------------------------------------
# Cache key
# ---------------------------------------------------------------------------
GRAPH_CACHE_KEY = "node_graph"
GRAPH_CACHE_TIMEOUT = None  # No expiry – we invalidate explicitly


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------
class NodeNotInGraphError(Exception):
    """Raised when a requested node_id is not present in the cached graph."""


# ---------------------------------------------------------------------------
# Build / cache helpers
# ---------------------------------------------------------------------------

def build_graph() -> nx.DiGraph:
    """
    Query *all* Nodes and their M2M ``children``, return a ``nx.DiGraph``.

    Uses ``prefetch_related('children')`` to avoid N+1 queries.
    """
    G = nx.DiGraph()

    nodes = Node.objects.prefetch_related("children").all()
    for node in nodes:
        G.add_node(node.pk)
        for child in node.children.all():
            G.add_edge(node.pk, child.pk)

    return G


def get_graph() -> nx.DiGraph:
    """Return the cached graph, rebuilding it on a cache miss."""
    G = cache.get(GRAPH_CACHE_KEY)
    if G is None:
        G = build_graph()
        cache.set(GRAPH_CACHE_KEY, G, timeout=GRAPH_CACHE_TIMEOUT)
    return G


def invalidate_graph(*, rebuild: bool = False) -> None:
    """
    Delete the cached graph.

    Args:
        rebuild: If ``True`` (Option B / eager), immediately rebuild and
                 re-cache the graph so the next read is instant.  Defaults to
                 ``False`` (Option A / lazy) to avoid redundant rebuilds when
                 multiple writes happen in quick succession.
    """
    cache.delete(GRAPH_CACHE_KEY)
    if rebuild:
        G = build_graph()
        cache.set(GRAPH_CACHE_KEY, G, timeout=GRAPH_CACHE_TIMEOUT)


# ---------------------------------------------------------------------------
# Query helpers
# ---------------------------------------------------------------------------

def _ensure_node_in_graph(G: nx.DiGraph, node_id: int) -> None:
    if node_id not in G:
        raise NodeNotInGraphError(
            f"Node {node_id} is not present in the graph."
        )


def get_descendants(node_id: int) -> set[int]:
    """Return all descendant node IDs reachable from *node_id*."""
    G = get_graph()
    _ensure_node_in_graph(G, node_id)
    return nx.descendants(G, node_id)


def get_ancestors(node_id: int) -> set[int]:
    """Return all ancestor node IDs that can reach *node_id*."""
    G = get_graph()
    _ensure_node_in_graph(G, node_id)
    return nx.ancestors(G, node_id)


def has_cycle() -> bool:
    """Return ``True`` if the graph contains at least one cycle."""
    G = get_graph()
    return not nx.is_directed_acyclic_graph(G)


def get_cycles() -> list[list[int]]:
    """Return every simple cycle in the graph (for debugging / visibility)."""
    G = get_graph()
    return list(nx.simple_cycles(G))
