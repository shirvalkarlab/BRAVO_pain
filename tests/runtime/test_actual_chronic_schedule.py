"""Real disposable database checks for complete, atomic schedule publication."""
from test_optional_oauth_startup import isolated


def test_schedule_preparation_is_owner_scoped_complete_and_atomic(tmp_path):
    isolated(tmp_path, '''
        import copy
        from unittest.mock import patch
        from django.core.management import call_command
        from Server import models
        from modules import DataCurator
        from modules.MedtronicPercept import chronic_schedule as C
        call_command("migrate", verbosity=0, interactive=False)
        person = models.Participant.objects.create(name="Synthetic owner")
        foreign = models.Participant.objects.create(name="Synthetic other owner")
        dev = models.DBSDevice.objects.create(owner=person, serial_number="SYNTHETIC", type="Percept RC")
        other = models.DBSDevice.objects.create(owner=foreign, serial_number="SYNTHETIC", type="Percept RC")
        empty = {"starts": [], "ends": [], "switches": []}
        sources = [models.SourceFile.objects.create(owner=person, device=dev.uid, type="MedtronicJSON",
                    metadata={"SensingSettingsRecord": empty}) for _ in range(2)]
        # A matching serial belonging to another owner must never enter the inventory.
        models.SourceFile.objects.create(owner=foreign, device=other.uid, type="MedtronicJSON", metadata={})
        rows = [models.Recording.objects.create(source=sf, type="MedtronicChronicBrainSense",
                    metadata={"ChannelNames": ["LeftHemisphere LFP"], "ContactSchedule": [[0,"1-3"]]}) for sf in sources]
        before = [copy.deepcopy(r.metadata) for r in rows]
        sources[1].metadata = {}
        sources[1].save()
        try:
            DataCurator.restamp_chronic_schedule(person, dev)
            raise AssertionError("missing source settings accepted")
        except ValueError:
            pass
        assert [models.Recording.objects.get(uid=r.uid).metadata for r in rows] == before
        sources[1].metadata = {"SensingSettingsRecord": empty}
        sources[1].save()
        original_save = models.Recording.save
        calls = []
        def fail_second(self, *args, **kw):
            calls.append(self.uid)
            if len(calls) == 2:
                raise RuntimeError("synthetic failed write")
            return original_save(self, *args, **kw)
        with patch.object(models.Recording, 'save', fail_second):
            try:
                DataCurator.restamp_chronic_schedule(person, dev)
                raise AssertionError("save failure swallowed")
            except RuntimeError:
                pass
        assert len(calls) == 2
        assert [models.Recording.objects.get(uid=r.uid).metadata for r in rows] == before
        result = DataCurator.restamp_chronic_schedule(person, dev)
        assert result['status'] == 'complete' and result['exports'] == 2
        for row in rows:
            row.refresh_from_db()
            assert row.metadata['ContactSchedule'] == [[0,'1-3']]
            assert row.metadata['ScheduleNoRecord'] == [[0,None]]
        for source in sources:
            source.refresh_from_db()
            assert source.metadata['ChronicScheduleRestamp'] == result
        assert DataCurator.restamp_chronic_schedule(person, dev)['restamped'] == 0
    ''')
