"""Rebuild XY sweep grids from saved cells.

New images carry `sweep_id`, axis labels and a row-major `sweep_index` in Bubba metadata (-1 = the labelled
sheet). Older images only have notes like `XY sweep cfg=4, cfg=6 | steps=15, steps=20`; those are grouped by
identical notes in the same folder, saved close together, and laid out in save order.
"""

from __future__ import annotations

import os
import re
from typing import Any, Callable

LEGACY_NOTES_PREFIX = "XY sweep "
LEGACY_GAP_SECONDS = 300.0  # a pause longer than this starts a new run with the same notes


def _bubba(metadata_summary: dict[str, Any]) -> dict[str, Any]:
    embedded = (metadata_summary or {}).get("metadata")
    bubba = embedded.get("bubba_metadata") if isinstance(embedded, dict) else None
    return bubba if isinstance(bubba, dict) else {}


def _split_axis(part: str) -> list[str]:
    """Split one axis of legacy notes. Labels look like `axis=value`; values may contain ", "."""
    part = part.strip()
    match = re.match(r"([A-Za-z_]+)=", part)
    if not match:
        return [item.strip() for item in part.split(",") if item.strip()]
    return [item.strip() for item in re.split(rf",\s*(?={re.escape(match.group(1))}=)", part) if item.strip()]


def parse_legacy_notes(notes: str) -> tuple[list[str], list[str]] | None:
    text = str(notes or "").strip()
    if not text.startswith(LEGACY_NOTES_PREFIX):
        return None
    parts = text[len(LEGACY_NOTES_PREFIX) :].split(" | ")
    x_labels = _split_axis(parts[0])
    y_labels = _split_axis(parts[1]) if len(parts) > 1 else []
    return (x_labels, y_labels) if x_labels else None


def sweep_key(metadata_summary: dict[str, Any]) -> str:
    """Grouping key for an indexed row: `id:<sweep_id>`, `notes:<notes>` or '' when not part of a sweep."""
    bubba = _bubba(metadata_summary)
    if bubba.get("sweep_id"):
        return f"id:{bubba['sweep_id']}"
    if parse_legacy_notes(bubba.get("notes", "")):
        return f"notes:{bubba['notes'].strip()}"
    return ""


def _cell(row: dict[str, Any], index: int, columns: int, x_labels: list[str], y_labels: list[str]) -> dict[str, Any]:
    row_index, column = divmod(index, columns)
    return {
        "path": row["path"],
        "name": row["name"],
        "index": index,
        "column": column,
        "row": row_index,
        "x": x_labels[column] if column < len(x_labels) else "",
        "y": y_labels[row_index] if row_index < len(y_labels) else "",
    }


def build_sweep_group(
    target_path: str,
    rows: list[dict[str, Any]],
    image_size: Callable[[str], tuple[int, int] | None],
) -> dict[str, Any] | None:
    """The labelled grid for the sweep containing `target_path`.

    `rows` need path, name, relative_path, modified_ts and a parsed `metadata` summary.
    `image_size(path)` returns pixel size; only legacy groups use it, to tell the sheet from the cells.
    """
    target_abs = os.path.abspath(target_path)
    target = next((row for row in rows if os.path.abspath(row["path"]) == target_abs), None)
    if target is None:
        return None
    key = sweep_key(target["metadata"])
    if not key:
        return None
    bubba = _bubba(target["metadata"])

    if key.startswith("id:"):
        members = [row for row in rows if sweep_key(row["metadata"]) == key]
        x_labels = list(bubba.get("sweep_x_labels") or [])
        y_labels = list(bubba.get("sweep_y_labels") or [])
        columns = max(1, len(x_labels))
        cells, sheets = [], []
        for row in members:
            index = _bubba(row["metadata"]).get("sweep_index", -1)
            (sheets if index is None or int(index) < 0 else cells).append((int(index or 0), row))
        cells.sort(key=lambda item: (item[0], item[1]["modified_ts"]))
        cell_list = [_cell(row, index, columns, x_labels, y_labels) for index, row in cells]
        sheet = max((row for _, row in sheets), key=lambda row: row["modified_ts"], default=None)
        source = "sweep_id"
    else:
        x_labels, y_labels = parse_legacy_notes(bubba.get("notes", ""))
        columns = max(1, len(x_labels))
        expected = columns * max(1, len(y_labels))
        folder = os.path.dirname(target["relative_path"])
        candidates = sorted(
            (row for row in rows if sweep_key(row["metadata"]) == key and os.path.dirname(row["relative_path"]) == folder),
            key=lambda row: (row["modified_ts"], row["name"].lower()),
        )
        # Split into runs saved close together, then keep the run holding the target.
        runs: list[list[dict[str, Any]]] = []
        for row in candidates:
            if runs and row["modified_ts"] - runs[-1][-1]["modified_ts"] <= LEGACY_GAP_SECONDS:
                runs[-1].append(row)
            else:
                runs.append([row])
        run = next(run for run in runs if target in run)
        sizes = {row["path"]: image_size(row["path"]) for row in run}
        known = [size for size in sizes.values() if size]
        cell_size = max(set(known), key=known.count) if known else None
        sheets = [row for row in run if cell_size and sizes[row["path"]] and sizes[row["path"]] != cell_size]
        cell_rows = [row for row in run if row not in sheets]
        # A re-run with identical notes inside the gap: chunk by the expected cell count.
        if len(cell_rows) > expected:
            position = cell_rows.index(target) if target in cell_rows else 0
            start = (position // expected) * expected
            cell_rows = cell_rows[start : start + expected]
        cell_list = [_cell(row, index, columns, x_labels, y_labels) for index, row in enumerate(cell_rows)]
        sheet = sheets[-1] if sheets else None
        source = "notes"

    return {
        "sweep_id": bubba.get("sweep_id", ""),
        "source": source,
        "x_axis": x_labels[0].split("=", 1)[0] if x_labels and "=" in x_labels[0] else "",
        "y_axis": y_labels[0].split("=", 1)[0] if y_labels and "=" in y_labels[0] else "",
        "x_labels": x_labels,
        "y_labels": y_labels,
        "columns": columns,
        "rows": max(1, len(y_labels)),
        "cells": cell_list,
        "sheet": {"path": sheet["path"], "name": sheet["name"]} if sheet else None,
    }
