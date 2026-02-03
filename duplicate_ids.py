import os
import datetime
import arcpy
from common import ensure_dir, Timer, ensure_gdb, resolve_layer

arcpy.env.overwriteOutput = True

def main(cfg: dict) -> dict:
    """
    Check: duplicate IDs in one or more datasets. Exports duplicate features.
    Now supports both single FC and multiple layers.
    """
    t = Timer()
    validator = "duplicate_ids"
    conf = cfg["DUPLICATE_IDS"]

    # Support both old single-FC format and new multi-layer format
    if "FC" in conf:
        # Old format: single feature class
        layers = [conf["FC"]]
    elif "LAYERS" in conf:
        # New format: list of feature classes
        layers = conf["LAYERS"]
    else:
        raise ValueError("DUPLICATE_IDS config must have either 'FC' or 'LAYERS' key")

    id_field = conf["ID_FIELD"]
    scratch_gdb = ensure_gdb(cfg.get("SCRATCH_GDB") or arcpy.env.scratchGDB, arcpy=arcpy)
    ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")

    # Process each layer
    total_errors = 0
    layer_results = []
    output_paths = []

    for layer_name in layers:
        fc = resolve_layer(cfg, layer_name)
        
        # Check if layer exists
        if not arcpy.Exists(fc):
            layer_results.append(f"{layer_name}: NOT FOUND")
            continue

        # Build counts
        counts = {}
        try:
            with arcpy.da.SearchCursor(fc, [id_field]) as cur:
                for (v,) in cur:
                    key = "" if v is None else str(v).strip()
                    counts[key] = counts.get(key, 0) + 1
        except Exception as e:
            layer_results.append(f"{layer_name}: ERROR - {str(e)}")
            continue

        dup_vals = [k for k, c in counts.items() if k != "" and c > 1]
        
        if not dup_vals:
            layer_results.append(f"{layer_name}: OK (0 duplicates)")
            continue

        # Select duplicates
        lyr = f"lyr_dups_{layer_name}"
        out_err = os.path.join(scratch_gdb, f"{validator}_{layer_name}_{ts}")
        
        try:
            arcpy.management.MakeFeatureLayer(fc, lyr)
            
            # Build safe SQL: split in chunks to avoid long IN
            where_parts = []
            for chunk in chunk_list(dup_vals, 999):
                vals = ",".join([sql_quote(fc, id_field, v) for v in chunk])
                where_parts.append(f"{arcpy.AddFieldDelimiters(fc, id_field)} IN ({vals})")
            where = " OR ".join(where_parts)
            arcpy.management.SelectLayerByAttribute(lyr, "NEW_SELECTION", where)

            cnt = int(arcpy.management.GetCount(lyr)[0])
            arcpy.management.CopyFeatures(lyr, out_err)

            total_errors += cnt
            output_paths.append(out_err)
            layer_results.append(f"{layer_name}: {cnt} features ({len(dup_vals)} distinct IDs)")

            try:
                arcpy.management.Delete(lyr)
            except Exception:
                pass
                
        except Exception as e:
            layer_results.append(f"{layer_name}: ERROR exporting - {str(e)}")

    # Build summary
    status = "OK" if total_errors == 0 else "ERRORS_FOUND"
    inputs_str = f"layers={', '.join(layers)}; id_field={id_field}"
    notes_str = "; ".join(layer_results)
    output_str = "; ".join(output_paths) if output_paths else ""

    return {
        "validator": validator,
        "status": status,
        "error_count": total_errors,
        "output_path": output_str,
        "inputs": inputs_str,
        "notes": notes_str,
        "duration_s": t.seconds(),
    }

def chunk_list(lst, n):
    for i in range(0, len(lst), n):
        yield lst[i:i+n]

def sql_quote(fc, field, v):
    # For text fields, quote with single quotes; for numeric leave as is.
    f = [f for f in arcpy.ListFields(fc) if f.name.lower()==field.lower()][0]
    if f.type in ("Integer","SmallInteger","Single","Double"):
        return str(v)
    # escape single quotes
    s = str(v).replace("'", "''")
    return f"'{s}'"