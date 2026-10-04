# NeuraSWE controlled evaluation

The runner records outcomes from controlled fixture repositories without claiming an
external benchmark score. Copy `cases.example.json` to `cases.json`, point each case
at a local repository and run `python benchmarks/runner.py --cases benchmarks/cases.json
--output benchmark-results.json`. The runner never publishes pull requests.

Each case supplies a setup command, validation command and expected changed paths.
Results include elapsed time, validation outcome, changed paths, and optional tool,
token, model-request, cost and PR-publication data exported by a NeuraSWE run. Point
`run_metrics_file` at a JSON export containing `tool_counts`, `model_requests`,
`total_tokens`, `estimated_cost`, and `pr_status`. `allowed_paths` makes unexpected
file changes count as an incorrect patch.
