#!/usr/bin/env python
"""Regenerate docs/self_test_clusters.xlsx from docs/self_test_clusters.csv.

Run after editing the CSV by hand or after a fresh `scripts/self_test.py`
sweep changes the status of any case. Produces a formatted workbook with
color-coded PASS/FAIL/NOT_TESTED, cluster highlights, wrapped cells and a
frozen header row.

Usage:
    .venv/bin/python scripts/gen_test_xlsx.py
"""
from __future__ import annotations

import csv
import sys
from pathlib import Path

from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side


SRC = Path("docs/self_test_clusters.csv")
DST = Path("docs/self_test_clusters.xlsx")

STATUS_FILL = {
    "PASS": PatternFill("solid", fgColor="C6EFCE"),
    "FAIL": PatternFill("solid", fgColor="FFC7CE"),
    "NOT_TESTED": PatternFill("solid", fgColor="FFEB9C"),
}
STATUS_FONT = {
    "PASS": Font(color="006100", bold=True),
    "FAIL": Font(color="9C0006", bold=True),
    "NOT_TESTED": Font(color="9C6500", bold=True),
}
CLUSTER_FILL = PatternFill("solid", fgColor="D9E1F2")
HEADER_FILL = PatternFill("solid", fgColor="4472C4")
HEADER_FONT = Font(color="FFFFFF", bold=True, size=11)
THIN = Side(style="thin", color="B4B4B4")
BORDER = Border(left=THIN, right=THIN, top=THIN, bottom=THIN)

COLUMN_WIDTHS = {
    "A": 13,   # cluster
    "B": 36,   # cluster_purpose
    "C": 7,    # case_id
    "D": 42,   # case_name
    "E": 64,   # case_intent
    "F": 12,   # status
    "G": 36,   # evidence
    "H": 56,   # notes
}


def main() -> int:
    if not SRC.exists():
        print(f"error: {SRC} not found", file=sys.stderr)
        return 1

    with SRC.open(newline="", encoding="utf-8") as f:
        rows = list(csv.reader(f))
    if not rows:
        print(f"error: {SRC} is empty", file=sys.stderr)
        return 1

    headers, data = rows[0], rows[1:]

    wb = Workbook()
    ws = wb.active
    ws.title = "Self-test scenarios"

    ws.append(headers)
    for cell in ws[1]:
        cell.fill = HEADER_FILL
        cell.font = HEADER_FONT
        cell.alignment = Alignment(horizontal="center", vertical="center")
        cell.border = BORDER

    prev_cluster = None
    for r in data:
        cluster = r[0]
        if cluster != prev_cluster and prev_cluster is not None:
            ws.append([""] * len(headers))
        prev_cluster = cluster

        ws.append(r)
        row_idx = ws.max_row
        for col_idx in range(1, len(headers) + 1):
            c = ws.cell(row=row_idx, column=col_idx)
            c.alignment = Alignment(wrap_text=True, vertical="top")
            c.border = BORDER

        ws.cell(row=row_idx, column=1).fill = CLUSTER_FILL
        ws.cell(row=row_idx, column=1).font = Font(bold=True)
        ws.cell(row=row_idx, column=2).fill = CLUSTER_FILL

        status = r[5]
        if status in STATUS_FILL:
            sc = ws.cell(row=row_idx, column=6)
            sc.fill = STATUS_FILL[status]
            sc.font = STATUS_FONT[status]
            sc.alignment = Alignment(horizontal="center", vertical="center")

    for col, w in COLUMN_WIDTHS.items():
        ws.column_dimensions[col].width = w
    ws.freeze_panes = "A2"
    ws.row_dimensions[1].height = 24

    wb.save(DST)
    print(f"Wrote {DST}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
