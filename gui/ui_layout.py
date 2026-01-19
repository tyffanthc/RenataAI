from __future__ import annotations

import tkinter as tk
from tkinter import ttk
from typing import Tuple


LABEL_W = 16
ENTRY_W = 9
ENTRY_W_LONG = 25
ROW_PADY = 4
COL_GAP = 12


def configure_form_grid(frame: ttk.Frame) -> None:
    for col in range(5):
        frame.grid_columnconfigure(col, weight=0)
    frame.grid_columnconfigure(2, minsize=COL_GAP)


def add_labeled_entry(
    frame: ttk.Frame,
    row: int,
    label: str,
    variable: tk.Variable,
    *,
    label_width: int = LABEL_W,
    entry_width: int = ENTRY_W,
    column: int = 0,
    pady: int = ROW_PADY,
) -> ttk.Entry:
    ttk.Label(frame, text=f"{label}:", width=label_width).grid(
        row=row, column=column, sticky="w", pady=pady
    )
    entry = ttk.Entry(frame, textvariable=variable, width=entry_width)
    entry.grid(row=row, column=column + 1, sticky="w", pady=pady)
    return entry


def add_labeled_pair(
    frame: ttk.Frame,
    row: int,
    left_label: str,
    left_var: tk.Variable,
    right_label: str,
    right_var: tk.Variable,
    *,
    label_width: int = LABEL_W,
    entry_width: int = ENTRY_W,
    left_entry_width: int | None = None,
    right_entry_width: int | None = None,
    pady: int = ROW_PADY,
) -> Tuple[ttk.Entry, ttk.Entry]:
    left_entry = add_labeled_entry(
        frame,
        row,
        left_label,
        left_var,
        label_width=label_width,
        entry_width=left_entry_width or entry_width,
        column=0,
        pady=pady,
    )
    right_entry = add_labeled_entry(
        frame,
        row,
        right_label,
        right_var,
        label_width=label_width,
        entry_width=right_entry_width or entry_width,
        column=3,
        pady=pady,
    )
    return left_entry, right_entry
