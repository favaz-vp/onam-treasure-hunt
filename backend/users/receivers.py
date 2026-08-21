from django.db.models.signals import post_save, post_delete, m2m_changed
from django.dispatch import receiver
from .models import User, Node


@receiver(post_save, sender=User)
def set_captain(sender, instance, **kwargs):
    if not instance.team or not instance.is_captain:
        return

    # Remove captain status from everyone else
    User.objects.filter(team=instance.team, is_captain=True).exclude(
        pk=instance.pk
    ).update(is_captain=False)


# ---------------------------------------------------------------------------
# Node graph cache invalidation
# ---------------------------------------------------------------------------

@receiver(post_save, sender=Node)
def invalidate_graph_on_node_save(sender, instance, created, **kwargs):
    """Invalidate the cached graph whenever a Node is created."""
    if created:
        from .graph_utils import invalidate_graph
        invalidate_graph()  # Option A (lazy). For eager: invalidate_graph(rebuild=True)


@receiver(post_delete, sender=Node)
def invalidate_graph_on_node_delete(sender, instance, **kwargs):
    """Invalidate the cached graph whenever a Node is deleted."""
    from .graph_utils import invalidate_graph
    invalidate_graph()


@receiver(m2m_changed, sender=Node.children.through)
def invalidate_graph_on_edge_change(sender, instance, action, **kwargs):
    """
    Invalidate the cached graph whenever edges (children) are added, removed,
    or cleared on a Node.
    """
    if action in ("post_add", "post_remove", "post_clear"):
        from .graph_utils import invalidate_graph
        invalidate_graph()
