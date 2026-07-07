"""Shared helper for building small, disposable .xlsx fixtures in tests.

WHY THIS FILE EXISTS:
Import Engine tests must never depend on data/raw/*.xlsx — that file is
gitignored (it contains real people's data) and will not exist in a fresh
clone or in CI. This helper builds tiny, purpose-built workbooks in a temp
directory instead, so every test is fast, self-contained, and reproducible.
"""

from __future__ import annotations

from pathlib import Path
from typing import Mapping, Sequence

import openpyxl


def build_workbook(
    directory: Path,
    sheets: Mapping[str, Sequence[Sequence[object]]],
    filename: str = "fixture.xlsx",
) -> Path:
    """Write a small workbook with the given sheets and return its path.

    Args:
        directory: Where to write the file (typically pytest's tmp_path).
        sheets: Ordered mapping of sheet name -> rows, where each row is a
            sequence of cell values. The first row of each sheet is treated
            as its header row by convention (the Import Engine itself
            decides that, not this helper). Passing a Python `str` for a
            value keeps it stored as Excel text (preserving things like
            leading zeros); passing `int`/`float` stores it as an Excel
            number.
        filename: Name of the file to create inside `directory`.

    Returns:
        Path to the written workbook.
    """

    workbook = openpyxl.Workbook()
    workbook.remove(workbook.active)  # drop the default blank "Sheet"

    for sheet_name, rows in sheets.items():
        worksheet = workbook.create_sheet(title=sheet_name)
        for row in rows:
            worksheet.append(list(row))

    path = directory / filename
    workbook.save(path)
    return path
