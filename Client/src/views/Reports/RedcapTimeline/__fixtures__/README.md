# Synthetic adapter contract

`synthetic_adapter_output.json` is generated from independently authored inputs in
`generate_adapter_contract.py`, using the actual Aditya presentation adapter and
Prasad native-record decoder. It contains no participant records or downloaded
response data. Regenerate from the repository root with:

```sh
.venv/bin/python Client/src/views/Reports/RedcapTimeline/__fixtures__/generate_adapter_contract.py
```

The native input deliberately includes two invalid-power sentinel records with
valid amplitudes, producing singleton and two-point output segments. Source
settings contain two left programs and one right program, local electrode labels,
explicit SenSight geometry, microsecond pulse widths, and a 12,000-millisecond
cycling period with a 0.25 duty ratio. Those authored values provide independent
expected results in `adapterOutput.contract.test.js`.

The adapter's exclusive sample envelope includes each final measurement but does
not assert an activation duration. Raw source program types do not establish
adaptive delivery state. Frontend tests preserve these distinctions.
