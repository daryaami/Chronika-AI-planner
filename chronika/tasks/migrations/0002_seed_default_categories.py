from django.db import migrations

def create_default_categories(apps, schema_editor):
    Category = apps.get_model('tasks', 'Category')
    default_categories = [
        {"name": "Work", "color": "#A833FF"},
        {"name": "Personal", "color": "#33C1FF"},
    ]
    for cat in default_categories:
        Category.objects.get_or_create(
            name=cat["name"],
            user=None,
            defaults={"color": cat["color"], "is_default": True}
        )

def delete_default_categories(apps, schema_editor):
    Category = apps.get_model('tasks', 'Category')
    Category.objects.filter(user=None, is_default=True).delete()

class Migration(migrations.Migration):

    dependencies = [
        ('tasks', '0001_initial'),
    ]

    operations = [
        migrations.RunPython(create_default_categories, delete_default_categories),
    ]
