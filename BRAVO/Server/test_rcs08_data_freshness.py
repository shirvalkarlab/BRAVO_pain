"""Represented-time boundaries: never arrival, fetch range or job completion."""
import datetime as dt
from types import SimpleNamespace as NS
from unittest.mock import patch

import pytest
from django.test import TestCase

from modules import RCS08DataFreshness as fresh
from Server import models

NOW = dt.datetime(2026, 9, 5, 12, tzinfo=dt.timezone.utc).timestamp()


@pytest.mark.parametrize("value", [None, True, "2026-09-05", float("nan"), float("inf"), 0, -1, NOW + 1])
def test_bad_or_future_time_never_becomes_a_valid_freshness_time(value):
    assert not fresh.timestamp_entry(value, "source", "meaning", "missing", now=NOW)["available"]


def test_timestamp_value_is_actual_instant_and_display_timezone_is_explicit():
    entry = fresh.timestamp_entry(NOW - 60, "survey", "actual survey", "missing", now=NOW)
    assert entry["value"] == "2026-09-05T11:59:00+00:00"
    assert entry["timezone"] == "America/Los_Angeles" and entry["precision"] == "second"


class FreshnessDatabaseTests(TestCase):
    def setUp(self):
        self.institute = models.Institute.objects.create(name="local synthetic")
        self.other = models.Institute.objects.create(name="another institute")
        self.person = models.Participant.objects.create(name="RCS08", institute=self.institute)
        self.form = models.ScaleForms.objects.create(institute=self.institute, name="RCS08 Daily PRO (REDCap)",
            record_type="REDCap API Sync", record=[{
                "questions": [{"type": "score", "variableName": key} for key in fresh.RedcapTimeline.DAILY_MAPPING],
                "processing": {"timeline_schema": fresh.RedcapTimeline.VERSION, "reviewed_sha256": "a" * 64},
                "visit_context": {"version": fresh.RedcapVisitContext.VERSION, "reviewed_sha256": "a" * 64,
                                  "exclusion_reason": fresh.RedcapVisitContext.REASON,
                                  "metrics": {key: [] for key, _, _ in fresh.RedcapTimeline.METRICS}}}])

    def record(self, value, participant=None):
        return models.ScaleRecord.objects.create(participant=participant or self.person, source=self.form,
                                                  date=value, record=[])

    def test_latest_survey_uses_actual_record_and_clinic_context_not_form_upload_date(self):
        self.form.date = NOW + 10000
        self.form.save()
        self.record(NOW - 500)
        self.record(NOW + 1)
        other_person = models.Participant.objects.create(name="someone else", institute=self.other)
        self.record(NOW - 1, other_person)
        visit = self.form.record[0]["visit_context"]
        visit["metrics"]["mood_vas"] = [{"time": NOW - 100, "value": 50}]
        self.form.save()
        result = fresh.for_institute(self.institute, now=NOW)
        assert result["redcap"]["value"] == dt.datetime.fromtimestamp(NOW - 100, dt.timezone.utc).isoformat()
        assert not result["redcap"]["partial"]
        assert not result["oura"]["available"] and "measurements" in result["oura"]["source"]
        assert not result["neural_pdf"]["available"]
        assert not fresh.for_institute(self.other, now=NOW)["redcap"]["available"]

    def test_missing_empty_invalid_and_partial_reviewed_publications(self):
        assert not fresh.reviewed_survey(self.person, NOW)["available"]
        self.record(NOW - 100)
        self.form.record[0].pop("visit_context")
        self.form.save()
        result = fresh.reviewed_survey(self.person, NOW)
        assert result["available"] and result["partial"]
        self.form.record[0]["visit_context"] = "corrupt"
        self.form.save()
        assert fresh.reviewed_survey(self.person, NOW)["partial"]
        self.form.record = []
        self.form.save()
        assert not fresh.reviewed_survey(self.person, NOW)["available"]
        self.form.delete()
        assert not fresh.reviewed_survey(self.person, NOW)["available"]

    def test_renamed_owner_ambiguity_and_disappeared_owner_fail_closed(self):
        self.record(NOW - 100)
        models.SourceFile.objects.create(type="RCS08SurveyAudit", owner=self.person)
        self.person.name = "Renamed"
        self.person.save()
        with patch.object(fresh.time, "time", return_value=NOW):
            assert fresh.for_institute(self.institute)["redcap"]["available"]
        with patch.object(fresh.models.Participant, "find", return_value=None):
            assert not fresh.for_institute(self.institute, now=NOW)["redcap"]["available"]
        another = models.Participant.objects.create(name="RCS08", institute=self.institute)
        assert not fresh.for_institute(self.institute, now=NOW)["redcap"]["available"]
        assert another.uid != self.person.uid


def source(uid="good", **changes):
    return NS(**{**dict(uid=uid, owner_id="p", type="MedtronicJSON", metadata={"Device": "d"},
                        date=NOW + 50000), **changes})


def test_neural_session_time_is_native_cached_boundary_not_file_date_or_decoder_estimate(monkeypatch):
    person = NS(uid="p", name="RCS08")
    sources = [source(), source("empty"), source("missing"), source("excluded"),
               source("foreign", owner_id="other"), source("wrongtype", type="Other"),
               source("quarantined", metadata={"Device": "d", "AnalysisExclusion": "QC"}),
               source("nodevice", metadata={})]
    loaded = []
    def context(row, *args, **kwargs):
        loaded.append((row.uid, kwargs))
        if row.uid == "missing":
            return None, False
        return {"excluded": "wrong implant" if row.uid == "excluded" else None,
                "events": [] if row.uid == "empty" else [
                    {"kind": "settings_observed", "time": NOW - 10},
                    {"kind": "settings_observed", "time": NOW + 1},
                    {"kind": "settings_observed", "time": 1.},
                    {"kind": "group_change", "time": NOW - 1}]}, True
    monkeypatch.setattr(fresh.RedcapStimulation, "source_context", context)
    entry = fresh.neural_sessions(person, sources, NOW)
    assert entry["value"] == dt.datetime.fromtimestamp(NOW - 10, dt.timezone.utc).isoformat()
    assert entry["partial"] and entry["coverage"] == {"eligible_sources": 3, "cached_sources": 2, "dated_sources": 1}
    assert [uid for uid, _ in loaded] == ["good", "empty", "missing", "excluded"]
    assert all(kwargs == {"cached_only": True} for _, kwargs in loaded)
    monkeypatch.setattr(fresh.RCS08DataPolicy, "applies_to", lambda participant: False)
    assert not fresh.neural_sessions(person, [source()], NOW)["partial"]
    assert not fresh.neural_sessions(person, [], NOW)["available"]
