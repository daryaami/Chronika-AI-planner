# Generated manually

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("events", "0010_alter_event_htmllink"),
    ]

    operations = [
        migrations.AddField(
            model_name="event",
            name="google_sync_status",
            field=models.CharField(
                choices=[
                    ("PENDING", "Pending Google sync"),
                    ("SYNCED", "Synced with Google"),
                    ("FAILED", "Google sync failed"),
                ],
                default="SYNCED",
                help_text="Состояние выгрузки в Google Calendar (асинхронно после локальных изменений).",
                max_length=16,
            ),
        ),
    ]
