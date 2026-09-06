# Private runtime assets

Participant-specific conversion models and correction tables are data dependencies.
They must reach the replacement host unchanged, but must not enter source releases
or container images. They are separate from the generic beta-peak models bundled
with BRAVO.

From the checkout root, run:

```bash
python3 scripts/prepare_private_runtime.py
```

The helper copies legacy files from `BRAVO/config/` and
`BRAVO/modules/Biomarkers/data/psd_lsb_models/` into the corresponding directories
inside ignored `secrets/runtime_assets/`. It keeps originals unchanged, verifies
SHA-256 hashes, restricts file permissions, and refuses to replace a differing
destination. Resolve a conflict by reviewing the two versions; do not discard a
reviewed model or policy to make deployment proceed.

`secrets/runtime_assets/manifest.json` records the private asset hashes and sizes.
Compose mounts both directories read-only into the server and sync containers at
their original application paths. Analysis, cache fingerprints and source policy
loaders therefore see the same files without code or scientific parameter changes.
Both `bravo-appliance up` and `bravo-restore` prepare these mounts before startup.

The sensitive appliance backup includes `secrets/`, so a new backup includes these
assets. Compare its private manifest against the replacement host after restore.
An older backup may predate the migration: transfer the prepared asset directory
privately as well. Never upload the private manifest or files to GitHub. A source
clone or a Docker image alone does not carry these participant models.

Independent empty installations create empty asset directories and supply their
own reviewed data. They must not receive the shared research instance's assets or
credentials automatically. Missing participant models retain the application's
existing unavailable behavior.

The ignore rules protect new builds and new untracked files. They do not erase
files already tracked in local history. Publication must use the separately
reviewed source snapshot and outgoing-history audit.
