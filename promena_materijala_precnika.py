\
import os
import datetime
import arcpy
from common import ensure_dir, Timer, ensure_gdb, resolve_layer

arcpy.env.overwriteOutput = True

def main(cfg: dict) -> dict:
    """
    Check: fittings points of type 'Promena materijala' and 'Redukcija prečnika'
    must connect to 2 pipes with DIFFERENT materijal / precnik respectively.
    Exports error points as shapefiles.
    """
    t = Timer()
    validator = "promena_materijala_precnika"
    conf = cfg["PROMENA_MATERIJALA_PRECNIKA"]

    pipes_fc = resolve_layer(cfg, conf["PIPES_FC"])
    fittings_fc = resolve_layer(cfg, conf["FITTINGS_FC"])
    tip_field = conf.get("TIP_FIELD", "tip")
    material_field = conf.get("MATERIAL_FIELD", "materijal")
    diameter_field = conf.get("DIAMETER_FIELD", "precnik")
    require_exactly_2 = bool(conf.get("REQUIRE_EXACTLY_2_PIPES", True))
    
    scratch_gdb = ensure_gdb(cfg.get("SCRATCH_GDB") or arcpy.env.scratchGDB, arcpy=arcpy)
    ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")

    out_mat = os.path.join(scratch_gdb, f"Promena_materijala_error_{ts}")
    out_dia = os.path.join(scratch_gdb, f"Redukcija_precnika_error_{ts}")

    # Select relevant fittings
    lyr_fit = "lyr_fit"
    arcpy.management.MakeFeatureLayer(fittings_fc, lyr_fit)

    # We'll iterate fittings and test intersecting pipes using SelectLayerByLocation on pipes layer
    lyr_pipes = "lyr_pipes"
    arcpy.management.MakeFeatureLayer(pipes_fc, lyr_pipes)

    mat_oids = []
    dia_oids = []

    with arcpy.da.SearchCursor(lyr_fit, ["OID@", tip_field]) as cur:
        for oid, tip in cur:
            if tip not in ("Promena materijala", "Redukcija prečnika"):
                continue

            arcpy.management.SelectLayerByAttribute(lyr_pipes, "CLEAR_SELECTION")
            arcpy.management.SelectLayerByLocation(lyr_pipes, "INTERSECT", arcpy.Describe(lyr_fit).catalogPath, selection_type="NEW_SELECTION")
            # The above selects pipes intersecting ANY selected fitting; so instead do by OID selection:
            
            oid_field = arcpy.Describe(lyr_fit).OIDFieldName
            oid_field_delim = arcpy.AddFieldDelimiters(lyr_fit, oid_field)
            arcpy.management.SelectLayerByAttribute(lyr_fit, "NEW_SELECTION", f"{oid_field_delim} = {oid}")

            arcpy.management.SelectLayerByLocation(lyr_pipes, "INTERSECT", lyr_fit, selection_type="NEW_SELECTION")

            pipe_count = int(arcpy.management.GetCount(lyr_pipes)[0])

            # Extract attribute values from selected pipes
            vals_material = []
            vals_dia = []
            with arcpy.da.SearchCursor(lyr_pipes, [material_field, diameter_field]) as pc:
                for m, d in pc:
                    vals_material.append(m)
                    vals_dia.append(d)

            if require_exactly_2 and pipe_count != 2:
                # treat as error for both types because topology is unexpected
                if tip == "Promena materijala":
                    mat_oids.append(oid)
                else:
                    dia_oids.append(oid)
                continue

            if tip == "Promena materijala":
                # error if materials are equal (or only one distinct)
                if len(set(map(str, vals_material))) <= 1:
                    mat_oids.append(oid)
            elif tip == "Redukcija prečnika":
                if len(set(map(str, vals_dia))) <= 1:
                    dia_oids.append(oid)

    # Export errors
    mat_cnt = len(mat_oids)
    dia_cnt = len(dia_oids)
    out_paths = []

    if mat_cnt:
        oid_field = arcpy.Describe(lyr_fit).OIDFieldName
        oid_field_delim = arcpy.AddFieldDelimiters(lyr_fit, oid_field)
        arcpy.management.SelectLayerByAttribute(
            lyr_fit,
            "NEW_SELECTION",
            f"{oid_field_delim} IN ({','.join(map(str, mat_oids))})",
        )
        arcpy.management.CopyFeatures(lyr_fit, out_mat)
        out_paths.append(out_mat)

    if dia_cnt:
        oid_field = arcpy.Describe(lyr_fit).OIDFieldName
        oid_field_delim = arcpy.AddFieldDelimiters(lyr_fit, oid_field)
        arcpy.management.SelectLayerByAttribute(
            lyr_fit,
            "NEW_SELECTION",
            f"{oid_field_delim} IN ({','.join(map(str, dia_oids))})",
        )
        arcpy.management.CopyFeatures(lyr_fit, out_dia)
        out_paths.append(out_dia)

    # cleanup
    for lyr in [lyr_fit, lyr_pipes]:
        try:
            arcpy.management.Delete(lyr)
        except Exception:
            pass

    return {
        "validator": validator,
        "status": "OK",
        "error_count": mat_cnt + dia_cnt,
        "output_path": ";".join(out_paths),
        "inputs": f"pipes={pipes_fc}; fittings={fittings_fc}",
        "notes": f"require_exactly_2={require_exactly_2}",
        "duration_s": t.seconds(),
    }
