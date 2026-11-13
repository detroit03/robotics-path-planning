# Results — file guide

This directory contains **one completed Webots pilot run**, not a completed benchmark.

| Path | Content |
| --- | --- |
| `benchmark.json` | Actual A* / low density / slow obstacles / seed 7 measurement |
| `webots_results.png` | Overview of that measured pilot run |
| `analysis_pilot/report.md` | Pilot statistics, plots, trajectory and experiment coverage |
| `benchmark_logs/` | The nonempty controller output from the pilot run |
| `diagnostics/` | Failed simulator-start attempts; these contain no robot measurements |

The publishable copy of the pilot is [examples/pilot_run.json](../examples/pilot_run.json),
with its [analysis](../docs/analysis_pilot/report.md). Runtime output is Git-ignored.

The 81-run benchmark is **not completed**. Startup failures are documented under
`diagnostics/`; they must not be interpreted as measured algorithm failures.

Output rules:

- A CSV is generated only when it has data rows.
- `failures.csv` is absent when no measured simulation failed.
- Unmeasured metrics are omitted from summary CSV columns and listed in the report.
- A single observation has no sample standard deviation, so no empty standard-deviation column is emitted.
- New process logs always contain run metadata and an exit/timeout status, even if Webots prints nothing.
- Missing experiments cannot be recovered by filling cells with zero; they require new successful simulator runs.
