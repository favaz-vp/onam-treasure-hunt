# Re-export viewsets from game app for backward-compatibility
from game.views import NodeViewSet, MapViewSet

__all__ = [
    "NodeViewSet",
    "MapViewSet",
]
