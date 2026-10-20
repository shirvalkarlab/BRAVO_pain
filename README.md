# BRAVO · Aditya Jetstream

[Open the shared BRAVO site](https://bravo-aditya.mde260021.projects.jetstream-cloud.org/).
Sign in with your individual BRAVO account. Access is arranged privately through
the site administrator; this repository does not contain credentials or data.
The former laptop and Tailscale link are no longer required.

This `aditya` branch combines the Fixel development platform, Prasad's pain
analysis modules and Aditya's **All Data Streams** page. Prasad's analysis services
remain the scientific backend. The public source snapshot excludes private
clinical configuration, source data, operational receipts and private Git history.

## Start here

- [Lab user guide](docs/user-guide.md): find the custom modules, understand tabs,
  refresh data and interpret missing results.
- [Release status](docs/release-status.md): source version, deployed version,
  validation and known limits.
- [Operations guide](docs/operations-guide.md): sync, configuration and recovery.
- [Runtime and deployment](docs/runtime-and-deployment.md): independent installation.
- [Source provenance](docs/publication-provenance.md) and [initial import manifest](docs/source-import-manifest.json).

To find the custom modules, open an authorized participant and select
**Choosing stimulation settings → View**. This includes **Aditya - All Data
Streams**, **Biomarkers exploration**, **Stim optimizer** and **Closed-loop
deployment**. Standard reports are under **Brain Data** and the other categories.

A populated chart does not establish complete coverage or clinical suitability.
Read its dates, units, provenance and availability messages. A displayed candidate
is not an instruction to program a device.

## Development

Use Python 3.12 with `uv.lock` and Node 24 with the npm lockfile. Run from the root:

```sh
uv sync --frozen
uv run --frozen pytest tests/runtime -q
uv run --frozen python scripts/run_portable_tests.py
```

Frontend checks:

```sh
cd Client
npm ci
CI=true npm test -- --watchAll=false --runInBand
npm run build
```

These checks use isolated synthetic inputs. Never run inherited live/store tests
against production to validate a code change. Independent installations require
their own database, storage, encryption keys, provider access and reviewed
[clinical configuration](docs/private-clinical-configuration.md). Optional model
weights are provisioned separately; see [model assets](docs/optional-model-assets.md).

## Attribution

The University of Florida Brain Recording Analysis and Visualization Online
(BRAVO) platform processes and visualizes sensing-enabled neurostimulator data.
This integration preserves upstream licenses, including [LICENSE.md](LICENSE.md).
General upstream documentation is at [BRAVO documentation](https://bravo-documentation.jcagle.solutions/).

Cagle, J. N., Johnson, K. A., Almeida, L., Wong, J. K., Ramirez-Zamora, A., Okun,
M. S., et al. (2023). Brain Recording Analysis and Visualization Online (BRAVO):
An open-source visualization tool for deep brain stimulation data. *Brain
Stimulation*, 16(3), 793–797.

Report the page, selected settings, build revision and a sanitized error. Keep
participant identifiers, raw data, credentials and diagnostic exports out of
public GitHub issues.
