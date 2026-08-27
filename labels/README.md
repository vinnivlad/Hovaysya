# Labels

Ground truth for the eval harness. See [../docs/labeling-schema.md](../docs/labeling-schema.md)
for the schema, level definitions, and scoring rules.

`moments.jsonl` — one label per line, in timestamp order.

**This directory is committed on purpose.** Everything under `data/` is
re-derivable by re-running the export; these labels are irreplaceable human
judgement. Do not move them into `data/`, and do not regenerate them.

## More than one file

Every file here is a **complete snapshot**: the page exports all labels for all
nights at once, not a delta. So the merge rule is per night — **the newest file
that mentions a night defines the whole set for that night** — and it lives in
`tools/labeler/load.py`.

Dropping a fresh export into this directory is all that is needed for it to
count. Nothing has to be moved or deleted, and a label removed in the page stays
removed, which a plain union by id would silently undo.
