import csv
import os
import re
import time
from datetime import datetime

CSV_SCHEMA = [
    "run_id",
    "timestamp",
    "project",
    "validator",
    "status",
    "error_count",
    "output_path",
    "inputs",
    "notes",
    "duration_min",
]


def resolve_layer(cfg: dict, value: str) -> str:
    """
    Resolves:
      - absolute paths -> unchanged
      - layer/FC names ->
          * if INPUT_GDB is set: INPUT_GDB/<name>
          * else if INPUT_DIR is set: INPUT_DIR/<name>.shp
    """
    if not value:
        return value

    # absolute path (C:\ or \\server\share)
    if os.path.isabs(value) or value.startswith("\\\\") or (len(value) > 2 and value[1] == ":"):
        return value

    input_gdb = cfg.get("INPUT_GDB")
    if input_gdb:
        # in file geodatabase, feature class is referenced without extension
        return os.path.join(input_gdb, value)

    input_dir = cfg.get("INPUT_DIR")
    if input_dir:
        fname = value if value.lower().endswith(".shp") else f"{value}.shp"
        return os.path.join(input_dir, fname)

    return value  # fallback (ArcPy will likely fail)

def now_iso() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")

def ensure_dir(path: str) -> str:
    os.makedirs(path, exist_ok=True)
    return path

def make_run_id(prefix: str = "run") -> str:
    return f"{prefix}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"

def append_result_row(csv_path: str, row: dict) -> None:
    ensure_dir(os.path.dirname(csv_path))
    file_exists = os.path.exists(csv_path)
    with open(csv_path, "a", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=CSV_SCHEMA)
        if not file_exists:
            w.writeheader()
        out = {k: row.get(k, "") for k in CSV_SCHEMA}
        w.writerow(out)

class Timer:
    def __init__(self):
        self.t0 = time.time()
    def seconds(self) -> float:
        return round(time.time() - self.t0, 3)
    def elapsed(self) -> float:
        return self.seconds()

def safe_fc_name(name: str, maxlen: int = 60) -> str:
    # file geodatabase name rules are lenient but keep it short and safe
    repl = (
        name.replace(" ", "_")
            .replace("-", "_")
            .replace("/", "_")
            .replace("\\", "_")
    )
    # remove non-ascii-ish chars that can cause trouble
    repl = "".join(ch if (ch.isalnum() or ch == "_") else "_" for ch in repl)
    repl = re.sub(r"_+", "_", repl).strip("_")
    if len(repl) > maxlen:
        repl = repl[:maxlen]
    if not repl:
        repl = "fc"
    return repl

def ensure_gdb(gdb_path: str, arcpy=None) -> str:
    # Create a file gdb if missing. If arcpy isn't available, just return path.
    if not gdb_path.lower().endswith(".gdb"):
        raise ValueError(f"SCRATCH_GDB must end with .gdb: {gdb_path}")
    if os.path.exists(gdb_path):
        return gdb_path
    ensure_dir(os.path.dirname(gdb_path))
    if arcpy is None:
        return gdb_path
    arcpy.management.CreateFileGDB(os.path.dirname(gdb_path), os.path.basename(gdb_path))
    return gdb_path
