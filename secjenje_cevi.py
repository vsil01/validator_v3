import os
import datetime
import arcpy
from common import ensure_dir, Timer, ensure_gdb, resolve_layer

arcpy.env.overwriteOutput = True


def main(cfg: dict) -> dict:
    """
    Check: each pipe/line must have exactly N intersections with merged point layers.
    Exports error lines to a SHAPEFILE inside results folder.
    """
    t = Timer()
    validator = "secenje_cevi"

    # --- resolve inputs (supports absolute paths OR layer names) ---
    lines_fc_raw = cfg["SECENJE_CEVI"]["LINES_FC"]          # e.g. "Merge" or full path
    point_fcs_raw = cfg["SECENJE_CEVI"]["POINT_FCS"]        # e.g. ["Fitinzi", ...] or full paths

    lines_fc = resolve_layer(cfg, lines_fc_raw)
    point_fcs = [resolve_layer(cfg, p) for p in point_fcs_raw]

    expected = int(cfg["SECENJE_CEVI"].get("EXPECTED_JOIN_COUNT", 2))

    # --- fail early with a useful message if any input is missing ---
    missing = [p for p in [lines_fc, *point_fcs] if not arcpy.Exists(p)]
    if missing:
        raise FileNotFoundError(
            "SECENJE_CEVI: Some input datasets do not exist (or are not supported by ArcGIS):\n"
            + "\n".join(missing)
            + f"\n\nINPUT_DIR={cfg.get('INPUT_DIR')}"
            + f"\nLINES_FC(raw)={lines_fc_raw}"
            + f"\nPOINT_FCS(raw_count)={len(point_fcs_raw)}"
        )

    ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")

    # Use scratchGDB for temp
    scratch_gdb = ensure_gdb(cfg.get("SCRATCH_GDB") or arcpy.env.scratchGDB, arcpy=arcpy)
    merged_pts = os.path.join(scratch_gdb, f"_tmp_all_points_{ts}")
    sj_out = os.path.join(scratch_gdb, f"_tmp_lines_sj_{ts}")

    out_selected = os.path.join(scratch_gdb, f"{validator}_errors_{ts}")

    error_count = 0
    status = "OK"
    notes = ""

    try:
        arcpy.management.Merge(point_fcs, merged_pts)

        arcpy.analysis.SpatialJoin(
            target_features=lines_fc,
            join_features=merged_pts,
            out_feature_class=sj_out,
            join_operation="JOIN_ONE_TO_ONE",
            join_type="KEEP_ALL",
            match_option="INTERSECT",
        )

        lyr = "lines_sj_lyr"
        arcpy.management.MakeFeatureLayer(sj_out, lyr)
        arcpy.management.SelectLayerByAttribute(lyr, "NEW_SELECTION", f"Join_Count <> {expected}")
        outputs = []
        error_count = 0

        jc = arcpy.AddFieldDelimiters(sj_out, "Join_Count")

        # --- Over-connected pipes (too many intersections) ---
        arcpy.management.SelectLayerByAttribute(
            lyr, "NEW_SELECTION", f"{jc} > {expected}"
        )
        cnt_over = int(arcpy.management.GetCount(lyr)[0])
        if cnt_over > 0:
            out_over = os.path.join(scratch_gdb, f"secenje_cevi_errors_{ts}")
            arcpy.management.CopyFeatures(lyr, out_over)
            outputs.append(out_over)

# --- Under-connected pipes (not enough intersections) ---
        arcpy.management.SelectLayerByAttribute(
            lyr, "NEW_SELECTION", f"{jc} < {expected}"
        )
        cnt_under = int(arcpy.management.GetCount(lyr)[0])
        if cnt_under > 0:
            out_under = os.path.join(scratch_gdb, f"nedovrsene_cevi_errors_{ts}")
            arcpy.management.CopyFeatures(lyr, out_under)
            outputs.append(out_under)

        error_count = cnt_over + cnt_under

        if error_count == 0:
            outputs = []
        else:
            out_selected = ""  # no output created

    except Exception as e:
        status = "FAIL"
        notes = repr(e)
        raise
    finally:
        for tmp in [merged_pts, sj_out]:
            try:
                if arcpy.Exists(tmp):
                    arcpy.management.Delete(tmp)
            except Exception:
                pass
        try:
            arcpy.management.Delete("lines_sj_lyr")
        except Exception:
            pass
        try:
            arcpy.management.ClearWorkspaceCache()
        except Exception:
            pass

    return {
        "validator": validator,
        "status": status,
        "error_count": error_count,
        "output_path": out_selected,
        "inputs": f"lines={lines_fc}; points={len(point_fcs)}; expected={expected}",
        "notes": notes,
        "duration_s": t.seconds(),
    }
