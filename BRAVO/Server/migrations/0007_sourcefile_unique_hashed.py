# Adds an indexed SourceFile.unique_hashed column mirroring metadata["UniqueHashed"], so the
# upload duplicate check is an index seek instead of a JSON-extract full-table scan on MySQL
# (which grew slower with every stored file). Backfills existing rows from the JSON metadata.

from django.db import migrations, models


def backfill_unique_hashed(apps, schema_editor):
    SourceFile = apps.get_model("Server", "SourceFile")
    db_alias = schema_editor.connection.alias
    qs = SourceFile.objects.using(db_alias).all().only("uid", "metadata", "unique_hashed").iterator(chunk_size=500)
    batch = []
    for sf in qs:
        uh = ""
        try:
            uh = (sf.metadata or {}).get("UniqueHashed", "") or ""
        except AttributeError:
            uh = ""
        if uh and sf.unique_hashed != uh:
            sf.unique_hashed = uh
            batch.append(sf)
        if len(batch) >= 500:
            SourceFile.objects.using(db_alias).bulk_update(batch, ["unique_hashed"])
            batch = []
    if batch:
        SourceFile.objects.using(db_alias).bulk_update(batch, ["unique_hashed"])


def noop_reverse(apps, schema_editor):
    # Column is dropped by the reverse of AddField; nothing to undo in data.
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('Server', '0006_authenticationtokens'),
    ]

    operations = [
        migrations.AddField(
            model_name='sourcefile',
            name='unique_hashed',
            field=models.CharField(db_index=True, default='', max_length=64),
        ),
        migrations.RunPython(backfill_unique_hashed, noop_reverse),
    ]
