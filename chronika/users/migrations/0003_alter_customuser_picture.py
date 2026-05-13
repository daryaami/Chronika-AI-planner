from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("users", "0002_customuser_locale"),
    ]

    operations = [
        migrations.AlterField(
            model_name="customuser",
            name="picture",
            field=models.URLField(blank=True, max_length=2048, null=True),
        ),
    ]
