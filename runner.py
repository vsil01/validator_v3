import arcpy
import json
import os
import importlib
from common import ensure_dir, append_result_row, make_run_id, now_iso

VALIDATORS = [
    "validators.secjenje_cevi",
    "validators.secjenje_tacaka",
    "validators.promena_materijala_precnika",
    "validators.atribute_cevi",
    "validators.duplicate_ids",
    "validators.nepovezana_mreza",
    "validators.nizvodno",
]

def import_validator(modname: str):
    """Import validator module.

    Supports both:
      - 'validators.secjenje_cevi' (package layout)
      - 'secjenje_cevi' (flat layout)
    """
    try:
        return importlib.import_module(modname)
    except ModuleNotFoundError:
        if modname.startswith("validators."):
            return importlib.import_module(modname.split("validators.",1)[1])
        raise


def load_cfg(path: str) -> dict:
    with open(path, "r", encoding="utf-8") as f:
        if path.lower().endswith(".json"):
            return json.load(f)
        raise ValueError("Only JSON config is supported in this template. (Easy to add YAML if you want.)")
        
def main(cfg_path: str):
    cfg = load_cfg(cfg_path)
      # ---- ArcPy environment from config ----
    # ---- ArcPy environment from config ----
    workspace = cfg.get("INPUT_GDB") or cfg.get("INPUT_DIR")  # GDB preferred, fallback to SHP folder
    scratch_gdb = cfg.get("SCRATCH_GDB")

    if workspace:
        arcpy.env.workspace = workspace

    if scratch_gdb:
        arcpy.env.scratchWorkspace = scratch_gdb

    arcpy.env.overwriteOutput = True

    run_id = cfg.get("RUN_ID") or make_run_id("validator")
    project = cfg.get("PROJECT", "")

    csv_path = cfg.get("RESULTS_CSV")

    for modname in VALIDATORS:
        mod = import_validator(modname)
        res = mod.main(cfg)  # must return dict
        # Normalize + append to csv
        row = {
            "run_id": run_id,
            "timestamp": now_iso(),
            "project": project,
            "validator": res.get("validator", modname),
            "status": res.get("status", "OK"),
            "error_count": res.get("error_count", 0),
            "output_path": res.get("output_path", ""),
            "inputs": res.get("inputs", ""),
            "notes": res.get("notes", ""),
            "duration_min": round(res.get("duration_s", "") / 60.0, 2),
        }
        append_result_row(csv_path, row)

    print(f"Done. Results CSV: {csv_path}")

if __name__ == "__main__":
    import sys
    if len(sys.argv) < 2:
        raise SystemExit("Usage: python runner.py path/to/config.json")
    main(sys.argv[1])