"""The provenance chain, and the refusal to consume a product derived from your own output.

WHY THIS EXISTS, stated in full because it is the reason this step is ordered before any module
writes anything back.

The approved design makes the cache a route between the three modules rather than a one-way
speed-up: biomarker exploration writes its results, closed-loop deployment writes its verdict, and
Stim Optimizer reads both and writes its own outputs. Those arrows close a loop.

**Stim Optimizer decides which stimulation settings still need exploring. That decision determines
which recordings come to exist.** If it then reads a ground-truth verdict computed from those same
recordings and treats it as independent evidence, the exploration policy is confirming itself. The
failure has NO SYMPTOM: nothing crashes, no page errors, every number is internally consistent, and
the record simply looks like converging evidence when it is a loop. A reviewer reading the output
could not tell the difference, and neither could we.

So each stored product carries the KEYS OF EVERY INPUT IT DERIVED FROM, transitively. A module
asking for a product declares itself, and a product whose chain already contains that module's own
output is refused. The refusal is an exception rather than a silent miss, because a silent miss
would rebuild the same self-derived product and hand it over anyway.

**THIS IS PROVEN BY CONSTRUCTION, NOT ASSERTED.** `tests/test_provenance_cycle.py` builds a
deliberate cycle — Stim Optimizer's settings feed a biomarker result, which feeds a closed-loop
verdict, which Stim Optimizer then asks for — and fails if the refusal does not fire. A test that
only checks a hand-written chain would pass while the real wiring leaked.

WHAT THIS IS NOT. It is not a general dependency tracker and it does not version code. It answers
exactly one question: does this product's history contain anything the asking module produced?
"""

import logging

_log = logging.getLogger(__name__)


class SelfDerivedProduct(Exception):
    """Raised when a module asks for a product its own output helped produce.

    Deliberately NOT a subclass of anything the store treats as a miss. A miss means "rebuild it";
    this means "you must not have this at all", and rebuilding would produce the same thing.
    """


#: The three modules, by the name each one passes as `writer` and `consumer`. Kept as a set so a
#: typo in a call site is caught rather than silently creating a fourth module that no rule covers.
MODULES = ("biomarkers", "closed_loop", "stim_optimizer")

#: Products that are RAW rather than derived: they come from the device export or from REDCap, and
#: no module's choices produced them. A raw input can never close a cycle, so it is exempt.
#: The tiles belong here — they are built from the recordings with no knowledge of any analysis
#: choice, any pain rating or any exploration decision.
#:
#: `therapy_pain_matched` is here too, and the reason deserves a sentence. It is written by the
#: Stim Optimizer module's code, but it is a deterministic join of two raw inputs — the settings the
#: device was programmed with and the pain reports — under a fixed wash-in rule. It embodies no
#: exploration decision, so a product derived from it is not "derived from Stim Optimizer's
#: choices", and refusing it to Stim Optimizer would refuse the very table step 5 exists to give it.
#: What Stim Optimizer CHOOSES — the ladder of settings it recommends exploring — is the
#: `exploration_ladder` kind, which stays derived and is what the constructed-cycle test refuses.
#: (It was called `settings_stream` until 2026-09-07; that name collided with the function that
#: reads the device's programmed history, a different and raw thing.)
#: `biomarker_psd_matrix` (Track E, decision 52) is the assembled per-channel spectrum matrix, a
#: deterministic decode-and-Welch of the device's own recordings with no other module's choices
#: baked in, the same reasoning that makes the tile cache raw.
RAW_KINDS = ("raw_lsb_tiles", "redcap_reports", "therapy_settings", "therapy_pain_matched",
            "biomarker_psd_matrix")


def module_of(key):
    """The module that wrote the product this key names, or None when the key says nothing.

    A key is `kind/participant/signature`. The writer is recorded in the chain entries rather than
    inferred from the kind, because two modules can legitimately write the same kind — but a bare
    string key with no writer still has to be interpretable, so the kind is the fallback.
    """
    if not isinstance(key, str):
        return None
    kind = key.split("/", 1)[0]
    return _WRITER_BY_KIND.get(kind)


#: Which module owns each kind. Only used when a chain entry carries no explicit writer.
_WRITER_BY_KIND = {
    "raw_lsb_tiles": "biomarkers",
    "biomarker_band_results": "biomarkers",
    "biomarker_band_correlation": "biomarkers",
    "biomarker_band_discrimination": "biomarkers",
    "biomarker_band_sweep": "biomarkers",
    "redcap_reports": "biomarkers",
    "therapy_settings": "stim_optimizer",
    "therapy_pain_matched": "stim_optimizer",
    "inputs": "closed_loop",
    "response": "closed_loop",
    "ground_truth_verdict": "closed_loop",
    "amplitude_effect_by_band": "closed_loop",
    "exploration_ladder": "stim_optimizer",
    "exploration_batch": "stim_optimizer",
    "stim_optimizer_summary": "stim_optimizer",
    "stim_optimizer_manifest": "stim_optimizer",
    "stim_optimizer_response": "stim_optimizer",
}


def entry(key, *, kind=None, writer=None, chain=None):
    """One link in a provenance chain.

    `chain` is the FLATTENED history of the input, so a chain is never walked lazily across files:
    a product's own sidecar holds everything needed to answer the refusal question without opening
    any other entry. That costs a little space and buys the property that a refusal cannot be
    defeated by an input file having been swept.
    """
    return {"key": key, "kind": kind, "writer": writer, "chain": list(chain or [])}


def flatten(inputs):
    """The transitive set of keys behind a list of provenance entries, plus the entries themselves.

    Returns a list of dicts suitable for a sidecar's `provenance` field. Duplicates are collapsed
    on the key, because the same tile entry legitimately feeds several inputs and counting it twice
    tells no one anything.
    """
    seen, out = set(), []
    for item in inputs or []:
        if isinstance(item, str):
            item = entry(item, kind=item.split("/", 1)[0], writer=module_of(item))
        if not isinstance(item, dict):
            continue
        key = item.get("key")
        if key is None or key in seen:
            continue
        seen.add(key)
        out.append({"key": key, "kind": item.get("kind"), "writer": item.get("writer")})
        for inner in item.get("chain") or []:
            ikey = inner.get("key") if isinstance(inner, dict) else inner
            if ikey is None or ikey in seen:
                continue
            seen.add(ikey)
            if isinstance(inner, dict):
                out.append({"key": ikey, "kind": inner.get("kind"),
                            "writer": inner.get("writer")})
            else:
                out.append({"key": ikey, "kind": str(ikey).split("/", 1)[0],
                            "writer": module_of(ikey)})
    return out


def writers_in(chain):
    """Every module that contributed anything to this chain, excluding raw inputs."""
    out = set()
    for item in chain or []:
        if isinstance(item, str):
            kind, writer = item.split("/", 1)[0], module_of(item)
        elif isinstance(item, dict):
            kind = item.get("kind") or str(item.get("key") or "").split("/", 1)[0]
            writer = item.get("writer") or module_of(item.get("key") or "")
        else:
            continue
        if kind in RAW_KINDS:
            continue
        if writer:
            out.add(writer)
    return out


def refusal_for(consumer, chain):
    """The reason this consumer must not have this product, or None when it may.

    Returning a sentence rather than a boolean is deliberate: the reason is logged and shown, and a
    bare False would leave whoever hits it guessing which input closed the loop.
    """
    if consumer is None:
        return None
    if consumer not in MODULES:
        # An unknown consumer name is a call-site bug. Refuse rather than wave it through, because
        # a name that matches nothing would silently exempt itself from every rule here.
        return (f"{consumer!r} is not one of the three modules {MODULES}; a product cannot be "
                f"released to a consumer whose identity the provenance rules do not cover")
    contributors = writers_in(chain)
    if consumer in contributors:
        offending = [c.get("key") for c in (chain or [])
                     if isinstance(c, dict)
                     and (c.get("writer") or module_of(c.get("key") or "")) == consumer
                     and (c.get("kind") or "") not in RAW_KINDS]
        return (f"this product derives from {consumer}'s own output ({', '.join(map(str, offending[:3]))}"
                f"{' and more' if len(offending) > 3 else ''}), so consuming it would let "
                f"{consumer}'s choices confirm themselves")
    return None

