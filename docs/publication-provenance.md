# Public Aditya snapshot provenance

This publication updates the lab repository's existing `aditya` lineage from
`fd4a60b6e92dd04da9edbf265181ad4802a2f8ac`. It is a reviewed tree snapshot of
integration source `05ce6fa6244bff65151af6b6d3ccc27215734329`, not a merge of the
private integration history.

The integration combines Fixel `development` at
`6f5d23a0056e0b0e0891561d214290a3476f89b8`, reviewed Prasad application changes from
`ps_closedloop_deployment-5qfvvu` through `9d6cafe483349139b5f9a36b30846307d21bf6f5`, and Aditya's presentation work.
The [initial import manifest](source-import-manifest.json) records the original
path-level import, not every subsequent file hash. Licenses and attribution remain
part of the source tree.

## Public snapshot differences

- Historical deployment logs, participant-derived descriptions and private
  operational summaries are omitted or replaced with generic public guides.
- Participant-specific anatomy presentation overrides are absent. Display helpers
  preserve supplied labels instead of inferring anatomy from a study code.
- Clinic-workbook ingestion requires an explicit folder; it has no participant-
  specific default path.
- Command help, standalone mock titles and protocol explanatory caveats use generic
  language. The protocol assumptions and numeric thresholds are unchanged.
- Private-source/live harness examples and a historical credential-bearing Docker
  template are omitted. Modern deployment templates require private configuration.
- Workspace instructions, checkout audit and CI triggers are adapted to the lab
  branch. Source references, raw archives and the running deployment are unchanged.

These are deliberate publication differences; the public branch is not a copy of
private deployment data/configuration. Scientific backend calculations are retained
except where an explicitly documented public-input requirement replaces a private
default. Portable tests use synthetic inputs. Publication validation and hosted
acceptance are separate checkpoints in [release status](release-status.md).
