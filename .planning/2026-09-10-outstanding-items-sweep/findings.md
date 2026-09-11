# Findings — outstanding items sweep

## §1 Item 1, figure snapshots
- Audit item [49] (AUDIT_TRIAGE_v3): "Embed Plotly PNG snapshots of the 4 figures into the deploy
  export / printed sheet". The Closed-Loop page's Plotly figures, by section id: `#cl-roc`
  (DeploymentRocPanel: ROC curve, histogram, forward-validation — three divs), `#cl-lsb`
  (LsbPowerPanel: two divs), `#cl-era` (EraRefitPanel: one), `#cl-three-source` (two). The first
  three sit inside the collapsed "analyst" fold and exist only once it has been opened.
- The print stylesheet shows `.cl-signoff-card *`, so images inside the card print with no CSS change.
- `exportJson` builds the file from state; snapshots can be added as base64 PNG data URLs.
