from django.db.models.signals import post_save
from django.dispatch import receiver
from .models import User


@receiver(post_save, sender=User)
def set_captain(sender, instance, **kwargs):
    if not instance.team or not instance.is_captain:
        return

    # Remove captain status from everyone else
    User.objects.filter(team=instance.team, is_captain=True).exclude(
        pk=instance.pk
    ).update(is_captain=False)
