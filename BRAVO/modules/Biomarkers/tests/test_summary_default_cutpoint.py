"""The deployment summary's cut-point when the page sends none (the PI, 2026-10-04, decision 416).

The summary turns a cut-point into its device switching value. Until now it needed the page to send
one, and the page took it from the ROC panel, a separate request that answers later, so a summary
computed on choosing a band was marked "changed since" as soon as the ROC's point arrived. Now, with
no `Cutpoint` in the request, the summary takes the ROC's own default point -- the Youden point of
the ROC the summary itself builds, the point the ROC panel starts on -- and says which it used.

Values: a sent cut-point is used as sent; with none, the Youden point's threshold; with no ROC or no
Youden point, none, and the reason is named.
"""
from modules.Biomarkers import bravo_service as B

ROC = {"available": True, "operating_points": {"youden": {"threshold": 2.25, "rule": "youden"},
                                               "f1": {"threshold": 3.5, "rule": "f1"}}}


def test_a_sent_cutpoint_is_used_as_sent():
    cut, src = B._summary_cutpoint({"Cutpoint": "1.75"}, ROC)
    assert cut == 1.75 and src == "sent"


def test_with_none_sent_the_rocs_youden_point_is_used():
    cut, src = B._summary_cutpoint({}, ROC)
    assert cut == 2.25 and src == "roc_default_youden"


def test_with_no_roc_there_is_no_cutpoint_and_the_reason_is_named():
    cut, src = B._summary_cutpoint({}, {"available": False})
    assert cut is None and src == "none: the ROC is not available"
    cut, src = B._summary_cutpoint({}, {"available": True, "operating_points": {}})
    assert cut is None and src == "none: the ROC has no Youden point"
