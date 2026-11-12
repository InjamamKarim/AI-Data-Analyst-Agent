import io

import pandas as pd

from backend.security.csv_sanitize import sanitize_cell, sanitize_dataframe


def test_formula_cells_are_neutralized_and_numbers_stay_numbers():
    assert sanitize_cell("=cmd|'/c calc'!A0").startswith("'")
    assert sanitize_cell("+1+1").startswith("'")
    assert sanitize_cell("@SUM(A1)").startswith("'")
    assert sanitize_cell("-delete all").startswith("'")
    assert sanitize_cell("-12.5") == "-12.5"
    assert sanitize_cell(3) == 3


def test_hostile_column_names_become_identifiers():
    frame = pd.read_csv(io.StringIO("=evil,qty\n=1+1,-3\n"))
    cleaned = sanitize_dataframe(frame)
    assert list(cleaned.columns) == ["evil", "qty"]
    assert str(cleaned.iloc[0]["evil"]).startswith("'")
    assert cleaned.iloc[0]["qty"] == -3
