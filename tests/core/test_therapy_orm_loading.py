"""Real serializer/query-count regression in a service-free subprocess database."""
import json
import os
from pathlib import Path
import subprocess
import sys


def test_eager_therapy_loading_preserves_payload_and_bounds_queries(tmp_path):
    # No inherited settings, database credentials or service addresses reach the child.
    env = {"PATH": os.defpath, "HOME": str(tmp_path), "TMPDIR": str(tmp_path)}
    result = subprocess.run(
        [sys.executable, str(Path(__file__).resolve()), "--isolated-orm", str(tmp_path)],
        env=env, capture_output=True, text=True, timeout=90, check=True,
    )
    receipt = json.loads(result.stdout)
    assert receipt["cases"] == 5
    assert receipt["populated_queries"] == [3, 3, 3, 3]
    assert receipt["serialization_queries"] == [0, 0, 0, 0, 0]
    assert receipt["legacy_full_queries"] > 50


def isolated_orm_probe(root):
    from cryptography.fernet import Fernet
    app = Path(__file__).resolve().parents[2] / "BRAVO"
    sys.path[:0] = [str(app), str(app / "modules")]
    os.environ.update(DATASERVER_PATH=str(root) + os.sep,
                      DATASERVER_ENCRYPTION=Fernet.generate_key().decode(),
                      DATASERVER_HASHKEY="synthetic-therapy-loading")
    from django.conf import settings
    settings.configure(
        SECRET_KEY="synthetic-therapy-loading", USE_TZ=True,
        INSTALLED_APPS=["django.contrib.auth", "django.contrib.contenttypes", "Server"],
        DATABASES={"default": {"ENGINE": "django.db.backends.sqlite3", "NAME": str(root / "orm.sqlite3")}},
        AUTH_USER_MODEL="Server.PlatformUser", DEFAULT_AUTO_FIELD="django.db.models.BigAutoField",
    )
    import django
    django.setup()
    from django.core.management import call_command
    from django.db import connection
    from django.test.utils import CaptureQueriesContext
    from Server.models import Participant, SourceFile, Electrode
    from Server.models.Therapy import Therapy, ElectricalTherapy, ElectricalStimulation, AdaptiveTherapy
    assert connection.vendor == "sqlite" and Path(connection.settings_dict["NAME"]).parent == root
    call_command("migrate", verbosity=0, interactive=False)
    owner = Participant.objects.create(uid="synthetic-owner")
    other = Participant.objects.create(uid="synthetic-other")
    sources = [SourceFile.objects.create(uid=f"synthetic-source-{i}", owner=o,
               metadata={"Timezone": tz, "Device": f"synthetic-{i}"})
               for i, (o, tz) in enumerate(((owner, "UTC"), (other, "US/Eastern")))]
    electrode = Electrode.objects.create(uid="synthetic-lead", owner=owner,
                                         channel_names=["zero", "one", "two", "three"])
    groups = []
    for i in range(24):
        therapy = Therapy.objects.create(uid=f"synthetic-therapy-{i}", source=sources[i % 2],
                                         date=float(24 - i), type="Post-visit Therapy", name=f"visit-{i}")
        group = ElectricalTherapy.objects.create(therapy=therapy, group_id=str(i % 4),
                      group_name=f"group-{i}", label=f"label-{i}", stimulation_type=f"mode-{i}")
        groups.append(group)
        if i % 4 == 0:  # Empty settings remain empty; no join is allowed to drop the parent.
            continue
        for j in range(2):
            stim = ElectricalStimulation.objects.create(group=group, electrode=electrode,
                    contact=[j], return_contact=[-1], amplitude=float(j), amplitude_fraction=[100])
            group.stimulation_settings.add(stim)
        adaptive = AdaptiveTherapy.objects.create(group=group, sensing={"zero": 0, "missing": None})
        group.adaptive_settings.add(adaptive)
    # A shared M2M setting retains its own group, not the group currently serializing it.
    shared = groups[1].stimulation_settings.first()
    groups[2].stimulation_settings.add(shared)

    def legacy(**kwargs):
        return ElectricalTherapy.objects.select_related("therapy").filter(**kwargs).prefetch_related(
            "stimulation_settings", "adaptive_settings").all()

    cases = [({}, None, None), ({"pk": groups[1].pk}, None, None),
             ({"therapy__source__owner": owner}, "-therapy__date", None),
             ({}, "-pk", 3), ({"therapy__source__owner_id": "not-present"}, None, None)]
    populated_counts, serialization_counts, legacy_counts = [], [], []
    for filters, ordering, limit in cases:
        old, new = legacy(**filters), ElectricalTherapy.find_all(**filters)
        assert old.query.order_by == new.query.order_by
        if ordering:
            old, new = old.order_by(ordering), new.order_by(ordering)
        if limit:
            old, new = old[:limit], new[:limit]
        with CaptureQueriesContext(connection) as old_queries:
            old_rows = list(old)
            expected = [row.get_info() for row in old_rows]
        with CaptureQueriesContext(connection) as fetch_queries:
            new_rows = list(new)
        with CaptureQueriesContext(connection) as render_queries:
            actual = [row.get_info() for row in new_rows]
        assert actual == expected
        assert [row.pk for row in old_rows] == [row.pk for row in new_rows]
        assert len(fetch_queries) == (3 if new_rows else 1)
        assert len(render_queries) == 0
        if new_rows:
            populated_counts.append(len(fetch_queries))
        serialization_counts.append(len(render_queries))
        legacy_counts.append(len(old_queries))
    print(json.dumps({"cases": len(cases), "populated_queries": populated_counts,
                      "serialization_queries": serialization_counts, "legacy_full_queries": legacy_counts[0]}))


if __name__ == "__main__":
    assert sys.argv[1] == "--isolated-orm"
    isolated_orm_probe(Path(sys.argv[2]).resolve())
