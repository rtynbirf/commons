Fixes #2804

## Summary

`IpynbConverter.accepts()` sniffed for the `nbformat` and `nbformat_minor` substrings anywhere in the decoded text. Ordinary JSON that merely mentions the marker names — in a string value, or as numeric fields without a `cells` array — was routed into the notebook converter, whose empty `cells` iteration returned a successful empty conversion: the document was silently discarded instead of falling through to the plain-text converter.

The converter now recognizes a notebook structurally: a JSON object (UTF-8 BOM tolerated) whose top level carries numeric `nbformat` and `nbformat_minor` versions and a `cells` list. Malformed or excessively nested JSON is declined rather than crashing detection with `RecursionError`; decode errors keep declining the candidate as before. Extension routing for `.ipynb` and genuine MIME-detected notebooks, including BOM-prefixed ones, are unchanged.

## Changes

- `packages/markitdown/src/markitdown/converters/_ipynb_converter.py`: new `_is_notebook_json()` helper; `accepts()` now parses the candidate and checks the structure instead of substring sniffing.
- `packages/markitdown/tests/test_module_misc.py`: 7 new regression cases (the issue's two repro shapes, a nested notebook-shaped object, deeply nested JSON, and controls for BOM-routed and extension-routed notebooks).

## Testing

- [x] Red/green: the 4 new regression tests fail on the untouched implementation and pass with the fix
- [x] The repro from #2804 now returns the JSON text instead of `''`
- [x] Local suite: 1169 passed, 12 skipped, 0 failed
