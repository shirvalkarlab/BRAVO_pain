"""Probe the sensing-band center frequency on a participant's Power-Domain recordings.

Run INSIDE the container (the raw .bdat recordings aren't reachable from the agent sandbox):

    docker exec -i -w /usr/src/BRAVO bravo_pain-bravo-server-1 \
        python3 -W ignore manage.py shell < scripts/probe_power_freqs.py

Prints, per recorded power contact, the center frequency that the card will now display
('L 0⁻-3⁺ (region) @ XX.X Hz'). Confirms analytics.power_center_freqs against real device data.
"""
PARTICIPANT_UID = "1eda36458758461383721208bbe6bb87"   # RCS08

from modules.Biomarkers import bravo_service as bs   # noqa: E402
from modules.Biomarkers.routines import analytics    # noqa: E402

pd_list = bs._load_recordings(PARTICIPANT_UID, bs.POWERDOMAIN_TYPES)
print(f"Loaded {len(pd_list)} Power-Domain recordings")

# Show one raw Descriptor.Therapy snapshot so we can see exactly where the frequency lives.
# (Streaming Power-Domain stores FrequencyInHertz DIRECTLY on the hemisphere dict; chronic/other
#  firmware nests it under SensingSetup — the extractor probes both.)
for r in pd_list:
    desc = r.get("Descriptor") if isinstance(r, dict) else None
    therapy = desc.get("Therapy") if isinstance(desc, dict) else None
    if isinstance(therapy, dict):
        for hemi in ("Left", "Right"):
            h = therapy.get(hemi)
            if isinstance(h, dict):
                print(f"  sample {hemi} keys:", list(h.keys()))
                print(f"    {hemi}.FrequencyInHertz =", h.get("FrequencyInHertz"))
        break

freqs = analytics.power_center_freqs(pd_list)
print("\nPer-contact center frequencies (Hz):")
for contact, hz in freqs.items():
    print(f"  {contact}: {hz} Hz")

print("\nWhat the card will render:")
for p in bs._recorded_powers(pd_list):
    base = f"{p['label']} ({p['region']})" if p.get("region") else p["label"]
    line = f"{base} @ {p['center_hz']:.1f} Hz" if p.get("center_hz") is not None else f"{base} [no freq in export]"
    print("  ", line)
