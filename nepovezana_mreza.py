import os
import datetime
import arcpy
from common import Timer, ensure_gdb, resolve_layer

arcpy.env.overwriteOutput = True


def _selected_count(layer_name: str) -> int:
    """Fast-ish selected feature count for feature layers."""
    desc = arcpy.Describe(layer_name)
    fidset = getattr(desc, "FIDSet", "")
    if not fidset:
        return 0
    return len(fidset.split(";"))


def main(cfg: dict) -> dict:
    """
    Validator: nepovezana_mreza (disconnected network segments)

    Logic (same as your old working approach):
      1) Seed selection: pipes intersecting water sources
      2) Expand selection iteratively by touching/nearby pipes (BOUNDARY_TOUCHES + WITHIN_A_DISTANCE)
      3) SWITCH_SELECTION => disconnected pipes
      4) Ignore disconnected pipes where upotreba starts with "Ne"
      5) Export remaining errors into SCRATCH_GDB as feature class

    Config:
      cfg["NEPOVEZANA_MREZA"] = {
        "PIPES_FC": "...",
        "WATER_SOURCES_FC": "...",
        "SNAP_TOL": "0.1 Meters",
        "REPAIR_GEOMETRY": false
      }
    """
    t = Timer()
    validator = "nepovezana_mreza"
    conf = cfg["NEPOVEZANA_MREZA"]

    pipes_in = resolve_layer(cfg, conf["PIPES_FC"])
    sources_in = resolve_layer(cfg, conf["WATER_SOURCES_FC"])
    snap_tolerance = conf.get("SNAP_TOL", "0.1 Meters")

    ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    scratch_gdb = ensure_gdb(cfg.get("SCRATCH_GDB") or arcpy.env.scratchGDB, arcpy=arcpy)

    # Output FC in scratch.gdb
    out_err = os.path.join(scratch_gdb, f"{validator}_errors_{ts}")

    # --- scratch copy of pipes (avoid locks and allow repairs without touching source) ---
    pipes_fc = os.path.join(scratch_gdb, f"{validator}_pipes_{ts}")
    arcpy.management.CopyFeatures(pipes_in, pipes_fc)

    # Optional repair on scratch copy only
    if conf.get("REPAIR_GEOMETRY", False):
        arcpy.management.RepairGeometry(pipes_fc)

    # Create layers
    arcpy.management.MakeFeatureLayer(pipes_fc, "pipelines_layer")
    arcpy.management.MakeFeatureLayer(sources_in, "water_sources_layer")

    # Seed selection: pipes intersecting water sources
    arcpy.management.SelectLayerByAttribute("pipelines_layer", "CLEAR_SELECTION")
    arcpy.management.SelectLayerByLocation(
        "pipelines_layer",
        "INTERSECT",
        "water_sources_layer",
        selection_type="NEW_SELECTION"
    )

    seed_cnt = _selected_count("pipelines_layer")
    src_cnt = int(arcpy.management.GetCount("water_sources_layer")[0])

    # Guard: if seed is 0, SWITCH_SELECTION would select ALL pipes => wrong result
    if seed_cnt == 0:
        # cleanup
        for obj in ["pipelines_layer", "water_sources_layer", pipes_fc]:
            try:
                arcpy.management.Delete(obj)
            except Exception:
                pass

        try:
            arcpy.management.ClearWorkspaceCache()
        except Exception:
            pass

        return {
            "validator": validator,
            "status": "FAIL",
            "error_count": 1,
            "output_path": "",
            "inputs": f"pipes={pipes_in}; sources={sources_in}; tol={snap_tolerance}",
            "notes": f"Seed selection is 0 (sources={src_cnt}). WATER_SOURCES_FC does not intersect pipes.",
            "duration_s": t.seconds(),
        }

    # Expand selection until stable (same logic as old script)
    prev_count = -1
    while prev_count != _selected_count("pipelines_layer"):
        prev_count = _selected_count("pipelines_layer")
        arcpy.management.SelectLayerByLocation(
            "pipelines_layer",
            "BOUNDARY_TOUCHES",
            "pipelines_layer",
            selection_type="ADD_TO_SELECTION"
        )
        arcpy.management.SelectLayerByLocation(
            "pipelines_layer",
            "WITHIN_A_DISTANCE",
            "pipelines_layer",
            snap_tolerance,
            selection_type="ADD_TO_SELECTION"
        )

    # Switch to disconnected pipes (errors)
    arcpy.management.SelectLayerByAttribute("pipelines_layer", "SWITCH_SELECTION")

    # Ignore out-of-function pipes: upotreba starts with "Ne"
    up_field = None
    for ff in arcpy.ListFields(pipes_fc):
        if ff.name.lower() == "upotreba":
            up_field = ff.name
            break

    if up_field:
        f = arcpy.AddFieldDelimiters(pipes_fc, up_field)
        arcpy.management.SelectLayerByAttribute(
            "pipelines_layer",
            "SUBSET_SELECTION",
            f"({f} IS NULL) OR ({f} = '') OR ({f} NOT LIKE 'Ne%')"
        )

    cnt = _selected_count("pipelines_layer")
    if cnt > 0:
        arcpy.management.CopyFeatures("pipelines_layer", out_err)
    else:
        out_err = ""

    # cleanup
    for obj in ["pipelines_layer", "water_sources_layer", pipes_fc]:
        try:
            arcpy.management.Delete(obj)
        except Exception:
            pass

    try:
        arcpy.management.ClearWorkspaceCache()
    except Exception:
        pass

    return {
        "validator": validator,
        "status": "OK" if cnt == 0 else "ERROR",
        "error_count": cnt,
        "output_path": out_err,
        "inputs": f"pipes={pipes_in}; sources={sources_in}; tol={snap_tolerance}",
        "notes": f"sources={src_cnt}; seed={seed_cnt}",
        "duration_s": t.seconds(),
    }
