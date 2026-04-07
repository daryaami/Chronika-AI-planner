from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("tasks", "0006_remove_task_embedding"),
    ]

    operations = [
        migrations.RenameField(
            model_name="task",
            old_name="created_at",
            new_name="created",
        ),
        migrations.RenameField(
            model_name="task",
            old_name="updated_at",
            new_name="updated",
        ),
        migrations.AlterModelOptions(
            name="task",
            options={"ordering": ["-due_date", "-created"]},
        ),
    ]

