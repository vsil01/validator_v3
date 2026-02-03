import os
import datetime
import arcpy
from common import ensure_dir, Timer, ensure_gdb, resolve_layer

arcpy.env.overwriteOutput = True

def main(cfg: dict) -> dict:
    """
    Check: pipes attributes completeness / consistency.
    Exports error features to shapefile.
    """
    t = Timer()
    validator = "atribute_cevi"
    conf = cfg["ATRIBUTE_CEVI"]

    pipes_fc = resolve_layer(cfg, conf["PIPES_FC"])
    required_fields = conf.get("REQUIRED_FIELDS", [])
    where = conf.get("WHERE", None)  # optional SQL filter for features to check

    scratch_gdb = ensure_gdb(cfg.get("SCRATCH_GDB") or arcpy.env.scratchGDB, arcpy=arcpy)
    ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    out_err = os.path.join(scratch_gdb, f"{validator}_errors_{ts}")

    lyr = "lyr_pipes_attr"
    arcpy.management.MakeFeatureLayer(pipes_fc, lyr, where_clause=where)

    missing_oids = []
    fields = ["OID@"] + required_fields

    with arcpy.da.SearchCursor(lyr, fields) as cur:
        for row in cur:
            oid = row[0]
            values = row[1:]
            bad = False
            for v in values:
                if v is None:
                    bad = True
                    break
                if isinstance(v, str) and v.strip() == "":
                    bad = True
                    break
            if bad:
                missing_oids.append(oid)

    cnt = len(missing_oids)
    if cnt:
        oid_field = arcpy.Describe(lyr).OIDFieldName
        oid_field_delim = arcpy.AddFieldDelimiters(lyr, oid_field)
        arcpy.management.SelectLayerByAttribute(
            lyr,
            "NEW_SELECTION",
            f"{oid_field_delim} IN ({','.join(map(str, missing_oids))})",
        )
        arcpy.management.CopyFeatures(lyr, out_err)
    else:
        out_err = ""

    try:
        arcpy.management.Delete(lyr)
    except Exception:
        pass

    return {
        "validator": validator,
        "status": "OK",
        "error_count": cnt,
        "output_path": out_err,
        "inputs": f"pipes={pipes_fc}; required_fields={required_fields}",
        "notes": where or "",
        "duration_s": t.seconds(),
    }
