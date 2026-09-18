from __future__ import annotations

import tkinter as tk

import pytest

from retailmetrics_s3.gui.app import RetailMetricsSession3GUI


@pytest.mark.gui
def test_gui_constructs_all_eight_tabs_without_database_access():
    try:
        app = RetailMetricsSession3GUI()
    except tk.TclError as exc:
        pytest.skip(f"Graphical session unavailable: {exc}")
    app.withdraw(); app.update_idletasks()
    assert app.notebook.tabs()
    assert [app.notebook.tab(tab, "text") for tab in app.notebook.tabs()] == list(app.TAB_NAMES)
    assert all(row["status"] == "Not run" for row in app.stage_rows.values())
    app.destroy()

