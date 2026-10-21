# Public Aditya snapshot provenance

This publication updates the lab repository's existing `aditya` lineage from
`fd4a60b6e92dd04da9edbf265181ad4802a2f8ac`. The earlier release was published as a
reviewed tree snapshot through [PR #14](https://github.com/shirvalkarlab/BRAVO_pain/pull/14),
with its release documentation updated in [PR #15](https://github.com/shirvalkarlab/BRAVO_pain/pull/15).
These updates preserve the existing lab branch history.

The integration combines Fixel `development` at
`6f5d23a0056e0b0e0891561d214290a3476f89b8`, reviewed Prasad application changes from
`ps_closedloop_deployment-5qfvvu` through `9d6cafe483349139b5f9a36b30846307d21bf6f5`, and Aditya's presentation work.
The [initial import manifest](source-import-manifest.json) records the original
path-level import, not every subsequent file hash. Licenses and attribution remain
part of the source tree.

The shared-viewer follow-up was published through
[PR #16](https://github.com/shirvalkarlab/BRAVO_pain/pull/16), public candidate
`712e362ed15d01deaba5a15ab54ec3a6d44ea77c`, merged as
`86bbad6dbbe15263b01d486c47b7fe95c30003b0`. It adds reviewed access-control,
interface, synthetic-test and generic-documentation changes on the existing lab
lineage, retaining the repository boundaries below. Account credentials are not
included.

## Repository boundaries

- Historical deployment logs, participant-derived descriptions and private
  operational summaries are omitted or replaced with generic public guides.
- Participant-specific anatomy presentation overrides are absent. Display helpers
  preserve supplied labels instead of inferring anatomy from a study code.
- Clinic-workbook ingestion requires an explicit folder; it has no participant-
  specific default path.
- Command help, standalone mock titles and protocol explanatory caveats use generic
  language. The protocol assumptions and numeric thresholds are unchanged.
- Live-service harnesses and credential-bearing templates are excluded. Deployment
  templates require separately supplied configuration.
- Workspace instructions, checkout audit and CI triggers target the lab branch.
  Documentation updates do not change the running deployment.

The repository contains application code and reusable configuration templates;
deployment data and credentials are supplied separately. Scientific backend
calculations are retained, with explicit input requirements documented for
installation. Portable tests use synthetic inputs. Publication validation and hosted
acceptance are separate checkpoints in [release status](release-status.md).
