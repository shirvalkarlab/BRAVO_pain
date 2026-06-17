# Adds an indexed Recording.content_fingerprint column: a DETERMINISTIC HMAC of the uncompressed
# recording payload, used for duplicate detection. The per-recording duplicate check in
# MedtronicPerceptJSONDecoder now filters on (content_fingerprint, source__owner) instead of the old
# (metadata=<full JSON blob>, source__metadata__Uploader=<JSON_EXTRACT>) — the latter were
# un-indexable JSON-field full-table scans run once PER recording, the cause of the slow upload on a
# populated database. The existing `hashed` column cannot serve this role: it hashes the
# blosc2-COMPRESSED bytes and blosc2 compression is non-deterministic, so `hashed` differs on every
# upload of identical data. New column; existing rows backfill to "" (they predate the dedup change
# and are matched by the legacy path until re-uploaded). Indexing it makes the check an index seek.

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('Server', '0007_sourcefile_unique_hashed'),
    ]

    operations = [
        migrations.AddField(
            model_name='recording',
            name='content_fingerprint',
            field=models.CharField(db_index=True, default='', max_length=64),
        ),
    ]
