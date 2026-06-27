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


def test_streaming_and_labeled_share_pooling_source_but_differ_in_display():
    """The two axes are kept distinct: Streaming and labeled events POOL together (same onboard-FFT
    units, same EVENT_PSD_SOURCE z-score group) yet are DIFFERENT display categories. Collapsing the
    two axes is exactly the bug CS-2 fixes."""
    tax = bs.PSD_SOURCE_TAXONOMY
    pe, se = tax["patient_event"], tax["streaming_event"]
    assert pe["pooling_source"] == se["pooling_source"] == bs.EVENT_PSD_SOURCE      # pool together
    assert pe["display"] != se["display"]                                          # display apart
    assert se["display"] == bs.DISPLAY_STREAMING_EVENT
    assert pe["display"] == bs.DISPLAY_PATIENT_EVENT


def test_taxonomy_lsb_routing_rule_matches_td_presence():
    """LSB route is decided by TD presence: a product WITH TD uses the direct TD->LSB transform; a
    PSD-only product (patient-triggered events) uses the PSD->LSB bridge. This is the contract CS-3
    consumes — montage snapshots are the bridge's calibration source, never a consumer."""
    tax = bs.PSD_SOURCE_TAXONOMY
    for key, spec in tax.items():
        if spec["has_td"]:
            assert spec["lsb_route"] == "td_transform", f"{key}: TD-bearing must route via transform"
        else:
            assert spec["lsb_route"] == "psd_bridge", f"{key}: PSD-only must route via bridge"
    # the two event sources are PSD-only -> bridge; the montage snapshot has TD -> transform
    assert tax["patient_event"]["has_td"] is False and tax["streaming_event"]["has_td"] is False
    assert tax["montage_snapshot"]["has_td"] is True
    assert tax["montage_snapshot"]["lsb_route"] == "td_transform"


def test_taxonomy_three_sources_have_distinct_display_categories():
    """All three PSD-event display categories are distinct, so none can masquerade as another on the
    timeline (the 'Streaming reads as Montage PSD' mislabel)."""
    tax = bs.PSD_SOURCE_TAXONOMY
    disp = {tax["patient_event"]["display"], tax["streaming_event"]["display"],
            tax["montage_snapshot"]["display"]}
    assert len(disp) == 3
    assert bs.DISPLAY_MONTAGE_SNAPSHOT != bs.DISPLAY_STREAMING_EVENT != bs.DISPLAY_PATIENT_EVENT
