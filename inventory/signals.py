from django.contrib.auth import get_user_model
from django.db.models.signals import post_save
from django.dispatch import receiver

from inventory.services import init_supplies


@receiver(post_save, sender=get_user_model())
def seed_supplies_for_new_user(sender, instance, created, **kwargs):
    if created:
        init_supplies(instance)
