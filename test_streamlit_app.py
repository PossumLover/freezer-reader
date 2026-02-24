import re
import pandas as pd
import pytest


def markdown_table_to_dataframe(table_lines):
    """Copy of function under test (avoids importing streamlit)."""
    rows = []
    for line in table_lines:
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        rows.append(cells)
    if len(rows) < 2:
        return None
    headers = rows[0]
    data_rows = [r for r in rows[1:] if not all(re.match(r'^[-:]+$', c) for c in r)]
    if not data_rows:
        return None
    seen = {}
    unique_headers = []
    for h in headers:
        if h in seen:
            seen[h] += 1
            unique_headers.append(f"{h}_{seen[h]}" if h else f"_{seen[h]}")
        else:
            seen[h] = 0
            unique_headers.append(h)
    num_cols = len(unique_headers)
    data_rows = [r[:num_cols] + [''] * (num_cols - len(r)) for r in data_rows]
    return pd.DataFrame(data_rows, columns=unique_headers)


def test_unique_columns():
    """Normal table with unique headers."""
    lines = [
        "| Name | Age | City |",
        "|------|-----|------|",
        "| Alice | 30 | NYC |",
    ]
    df = markdown_table_to_dataframe(lines)
    assert list(df.columns) == ["Name", "Age", "City"]
    assert df.shape == (1, 3)


def test_duplicate_columns():
    """Table with duplicate column names should get suffixes."""
    lines = [
        "| Name | Value | Name | Value |",
        "|------|-------|------|-------|",
        "| a    | 1     | b    | 2     |",
    ]
    df = markdown_table_to_dataframe(lines)
    assert list(df.columns) == ["Name", "Value", "Name_1", "Value_1"]
    assert df.shape == (1, 4)


def test_empty_column_names():
    """Table with empty column names (the exact error scenario)."""
    lines = [
        "|  | Date: |  |  |  | Species/Variety: |",
        "|--|-------|--|--|--|------------------|",
        "| x | 2024 | a | b | c | Rose |",
    ]
    df = markdown_table_to_dataframe(lines)
    # Empty strings should get deduplicated: '', '_1', '_2', '_3'
    assert df.columns.is_unique
    assert df.shape == (1, 6)


def test_mixed_duplicate_empty():
    """Table with both duplicate named and empty columns."""
    lines = [
        "| A |  | A |  |",
        "|---|--|---|--|",
        "| 1 | 2 | 3 | 4 |",
    ]
    df = markdown_table_to_dataframe(lines)
    assert df.columns.is_unique
    assert list(df.columns) == ["A", "", "A_1", "_1"]


def test_no_duplicates_unchanged():
    """Columns without duplicates should remain unchanged."""
    lines = [
        "| X | Y | Z |",
        "|---|---|---|",
        "| 1 | 2 | 3 |",
    ]
    df = markdown_table_to_dataframe(lines)
    assert list(df.columns) == ["X", "Y", "Z"]
