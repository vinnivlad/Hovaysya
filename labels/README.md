# Labels

Ground truth for the eval harness. See [../docs/labeling-schema.md](../docs/labeling-schema.md)
for the schema, level definitions, and scoring rules.

`moments.jsonl` — one label per line, in timestamp order.

**This directory is committed on purpose.** Everything under `data/` is
re-derivable by re-running the export; these labels are irreplaceable human
judgement. Do not move them into `data/`, and do not regenerate them.
