import json
import os
import subprocess
import sys
import threading
import tkinter as tk
from tkinter import filedialog, messagebox

REPO_ROOT = os.path.dirname(os.path.dirname(__file__))
CONFIG_PATH = os.path.join(REPO_ROOT, "config.json")
RUNNER_PATH = os.path.join(REPO_ROOT, "runner.py")
FIELDS = [
    ("Project name", "PROJECT", "text"),
    ("Input GDB", "INPUT_GDB", "gdb"),
    ("Scratch/Output GDB", "SCRATCH_GDB", "gdb"),
    ("Results CSV", "RESULTS_CSV", "csv"),
]


class ValidatorWizard(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Validator Wizard (Windows)")
        self.resizable(False, False)
        self.entries = {}
        self.is_running = False
        self._build_ui()
        self._load_into_form()

    def _build_ui(self):
        frame = tk.Frame(self, padx=16, pady=16)
        frame.grid(row=0, column=0, sticky="nsew")

        for row, (label, key, field_type) in enumerate(FIELDS):
            tk.Label(frame, text=label).grid(row=row, column=0, sticky="w", pady=4)

            entry = tk.Entry(frame, width=70)
            entry.grid(row=row, column=1, padx=(8, 0), pady=4)
            self.entries[key] = entry

            if field_type != "text":
                tk.Button(
                    frame,
                    text="Browse",
                    command=lambda e=entry, t=field_type: self._browse(e, t),
                ).grid(row=row, column=2, padx=(8, 0), pady=4)

        self.status_var = tk.StringVar(value="Ready")
        tk.Label(frame, textvariable=self.status_var, fg="#1f2937").grid(
            row=len(FIELDS), column=0, columnspan=3, sticky="w", pady=(10, 4)
        )

        buttons = tk.Frame(frame)
        buttons.grid(row=len(FIELDS) + 1, column=0, columnspan=3, sticky="e", pady=(8, 0))

        self.save_button = tk.Button(buttons, text="Save config", command=self.save_only)
        self.save_button.grid(row=0, column=0, padx=4)

        self.run_button = tk.Button(buttons, text="Save + Run validator", command=self.save_and_run)
        self.run_button.grid(row=0, column=1, padx=4)

        tk.Button(buttons, text="Close", command=self.destroy).grid(row=0, column=2, padx=4)

    def _browse(self, target_entry, field_type):
        if field_type == "gdb":
            chosen = filedialog.askdirectory(title="Select .gdb folder")
        elif field_type == "csv":
            chosen = filedialog.asksaveasfilename(
                title="Select or create results CSV",
                defaultextension=".csv",
                filetypes=[("CSV", "*.csv"), ("All files", "*.*")],
            )
        else:
            chosen = filedialog.askopenfilename(title="Select file")

        if chosen:
            target_entry.delete(0, tk.END)
            target_entry.insert(0, chosen)

    def _load_cfg(self):
        try:
            with open(CONFIG_PATH, "r", encoding="utf-8") as handle:
                return json.load(handle)
        except FileNotFoundError:
            return {}
        except json.JSONDecodeError as exc:
            messagebox.showerror("Invalid config.json", f"Could not parse config.json: {exc}")
            return {}

    def _load_into_form(self):
        config = self._load_cfg()
        for _, key, _ in FIELDS:
            self.entries[key].delete(0, tk.END)
            self.entries[key].insert(0, config.get(key, ""))

    def _gather_form(self):
        data = self._load_cfg()
        for _, key, _ in FIELDS:
            data[key] = self.entries[key].get().strip()
        return data

    def _validate(self, data):
        missing = [label for label, key, _ in FIELDS if not data.get(key)]
        if missing:
            messagebox.showwarning("Missing values", "Please fill all fields:\n- " + "\n- ".join(missing))
            return False
        return True

    def _write_cfg(self, data):
        with open(CONFIG_PATH, "w", encoding="utf-8") as handle:
            json.dump(data, handle, indent=2)
            handle.write("\n")

    def save_only(self):
        try:
            data = self._gather_form()
            if not self._validate(data):
                return
            self._write_cfg(data)
            self.status_var.set(f"Saved: {CONFIG_PATH}")
            messagebox.showinfo("Saved", "Configuration saved successfully.")
        except OSError as exc:
            messagebox.showerror("Save failed", f"Could not write config.json: {exc}")

    def save_and_run(self):
        if self.is_running:
            return

        try:
            data = self._gather_form()
            if not self._validate(data):
                return
            self._write_cfg(data)
        except OSError as exc:
            messagebox.showerror("Save failed", f"Could not write config.json: {exc}")
            return

        self.is_running = True
        self.run_button.configure(state="disabled")
        self.save_button.configure(state="disabled")
        self.status_var.set("Running validator...")

        def worker():
            cmd = [sys.executable, RUNNER_PATH, CONFIG_PATH]
            result = subprocess.run(cmd, cwd=REPO_ROOT, capture_output=True, text=True)
            self.after(0, lambda: self._on_run_finished(result))

        threading.Thread(target=worker, daemon=True).start()

    def _on_run_finished(self, result):
        self.is_running = False
        self.run_button.configure(state="normal")
        self.save_button.configure(state="normal")

        if result.returncode == 0:
            self.status_var.set("Validator finished successfully.")
            messagebox.showinfo("Done", "Validator finished successfully.")
        else:
            self.status_var.set("Validator failed. Check error details.")
            stderr = (result.stderr or "").strip()
            stdout = (result.stdout or "").strip()
            details = stderr if stderr else stdout
            if not details:
                details = f"Process exited with code {result.returncode}"
            messagebox.showerror("Validator failed", details)


if __name__ == "__main__":
    app = ValidatorWizard()
    app.mainloop()
