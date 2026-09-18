from __future__ import annotations

import tkinter as tk
from tkinter import ttk


class ScrollPage(tk.Frame):
    def __init__(self, parent, background: str):
        super().__init__(parent, bg=background)
        canvas = tk.Canvas(self, bg=background, highlightthickness=0)
        scrollbar = ttk.Scrollbar(self, orient="vertical", command=canvas.yview)
        self.content = tk.Frame(canvas, bg=background)
        window = canvas.create_window((0, 0), window=self.content, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)
        canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")
        self.content.bind("<Configure>", lambda _e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.bind("<Configure>", lambda e: canvas.itemconfigure(window, width=e.width))


def replace_tree(tree: ttk.Treeview, rows: list[dict], columns: tuple[str, ...]) -> None:
    tree.delete(*tree.get_children())
    for row in rows:
        tree.insert("", "end", values=[row.get(column, "") for column in columns])


def draw_bars(canvas: tk.Canvas, labels: list[str], series: list[tuple[str, str, list[float]]]) -> None:
    canvas.delete("all")
    canvas.update_idletasks()
    width = max(canvas.winfo_width(), 700); height = max(canvas.winfo_height(), 220)
    left, right, top, bottom = 55, 25, 30, 48
    values = [v for _, _, data in series for v in data]
    maximum = max(values, default=0)
    if not labels or maximum <= 0:
        canvas.create_text(width / 2, height / 2, text="Not run", fill="#64748b", font=("Segoe UI", 11))
        return
    usable = width - left - right; group = usable / len(labels); bar_width = min(42, group / (len(series) + 1))
    canvas.create_line(left, height - bottom, width - right, height - bottom, fill="#cbd5e1")
    for index, label in enumerate(labels):
        center = left + group * (index + .5)
        for series_index, (_, color, data) in enumerate(series):
            value = data[index]
            x0 = center + (series_index - (len(series) - 1) / 2) * bar_width - bar_width * .38
            x1 = x0 + bar_width * .76
            bar_height = (height - top - bottom) * value / maximum
            y0 = height - bottom - bar_height
            canvas.create_rectangle(x0, y0, x1, height - bottom, fill=color, outline="")
            canvas.create_text((x0 + x1) / 2, y0 - 9, text=f"{value:,.2f}", fill="#334155", font=("Segoe UI", 8))
        canvas.create_text(center, height - bottom + 17, text=label, fill="#475569", font=("Segoe UI", 8))
    x = left
    for name, color, _ in series:
        canvas.create_rectangle(x, 7, x + 11, 18, fill=color, outline="")
        canvas.create_text(x + 16, 12, text=name, anchor="w", fill="#475569", font=("Segoe UI", 8))
        x += 120

