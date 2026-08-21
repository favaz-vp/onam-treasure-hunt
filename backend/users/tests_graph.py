"""
Tests for the Node directed-graph cache layer (graph_utils + signals).

Fixture graph used by most tests:

    1 → 2 → 3 → 4 → 6 → 1        (cycle A)
                ↓
                5 → 7 → 8 → 9 → 4  (cycle B, rejoins via 4)
"""

from django.core.cache import cache
from django.test import TestCase, override_settings

from users.models import Node
from users.graph_utils import (
    GRAPH_CACHE_KEY,
    NodeNotInGraphError,
    build_graph,
    get_ancestors,
    get_cycles,
    get_descendants,
    get_graph,
    has_cycle,
    invalidate_graph,
)


# Force the default LocMemCache so tests don't depend on Redis.
@override_settings(
    CACHES={
        "default": {
            "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
            "LOCATION": "test-node-graph",
        }
    }
)
class GraphCacheInvalidationTests(TestCase):
    """Verify that signals correctly invalidate the cached graph."""

    def setUp(self):
        cache.clear()

    # -- creation ----------------------------------------------------------

    def test_cache_invalidated_on_node_create(self):
        """Creating a Node should delete the cached graph."""
        # Prime the cache
        get_graph()
        self.assertIsNotNone(cache.get(GRAPH_CACHE_KEY))

        # Create a node → cache should be gone
        Node.objects.create(data="new node")
        self.assertIsNone(cache.get(GRAPH_CACHE_KEY))

    # -- edge changes (M2M) -----------------------------------------------

    def test_cache_invalidated_on_child_add(self):
        """Adding a child edge should invalidate the cache."""
        n1 = Node.objects.create(data="n1")
        n2 = Node.objects.create(data="n2")
        cache.clear()

        # Prime
        get_graph()
        self.assertIsNotNone(cache.get(GRAPH_CACHE_KEY))

        # Add edge
        n1.children.add(n2)
        self.assertIsNone(cache.get(GRAPH_CACHE_KEY))

    def test_cache_invalidated_on_child_remove(self):
        """Removing a child edge should invalidate the cache."""
        n1 = Node.objects.create(data="n1")
        n2 = Node.objects.create(data="n2")
        n1.children.add(n2)
        cache.clear()

        # Prime
        get_graph()
        self.assertIsNotNone(cache.get(GRAPH_CACHE_KEY))

        # Remove edge
        n1.children.remove(n2)
        self.assertIsNone(cache.get(GRAPH_CACHE_KEY))

    def test_cache_invalidated_on_child_clear(self):
        """Clearing all children should invalidate the cache."""
        n1 = Node.objects.create(data="n1")
        n2 = Node.objects.create(data="n2")
        n1.children.add(n2)
        cache.clear()

        # Prime
        get_graph()
        self.assertIsNotNone(cache.get(GRAPH_CACHE_KEY))

        # Clear edges
        n1.children.clear()
        self.assertIsNone(cache.get(GRAPH_CACHE_KEY))

    # -- deletion ----------------------------------------------------------

    def test_cache_invalidated_on_node_delete(self):
        """Deleting a Node should invalidate the cache."""
        n = Node.objects.create(data="ephemeral")
        cache.clear()

        # Prime
        get_graph()
        self.assertIsNotNone(cache.get(GRAPH_CACHE_KEY))

        # Delete
        n.delete()
        self.assertIsNone(cache.get(GRAPH_CACHE_KEY))


@override_settings(
    CACHES={
        "default": {
            "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
            "LOCATION": "test-node-graph-traversal",
        }
    }
)
class GraphTraversalTests(TestCase):
    """
    Verify descendants / ancestors / cycle-detection on a graph with cycles.

    Graph structure (node PKs assigned after creation):

        1 → 2 → 3 → 4 → 6 → 1      (cycle A)
                    ↓
                    5 → 7 → 8 → 9 → 4  (cycle B, rejoins at 4)
    """

    @classmethod
    def setUpTestData(cls):
        # Create 9 nodes.  We rely on auto-incrementing PKs starting at 1
        # inside a clean test DB; if that ever changes, the assertions below
        # will need adjusting.
        cls.nodes = {}
        for i in range(1, 10):
            cls.nodes[i] = Node.objects.create(data=f"node-{i}", name=f"N{i}")

        # Wire up edges  (parent → child)
        cls.nodes[1].children.add(cls.nodes[2])   # 1→2
        cls.nodes[2].children.add(cls.nodes[3])   # 2→3
        cls.nodes[3].children.add(cls.nodes[4])   # 3→4
        cls.nodes[4].children.add(cls.nodes[6])   # 4→6
        cls.nodes[6].children.add(cls.nodes[1])   # 6→1  (closes cycle A)

        cls.nodes[4].children.add(cls.nodes[5])   # 4→5
        cls.nodes[5].children.add(cls.nodes[7])   # 5→7
        cls.nodes[7].children.add(cls.nodes[8])   # 7→8
        cls.nodes[8].children.add(cls.nodes[9])   # 8→9
        cls.nodes[9].children.add(cls.nodes[4])   # 9→4  (closes cycle B)

    def setUp(self):
        cache.clear()

    # -- descendants -------------------------------------------------------

    def test_get_descendants_from_node_1(self):
        """From node 1, every other node is reachable (cycles connect all)."""
        desc = get_descendants(self.nodes[1].pk)
        # nx.descendants always excludes the source node itself, even in
        # cycles, so node 1 is NOT in its own descendants set.
        expected = {self.nodes[i].pk for i in range(2, 10)}
        self.assertEqual(desc, expected)

    def test_get_descendants_from_node_5(self):
        """5 → 7 → 8 → 9 → 4 → {5,6}  → everything reachable."""
        desc = get_descendants(self.nodes[5].pk)
        # nx.descendants excludes the source node itself.
        expected = {self.nodes[i].pk for i in range(1, 10)} - {self.nodes[5].pk}
        self.assertEqual(desc, expected)

    # -- ancestors ---------------------------------------------------------

    def test_get_ancestors_of_node_6(self):
        """All nodes can reach node 6 through the cycles."""
        anc = get_ancestors(self.nodes[6].pk)
        # nx.ancestors excludes the source node itself.
        expected = {self.nodes[i].pk for i in range(1, 10)} - {self.nodes[6].pk}
        self.assertEqual(anc, expected)

    # -- cycles ------------------------------------------------------------

    def test_has_cycle(self):
        self.assertTrue(has_cycle())

    def test_get_cycles_returns_non_empty(self):
        cycles = get_cycles()
        self.assertGreater(len(cycles), 0)

    # -- guard: missing node -----------------------------------------------

    def test_descendants_of_missing_node_raises(self):
        with self.assertRaises(NodeNotInGraphError):
            get_descendants(999_999)

    def test_ancestors_of_missing_node_raises(self):
        with self.assertRaises(NodeNotInGraphError):
            get_ancestors(999_999)


@override_settings(
    CACHES={
        "default": {
            "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
            "LOCATION": "test-node-graph-acyclic",
        }
    }
)
class AcyclicGraphTests(TestCase):
    """Sanity-check on a simple DAG (no cycles)."""

    @classmethod
    def setUpTestData(cls):
        cls.a = Node.objects.create(data="A")
        cls.b = Node.objects.create(data="B")
        cls.c = Node.objects.create(data="C")
        cls.a.children.add(cls.b)
        cls.b.children.add(cls.c)

    def setUp(self):
        cache.clear()

    def test_no_cycle(self):
        self.assertFalse(has_cycle())

    def test_get_cycles_empty(self):
        self.assertEqual(get_cycles(), [])

    def test_descendants_chain(self):
        self.assertEqual(get_descendants(self.a.pk), {self.b.pk, self.c.pk})
        self.assertEqual(get_descendants(self.b.pk), {self.c.pk})
        self.assertEqual(get_descendants(self.c.pk), set())

    def test_ancestors_chain(self):
        self.assertEqual(get_ancestors(self.c.pk), {self.a.pk, self.b.pk})
        self.assertEqual(get_ancestors(self.b.pk), {self.a.pk})
        self.assertEqual(get_ancestors(self.a.pk), set())


@override_settings(
    CACHES={
        "default": {
            "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
            "LOCATION": "test-node-graph-rebuild",
        }
    }
)
class InvalidateRebuildTests(TestCase):
    """Verify the eager-rebuild (Option B) path."""

    def setUp(self):
        cache.clear()

    def test_invalidate_with_rebuild_populates_cache(self):
        Node.objects.create(data="x")
        cache.clear()
        self.assertIsNone(cache.get(GRAPH_CACHE_KEY))

        invalidate_graph(rebuild=True)
        self.assertIsNotNone(cache.get(GRAPH_CACHE_KEY))
