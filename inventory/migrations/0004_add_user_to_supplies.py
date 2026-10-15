import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


def delete_existing_rows(apps, schema_editor):
    apps.get_model("inventory", "TrackedSupply").objects.all().delete()
    apps.get_model("inventory", "InsulinBox").objects.all().delete()


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("inventory", "0003_alter_trackedsupply_last_used_at"),
    ]

    operations = [
        migrations.AddField(
            model_name="trackedsupply",
            name="user",
            field=models.ForeignKey(
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name="tracked_supplies",
                to=settings.AUTH_USER_MODEL,
            ),
        ),
        migrations.AddField(
            model_name="insulinbox",
            name="user",
            field=models.ForeignKey(
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name="insulin_boxes",
                to=settings.AUTH_USER_MODEL,
            ),
        ),
        migrations.RunPython(delete_existing_rows, migrations.RunPython.noop),
        migrations.AlterField(
            model_name="trackedsupply",
            name="user",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.CASCADE,
                related_name="tracked_supplies",
                to=settings.AUTH_USER_MODEL,
            ),
        ),
        migrations.AlterField(
            model_name="insulinbox",
            name="user",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.CASCADE,
                related_name="insulin_boxes",
                to=settings.AUTH_USER_MODEL,
            ),
        ),
        migrations.AlterField(
            model_name="trackedsupply",
            name="supply_type",
            field=models.CharField(
                choices=[("pump_sites", "Pump Sites"), ("cgms", "CGMs")],
                max_length=10,
                verbose_name="Supply Type",
            ),
        ),
        migrations.AddConstraint(
            model_name="trackedsupply",
            constraint=models.UniqueConstraint(
                fields=("user", "supply_type"), name="unique_supply_per_user"
            ),
        ),
    ]
