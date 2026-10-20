"""The Closed-Loop report's stability model, as a task for the worker's helper process (the PI,
2026-10-04, decision 427). The report submits it before its other work (`adapter._submit_stability`)
and reads the answer where it used to compute it (`adapter._stability_result`), so the model's
several seconds run beside the rest of the report instead of after it.

`stability_core` runs in the helper: it applies the parent's store settings first (a test sandbox,
a scratch store and the ledger switch stay what the caller set), then calls the same
`Biomarkers.bravo_service._validate_band_core` the report called in-process, and returns only the
three fields the report reads.
"""


def _modules():
    try:
        from modules.CacheStore import store as st, ledger as lg
        from modules.Biomarkers import bravo_service as bs
    except ImportError:                                   # pragma: no cover - host spelling
        from CacheStore import store as st, ledger as lg
        from Biomarkers import bravo_service as bs
    return st, lg, bs


def current_overrides():
    """The store settings of this process, for the helper to apply."""
    import os
    st, lg, bs = _modules()
    return {"store_dir": st.DIR_OVERRIDE, "store_enabled": st.ENABLED, "ledger": lg.ENABLED,
            "biomarkers_dir": bs._SHARED_CACHE_DIR_OVERRIDE,
            "env": {k: os.environ[k] for k in ("BRAVO_PT_CONFIG_DIR",) if k in os.environ}}


def stability_core(body, overrides):
    """`_validate_band_core(body)` under the parent's store settings: available, reason, stim."""
    import os
    for k, v in (overrides.get("env") or {}).items():
        os.environ[k] = v
    st, lg, bs = _modules()
    st.DIR_OVERRIDE = overrides.get("store_dir")
    st.ENABLED = overrides.get("store_enabled", True)
    lg.ENABLED = overrides.get("ledger", True)
    bs._SHARED_CACHE_DIR_OVERRIDE = overrides.get("biomarkers_dir")
    with bs.pro_request_scope():
        core = bs._validate_band_core(body)
    return {"available": core.get("available"), "reason": core.get("reason"),
            "stim": core.get("stim")}
