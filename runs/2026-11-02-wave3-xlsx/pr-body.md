fix(xlsx): preserve error cell values instead of silent NaN

Fixes #2728

## Summary

- XLSX cells carrying error values (data type `"e"`: `#DIV/0!`, `#REF!`, `#NAME?`, `#VALUE!`) are collapsed to `NaN` by `pd.read_excel`, so the converted Markdown silently shows `NaN` and the cell value is gone.
- After parsing, walk the same workbook with openpyxl again and restore every error cell whose position in the parsed DataFrame still holds `NaN`, casting the column to `object` when its dtype cannot hold strings.

## Changes

- `packages/markitdown/src/markitdown/converters/_xlsx_converter.py`: second openpyxl pass restoring error-cell values; formulas without cached results are out of scope and stay untouched; the showZeroes repair path keeps working.
- `packages/markitdown/tests/test_xlsx.py`: 5 regression tests — one per error code plus a mixed table; workbooks are generated with openpyxl in-test.

## Testing

- The new tests fail against the unpatched converter (silent `NaN`) and pass with the fix.
- Full suite: 1168 passed, 12 skipped, 0 failed.
