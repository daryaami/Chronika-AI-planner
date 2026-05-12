from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("assistant", "0001_initial"),
    ]

    operations = [
        migrations.RunSQL(
            sql="""
                ALTER TABLE assistant_assistantsession
                ADD COLUMN IF NOT EXISTS updated_at timestamp with time zone;

                UPDATE assistant_assistantsession
                SET updated_at = created_at
                WHERE updated_at IS NULL;

                ALTER TABLE assistant_assistantsession
                ALTER COLUMN updated_at SET NOT NULL;
            """,
            reverse_sql="""
                ALTER TABLE assistant_assistantsession
                DROP COLUMN IF EXISTS updated_at;
            """,
        ),
    ]
