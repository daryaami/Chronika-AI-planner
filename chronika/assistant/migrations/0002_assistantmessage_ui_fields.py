# Generated manually for UUID + UI blocks (avoids interactive makemigrations on unique+default).

import uuid

from django.db import migrations, models


def fill_public_ids(apps, schema_editor):
    AssistantMessage = apps.get_model("assistant", "AssistantMessage")
    for row in AssistantMessage.objects.filter(public_id__isnull=True):
        row.public_id = uuid.uuid4()
        row.save(update_fields=["public_id"])


class Migration(migrations.Migration):

    dependencies = [
        ("assistant", "0001_initial"),
    ]

    operations = [
        migrations.AddField(
            model_name="assistantmessage",
            name="public_id",
            field=models.UUIDField(db_index=True, editable=False, null=True),
        ),
        migrations.AddField(
            model_name="assistantmessage",
            name="blocks",
            field=models.JSONField(
                blank=True,
                default=list,
                help_text="UI-блоки ответа ассистента (протокол чата).",
            ),
        ),
        migrations.AddField(
            model_name="assistantmessage",
            name="fsm_state",
            field=models.CharField(blank=True, default="", max_length=64),
        ),
        migrations.RunPython(fill_public_ids, migrations.RunPython.noop),
        migrations.AlterField(
            model_name="assistantmessage",
            name="public_id",
            field=models.UUIDField(
                db_index=True,
                default=uuid.uuid4,
                editable=False,
                unique=True,
            ),
        ),
    ]
