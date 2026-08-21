"""
Management command: rebuild_node_graphs

Warms (or re-warms) the global Node graph cache.  Useful after bulk imports,
cache flushes, or Redis restarts.

Usage:
    python manage.py rebuild_node_graphs
"""

from django.core.management.base import BaseCommand

from users.graph_utils import build_graph, GRAPH_CACHE_KEY, GRAPH_CACHE_TIMEOUT
from django.core.cache import cache


class Command(BaseCommand):
    help = "Rebuild and cache the global Node directed graph."

    def handle(self, *args, **options):
        self.stdout.write("Building Node graph …")

        G = build_graph()
        cache.set(GRAPH_CACHE_KEY, G, timeout=GRAPH_CACHE_TIMEOUT)

        self.stdout.write(
            self.style.SUCCESS(
                f"Cached graph with {G.number_of_nodes()} nodes "
                f"and {G.number_of_edges()} edges."
            )
        )
