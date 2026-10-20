# Adds two indexed SourceFile columns mirroring JSON metadata, to turn the remaining upload-path
# JSON_EXTRACT full-table scans into index seeks:
#   - device:    mirrors metadata["Device"] (DBSDevice uid). The Therapy.checkDuplicate and
#                TherapyModification dedup checks filtered on source__metadata__Device (a JSON scan,
#                once per therapy / therapy-change-log entry); they now filter on source__device.
#   - institute: mirrors metadata["Institute"] (owning institute pk). The SourceFile dedup check
#                paired the indexed unique_hashed with metadata__Institute (a JSON scan); it now
#                pairs it with the indexed institute column.
# New columns; existing rows backfill to "" (matched by the legacy path until re-uploaded).

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('Server', '0008_recording_content_fingerprint'),
    ]

    operations = [
        migrations.AddField(
            model_name='sourcefile',
            name='device',
            field=models.CharField(db_index=True, default='', max_length=32),
        ),
        migrations.AddField(
            model_name='sourcefile',
            name='institute',
            field=models.CharField(db_index=True, default='', max_length=32),
        ),
    ]
