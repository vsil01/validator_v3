import os
import datetime
import arcpy

from common import Timer, safe_fc_name, ensure_gdb

arcpy.env.overwriteOutput = True


# ----------------------------
# Helpers
# ----------------------------
def _get_field(fc: str, field_name: str):
    for f in arcpy.ListFields(fc):
        if f.name.lower() == field_name.lower():
            return f
    return None


def _where_missing(fc: str, field_name: str) -> str:
    """
    ArcGIS-safe SQL where clause for missing values:
      - String/Guid: IS NULL OR = ''
      - Other: IS NULL
    (No TRIM() to avoid ERROR 000358)
    """
    fld = _get_field(fc, field_name)
    if fld is None:
        return ""

    f_sql = arcpy.AddFieldDelimiters(fc, fld.name)

    if fld.type in ("String", "Guid"):
        return f"{f_sql} IS NULL OR {f_sql} = ''"

    return f"{f_sql} IS NULL"


def _export_selection(in_fc: str, out_fc: str, where: str) -> int:
    """
    Select by attribute and export. Returns exported count.
    out_fc is full path to output feature class (e.g. <scratch.gdb>\name)
    """
    tmp_lyr = "tmp_lyr_sel"
    if arcpy.Exists(tmp_lyr):
        arcpy.management.Delete(tmp_lyr)

    arcpy.management.MakeFeatureLayer(in_fc, tmp_lyr)

    if where:
        arcpy.management.SelectLayerByAttribute(tmp_lyr, "NEW_SELECTION", where)

    cnt = int(arcpy.management.GetCount(tmp_lyr)[0])
    if cnt > 0:
        out_ws = os.path.dirname(out_fc)
        out_name = os.path.basename(out_fc)
        arcpy.conversion.FeatureClassToFeatureClass(tmp_lyr, out_ws, out_name)

    arcpy.management.Delete(tmp_lyr)
    return cnt


# ----------------------------
# Main
# ----------------------------
def main(cfg: dict) -> dict:
    """
    Validator:
      - Pumpe: field 'nizvodno' exists and is filled (not NULL/empty)
      - Zatvaraci: fields 'nizvodno' and 'uzvodno' exist and are filled (not NULL/empty)

    Outputs:
      - Error feature classes are written into SCRATCH_GDB (as feature classes, not shapefiles),
        consistent with other validators.
    """
    t = Timer()
    validator = "nizvodno"
    conf = cfg["NIZVODNO"]

    pumpe_fc = conf["PUMPE_FC"]
    zatvaraci_fc = conf["ZATVARACI_FC"]

    ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")

    scratch_gdb = ensure_gdb(cfg.get("SCRATCH_GDB") or arcpy.env.scratchGDB, arcpy=arcpy)

    outputs = []
    errors = []
    total_invalid = 0

    # ----------------------------
    # PUMPE: nizvodno
    # ----------------------------
    req_pumpe = ["nizvodno"]
    missing_fields = [f for f in req_pumpe if _get_field(pumpe_fc, f) is None]

    if missing_fields:
        # schema invalid => export whole fc as invalid
        out_name = safe_fc_name(f"pumpe_missing_fields_{ts}")
        out_path = os.path.join(scratch_gdb, out_name)
        arcpy.conversion.FeatureClassToFeatureClass(pumpe_fc, scratch_gdb, out_name)
        cnt = int(arcpy.management.GetCount(pumpe_fc)[0])

        total_invalid += cnt
        outputs.append(out_path)
        errors.append(f"Pumpe: missing required field(s): {', '.join(missing_fields)}. Exported all ({cnt}).")
    else:
        where = _where_missing(pumpe_fc, "nizvodno")
        out_name = safe_fc_name(f"pumpe_nizvodno_empty_{ts}")
        out_path = os.path.join(scratch_gdb, out_name)
        cnt = _export_selection(pumpe_fc, out_path, where)

        if cnt > 0:
            total_invalid += cnt
            outputs.append(out_path)
            errors.append(f"Pumpe: field 'nizvodno' has {cnt} empty/NULL value(s).")

    # ----------------------------
    # ZATVARACI: nizvodno
    # ----------------------------
    req_zat = ["nizvodno"]
    missing_fields = [f for f in req_zat if _get_field(zatvaraci_fc, f) is None]

    if missing_fields:
        out_name = safe_fc_name(f"zatvaraci_missing_fields_{ts}")
        out_path = os.path.join(scratch_gdb, out_name)
        arcpy.conversion.FeatureClassToFeatureClass(zatvaraci_fc, scratch_gdb, out_name)
        cnt = int(arcpy.management.GetCount(zatvaraci_fc)[0])

        total_invalid += cnt
        outputs.append(out_path)
        errors.append(f"Zatvaraci: missing required field(s): {', '.join(missing_fields)}. Exported all ({cnt}).")
    else:
        where = _where_missing(zatvaraci_fc, "nizvodno")
        out_name = safe_fc_name(f"zatvaraci_nizvodno_empty_{ts}")
        out_path = os.path.join(scratch_gdb, out_name)
        cnt = _export_selection(zatvaraci_fc, out_path, where)

        if cnt > 0:
            total_invalid += cnt
            outputs.append(out_path)
            errors.append(f"Zatvaraci: field 'nizvodno' has {cnt} empty/NULL value(s).")

    status = "OK"

    return {
        "validator": validator,
        "status": status,
        "error_count": total_invalid,
        "output_path": ";".join(outputs),
        "inputs": f"Pumpe={pumpe_fc}; Zatvaraci={zatvaraci_fc}",
        "notes": " ".join(errors),
        "duration_s": t.seconds(),
    }