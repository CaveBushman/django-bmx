from django.db import migrations


def ensure_pl_hu_columns(apps, schema_editor):
    News = apps.get_model("news", "News")
    table_name = News._meta.db_table
    existing_columns = {
        column.name
        for column in schema_editor.connection.introspection.get_table_description(
            schema_editor.connection.cursor(),
            table_name,
        )
    }

    columns = [
        ("audio_file_hu", "varchar(100) NULL"),
        ("audio_file_pl", "varchar(100) NULL"),
        ("content_hu", "text NOT NULL DEFAULT ''"),
        ("content_pl", "text NOT NULL DEFAULT ''"),
        ("prefix_hu", "text NOT NULL DEFAULT ''"),
        ("prefix_pl", "text NOT NULL DEFAULT ''"),
        ("title_hu", "varchar(255) NOT NULL DEFAULT ''"),
        ("title_pl", "varchar(255) NOT NULL DEFAULT ''"),
    ]
    quoted_table = schema_editor.quote_name(table_name)
    for name, definition in columns:
        if name in existing_columns:
            continue
        schema_editor.execute(f"ALTER TABLE {quoted_table} ADD COLUMN {schema_editor.quote_name(name)} {definition}")
        existing_columns.add(name)


class Migration(migrations.Migration):

    dependencies = [
        ("news", "0046_add_pl_hu_fields"),
    ]

    operations = [
        migrations.RunPython(ensure_pl_hu_columns, migrations.RunPython.noop),
    ]
