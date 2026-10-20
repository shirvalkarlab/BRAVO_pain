"""Join the additive Fixel and Prasad schema histories without rewriting either."""
from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("Server", "0010_recording_fs_scaling_factor"),
        ("Server", "0009_sourcefile_device_institute"),
    ]
    operations = []
