from django.db import migrations


def rename_prefix_columns(apps, schema_editor):
    """
    Renames prefix/prefix_XX columns to perex/perex_XX in the actual DB.
    The DB may be in a partial state (some perex_XX already exist), so each
    rename is conditional on what actually exists.
    """
    cursor = schema_editor.connection.cursor()
    cursor.execute("PRAGMA table_info(news_news)")
    existing = {row[1] for row in cursor.fetchall()}

    renames = [
        ("prefix", "perex"),
        ("prefix_en", "perex_en"),
        ("prefix_de", "perex_de"),
        ("prefix_sk", "perex_sk"),
        ("prefix_es", "perex_es"),
        ("prefix_it", "perex_it"),
        ("prefix_fr", "perex_fr"),
        ("prefix_pl", "perex_pl"),
        ("prefix_hu", "perex_hu"),
    ]

    for old, new in renames:
        if old in existing and new not in existing:
            schema_editor.execute(
                f"ALTER TABLE news_news RENAME COLUMN {schema_editor.quote_name(old)}"
                f" TO {schema_editor.quote_name(new)}"
            )
        elif old in existing and new in existing:
            # Both exist (partial DB state) — merge non-empty data then drop old column
            schema_editor.execute(
                f"UPDATE news_news SET {schema_editor.quote_name(new)} = {schema_editor.quote_name(old)}"
                f" WHERE ({schema_editor.quote_name(new)} IS NULL OR {schema_editor.quote_name(new)} = '')"
                f" AND {schema_editor.quote_name(old)} != ''"
            )
            schema_editor.execute(
                f"ALTER TABLE news_news DROP COLUMN {schema_editor.quote_name(old)}"
            )


class Migration(migrations.Migration):

    dependencies = [
        ("news", "0047_ensure_pl_hu_columns"),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            database_operations=[
                migrations.RunPython(rename_prefix_columns, migrations.RunPython.noop),
            ],
            state_operations=[
                migrations.RenameField(model_name="news", old_name="prefix", new_name="perex"),
                migrations.RenameField(model_name="news", old_name="prefix_en", new_name="perex_en"),
                migrations.RenameField(model_name="news", old_name="prefix_de", new_name="perex_de"),
                migrations.RenameField(model_name="news", old_name="prefix_sk", new_name="perex_sk"),
                migrations.RenameField(model_name="news", old_name="prefix_es", new_name="perex_es"),
                migrations.RenameField(model_name="news", old_name="prefix_it", new_name="perex_it"),
                migrations.RenameField(model_name="news", old_name="prefix_fr", new_name="perex_fr"),
                migrations.RenameField(model_name="news", old_name="prefix_pl", new_name="perex_pl"),
                migrations.RenameField(model_name="news", old_name="prefix_hu", new_name="perex_hu"),
            ],
        ),
    ]
