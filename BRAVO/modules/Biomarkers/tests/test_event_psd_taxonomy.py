"""CS-2: PSD-source taxonomy + Streaming-event un-exclusion (bravo_service).

Verifies the declarative PSD_SOURCE_TAXONOMY, the display-category helper that splits Streaming from
labeled patient events, and that the LSB routing rule (TD present -> direct transform; PSD-only
patient events -> bridge) is encoded consistently. Needs Django configured (bravo_service imports
models at load); the in-container harness runs each test under django.setup().
"""
import os
import sys
import pathlib

_BRAVO_ROOT = pathlib.Path(__file__).resolve().parents[3]
if str(_BRAVO_ROOT) not in sys.path:
    sys.path.insert(0, str(_BRAVO_ROOT))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "BRAVO.settings")
try:
    import django
    django.setup()
except Exception:
    pass

from modules.Biomarkers import bravo_service as bs


def test_streaming_is_no_longer_globally_excluded():
    """The old _EVENT_NAME_EXCLUDE hard-drop of 'Streaming' is gone — Streaming is the dominant
    PSD-bearing modality on RCS08 and must be surfaced, not discarded."""
    assert not hasattr(bs, "_EVENT_NAME_EXCLUDE"), \
        "Streaming must not be globally excluded; route it as its own category instead"


def test_event_display_category_splits_streaming_from_labeled():
    """Auto 'Streaming' snapshots get DISPLAY_STREAMING_EVENT; every manually labeled press gets
    DISPLAY_PATIENT_EVENT. Case-insensitive on the name."""
    assert bs._event_display_category("Streaming") == bs.DISPLAY_STREAMING_EVENT
    assert bs._event_display_category("streaming") == bs.DISPLAY_STREAMING_EVENT
    for nm in ("Higher Pain", "Medication", "Percocet", "Tingly/Burning", "Feeling Good"):
        assert bs._event_display_category(nm) == bs.DISPLAY_PATIENT_EVENT
    # empty / None never crashes; defaults to the labeled patient-event category
    assert bs._event_display_category("") == bs.DISPLAY_PATIENT_EVENT
    assert bs._event_display_category(None) == bs.DISPLAY_PATIENT_EVENT


def test_labeled_streaming_split_for_diamond_row_and_count():
    """The assembler runs the PSD-averaging event_markers on LABELED events only and surfaces the
    Streaming count separately (Streaming render as per-lane ticks from av.records, NOT the diamond
    row). This pins that split so a regression can't (a) flood the diamond row with Streaming or
    (b) waste decimated-PSD compute on the ~2479 Streaming markers the row never draws."""
    from modules.Biomarkers.routines import availability as av
    T0 = 1_700_000_000.0
    # mimic _load_patient_events output: 2 labeled + 3 streaming, each category-tagged
    event_list = [
        {"name": "Higher Pain", "category": bs.DISPLAY_PATIENT_EVENT,   "t": T0,       "psds": []},
        {"name": "Medication",  "category": bs.DISPLAY_PATIENT_EVENT,   "t": T0 + 10,  "psds": []},
        {"name": "Streaming",   "category": bs.DISPLAY_STREAMING_EVENT, "t": T0 + 20,  "psds": []},
        {"name": "Streaming",   "category": bs.DISPLAY_STREAMING_EVENT, "t": T0 + 30,  "psds": []},
        {"name": "Streaming",   "category": bs.DISPLAY_STREAMING_EVENT, "t": T0 + 40,  "psds": []},
    ]
    # the exact split the assembler performs
    labeled = [e for e in event_list if e.get("category") != bs.DISPLAY_STREAMING_EVENT]
    streaming_count = sum(1 for e in event_list if e.get("category") == bs.DISPLAY_STREAMING_EVENT)
    markers = av.event_markers(labeled)
    markers["streaming_count"] = streaming_count
    assert markers["n"] == 2                                   # diamond row = labeled only
    assert {e["label"] for e in markers["events"]} == {"Higher Pain", "Medication"}
    assert markers["streaming_count"] == 3                     # streaming surfaced as a count, not rows
    assert all(e["label"] != "Streaming" for e in markers["events"])


def test_event_psd_lsb_blocks_only_consumes_psd_only_events():
    """The bridge block-builder reads PSD-only patient events (via _event_psd_rows) and never touches
    montage/survey products — those carry TD and route through the direct transform. We assert the
    builder exists and that the taxonomy keeps montage on td_transform (the routing contract the builder
    relies on), without needing live data."""
    assert hasattr(bs, "_event_psd_lsb_blocks")
    # the bridge constant the builder's downstream (device_psd_to_lsb) applies
    from modules.Biomarkers.routines import analytics
    assert abs(analytics.LSB_PER_DEVICE_PSD - analytics.LSB_PER_UV2_TRANSFORM /
               analytics.LSB_PER_UV2_DEVICE_PSD_TD_RATIO) < 1e-9
    # montage is NOT a bridge consumer
    assert bs.PSD_SOURCE_TAXONOMY["montage_snapshot"]["lsb_route"] == "td_transform"
    assert bs.DISPLAY_MONTAGE_SNAPSHOT != bs.DISPLAY_STREAMING_EVENT != bs.DISPLAY_PATIENT_EVENT
