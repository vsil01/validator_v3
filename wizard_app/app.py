import json
import os
import tkinter as tk
from tkinter import filedialog, messagebox

CONFIG_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "config.json")
FIELDS = [
    ("Project name", "PROJECT"),
    ("Input GDB", "INPUT_GDB"),
    ("Scratch/Output GDB", "SCRATCH_GDB"),
    ("Results CSV", "RESULTS_CSV"),
]


def load_config(path):
    try:
        with open(path, "r", encoding="utf-8") as handle:
            return json.load(handle)
    except FileNotFoundError:
        return {}
    except json.JSONDecodeError as exc:
        messagebox.showerror("Invalid config.json", f"Could not parse config.json: {exc}")
        return {}


def save_config(path, data):
    try:
        with open(path, "w", encoding="utf-8") as handle:
            json.dump(data, handle, indent=2)
            handle.write("\n")
        messagebox.showinfo("Saved", f"Saved configuration to {path}")
    except OSError as exc:
        messagebox.showerror("Save failed", f"Could not write config.json: {exc}")


def browse_file(target_entry, filetypes):
    filename = filedialog.askopenfilename(filetypes=filetypes)
    if filename:
        target_entry.delete(0, tk.END)
        target_entry.insert(0, filename)


def build_app(root):
    root.title("Validator Config Wizard (Test)")
    root.resizable(False, False)

    config = load_config(CONFIG_PATH)

    frame = tk.Frame(root, padx=16, pady=16)
    frame.grid(row=0, column=0, sticky="nsew")

    entries = {}
    for row, (label, key) in enumerate(FIELDS):
        tk.Label(frame, text=label).grid(row=row, column=0, sticky="w", pady=4)
        entry = tk.Entry(frame, width=60)
        entry.grid(row=row, column=1, padx=(8, 0), pady=4)
        entry.insert(0, config.get(key, ""))
        entries[key] = entry

        if key != "PROJECT":
            filetypes = [
                ("Geodatabase", "*.gdb"),
                ("CSV", "*.csv"),
                ("All files", "*.*"),
            ]
            button = tk.Button(
                frame,
                text="Browse",
                command=lambda e=entry, f=filetypes: browse_file(e, f),
            )
            button.grid(row=row, column=2, padx=(8, 0), pady=4)

    def on_save():
        updated = config.copy()
        for _, key in FIELDS:
            updated[key] = entries[key].get().strip()
        save_config(CONFIG_PATH, updated)

    actions = tk.Frame(frame)
    actions.grid(row=len(FIELDS), column=0, columnspan=3, pady=(12, 0), sticky="e")

    tk.Button(actions, text="Save", command=on_save).grid(row=0, column=0, padx=4)
    tk.Button(actions, text="Close", command=root.destroy).grid(row=0, column=1, padx=4)


if __name__ == "__main__":
    app = tk.Tk()
    build_app(app)
    app.mainloop()
