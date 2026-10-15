from django.conf import settings
from django.db import models
from django.core.validators import MinValueValidator, MaxValueValidator


class SupplyType(models.TextChoices):
    PUMP_SITES = 'pump_sites', 'Pump Sites'
    CGMS = 'cgms', 'CGMs'


class InsulinBox(models.Model):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='insulin_boxes',
    )
    expiration_date = models.DateField(verbose_name='Expiration Date')
    vials_remaining = models.PositiveSmallIntegerField(
        verbose_name='Vials Remaining',
        default=5,
        validators=[MinValueValidator(1), MaxValueValidator(5)],
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['expiration_date']

    def __str__(self):
        return f"InsulinBox (expires: {self.expiration_date}, vials: {self.vials_remaining})"


class TrackedSupply(models.Model):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='tracked_supplies',
    )
    supply_type = models.CharField(
        max_length=10,
        choices=SupplyType.choices,
        verbose_name='Supply Type',
    )
    quantity = models.PositiveIntegerField(
        verbose_name='Quantity',
        default=0,
    )
    usage_interval_days = models.PositiveSmallIntegerField(
        verbose_name='Usage Interval (Days)',
    )
    last_used_at = models.DateField(
        null=True,
        blank=True,
        verbose_name='Last Used At',
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=['user', 'supply_type'],
                name='unique_supply_per_user',
            ),
        ]

    def __str__(self):
        return f"{self.supply_type} (qty: {self.quantity})"
