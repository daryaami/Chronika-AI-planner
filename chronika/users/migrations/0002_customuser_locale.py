from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("users", "0001_initial"),
    ]

    operations = [
        migrations.AddField(
            model_name="customuser",
            name="locale",
            field=models.CharField(
                blank=True,
                help_text="BCP 47 tag from Google account (e.g. ru, en-US)",
                max_length=35,
                null=True,
            ),
        ),
    ]
