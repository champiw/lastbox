from django.db import models
from django.core.validators import MinValueValidator, MaxValueValidator


class SupplyType(models.TextChoices):
    PUMP_SITES = 'pump_sites', 'Pump Sites'
    CGMS = 'cgms', 'CGMs'


class InsulinBox(models.Model):
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
    supply_type = models.CharField(
        max_length=10,
        choices=SupplyType.choices,
        unique=True,
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

    def __str__(self):
        return f"{self.supply_type} (qty: {self.quantity})"
