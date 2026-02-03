import os
import datetime
import arcpy

from common import Timer, ensure_gdb, safe_fc_name, resolve_layer

arcpy.env.overwriteOutput = True


# ----------------------------
# Helpers
# ----------------------------
def repl_safe(s: str) -> str:
    return "".join(ch if ch.isalnum() else "_" for ch in s)[:40]


def cfg_field(cfg: dict, field_key_or_name: str, default: str = None) -> str:
    """
    Semantic field mapping:
      cfg["FIELDS"]["TYPE"] = "tip"
    If key not found, treat it as real field name.
    """
    if not field_key_or_name:
        return default
    return cfg.get("FIELDS", {}).get(field_key_or_name, field_key_or_name) or default


def cfg_value(cfg: dict, group: str, key: str, default=None):
    return cfg.get("VALUES", {}).get(group, {}).get(key, default)


def get_real_field_name(fc: str, desired_name: str):
    """Return real field name (case-safe)."""
    if not desired_name:
        return None
    for f in arcpy.ListFields(fc):
        if f.name.lower() == desired_name.lower():
            return f.name
    return None


def chunk_list(lst, n=900):
    for i in range(0, len(lst), n):
        yield lst[i:i + n]


def is_actual_valid(actual: int, expected_def) -> bool:
    """
    Backward compatible + operators:
      - int/float            => exact match
      - list/tuple/set       => membership
      - dict {"op":">=","value":2} => comparison
      - None => SKIP (treated as valid/no rule)
    """
    if expected_def is None:
        return True

    # operator object
    if isinstance(expected_def, dict):
        op = expected_def.get("op")
        val = expected_def.get("value")
        if val is None:
            return True  # nothing to validate

        if op == ">=":
            return actual >= val
        if op == "<=":
            return actual <= val
        if op == ">":
            return actual > val
        if op == "<":
            return actual < val
        if op == "!=":
            return actual != val
        if op == "==":
            return actual == val

        raise ValueError(f"Unsupported EXPECTED operator: {op}")

    # membership
    if isinstance(expected_def, (list, tuple, set)):
        return actual in expected_def

    # exact
    return actual == expected_def


def _match_ignore(op: str, actual, expected) -> bool:
    """
    Supports a minimal set:
      '=' / '=='  , '!=' , 'IN'
    """
    if op is None:
        op = "="
    op = op.upper()

    if op in ("=", "=="):
        return actual == expected
    if op == "!=":
        return actual != expected
    if op == "IN":
        # expected should be list/tuple/set
        try:
            return actual in expected
        except TypeError:
            return False
    return False


# ----------------------------
# Main
# ----------------------------
def main(cfg: dict) -> dict:
    t = Timer()
    validator = "secenje_tacaka"
    conf = cfg["SECENJE_TACAKA"]

    merge_layer = resolve_layer(cfg, conf["MERGE_LAYER"])
    layers = conf["LAYERS"]

    ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    scratch_gdb = ensure_gdb(cfg.get("SCRATCH_GDB") or arcpy.env.scratchGDB, arcpy=arcpy)

    # --- Inactive filter (optional) ---
    inactive_conf = conf.get("INACTIVE_FILTER", {}) or {}
    inactive_enabled = bool(inactive_conf.get("ENABLED", False))
    inactive_layers = set(inactive_conf.get("APPLY_TO_LAYERS", []) or [])

    inactive_field_key = inactive_conf.get("FIELD_KEY", "STATUS")
    inactive_value_group = inactive_conf.get("VALUE_GROUP", "STATUS")
    inactive_value_key = inactive_conf.get("VALUE_KEY", "INACTIVE")

    inactive_field_cfg = cfg_field(cfg, inactive_field_key, default="status")
    inactive_value = cfg_value(cfg, inactive_value_group, inactive_value_key, default=None)

    # --- Ignore rules (your style: VALUE literal) ---
    ignore_rules_cfg = conf.get("IGNORE_RULES", []) or []

    error_count_total = 0
    outputs = []

    for item in layers:
        raw_ref = item.get("PATH") or item.get("LAYER") or item.get("NAME")
        layer_path = resolve_layer(cfg, raw_ref)
        layer_name = item.get("NAME") or os.path.splitext(os.path.basename(layer_path))[0]

        if not arcpy.Exists(layer_path):
            continue

        sj_out = os.path.join(scratch_gdb, f"sj_{repl_safe(layer_name)}_{ts}")
        out_err = os.path.join(scratch_gdb, f"{safe_fc_name(layer_name, 35)}_errors_{ts}")

        # SpatialJoin to compute Join_Count per point
        arcpy.analysis.SpatialJoin(
            target_features=layer_path,
            join_features=merge_layer,
            out_feature_class=sj_out,
            join_operation="JOIN_ONE_TO_ONE",
            join_type="KEEP_ALL",
            match_option="INTERSECT",
        )

        # Rule setup
        tip_rules = item.get("TIP_RULES")
        expected_fixed = item.get("EXPECTED")
        tip_field_cfg = item.get("TIP_FIELD", "tip")

        # Resolve real field names on sj_out
        join_count_field = get_real_field_name(sj_out, "Join_Count") or "Join_Count"

        real_tip = None
        if tip_rules:
            real_tip = get_real_field_name(sj_out, tip_field_cfg)

        # Config-driven inactive exclusion
        use_inactive_filter = inactive_enabled and (layer_name in inactive_layers) and (inactive_value is not None)
        real_status = get_real_field_name(sj_out, inactive_field_cfg) if use_inactive_filter else None

        # Config-driven ignore rules for this layer
        layer_ignore_rules = []
        for r in ignore_rules_cfg:
            if r.get("APPLY_TO_LAYER") != layer_name:
                continue
            # Field key (semantic) -> physical field name
            fld = cfg_field(cfg, r.get("FIELD_KEY"))
            real_fld = get_real_field_name(sj_out, fld)
            if not real_fld:
                continue
            layer_ignore_rules.append({
                "FIELD": real_fld,
                "OP": r.get("OP", "="),
                "VALUE": r.get("VALUE")
            })

        # Build cursor fields minimal + whatever needed for rules
        cursor_fields = ["OID@", join_count_field]
        if tip_rules and real_tip:
            cursor_fields.append(real_tip)
        if real_status:
            cursor_fields.append(real_status)
        for r in layer_ignore_rules:
            if r["FIELD"] not in cursor_fields:
                cursor_fields.append(r["FIELD"])

        idx = {f: i for i, f in enumerate(cursor_fields)}

        invalid_oids = []

        with arcpy.da.SearchCursor(sj_out, cursor_fields) as cur:
            for row in cur:
                oid = row[idx["OID@"]]
                actual_raw = row[idx[join_count_field]]
                actual = int(actual_raw) if actual_raw is not None else 0

                # Ignore rules (skip validation entirely)
                ignored = False
                for r in layer_ignore_rules:
                    a = row[idx[r["FIELD"]]]
                    if _match_ignore(r["OP"], a, r["VALUE"]):
                        ignored = True
                        break
                if ignored:
                    continue

                # Inactive exclusion (skip as "not an error")
                if real_status:
                    st = row[idx[real_status]]
                    if st is not None and str(st).strip() == str(inactive_value):
                        continue

                # TIP_RULES mode (with fallback to EXPECTED)
                if tip_rules and real_tip:
                    tip_val = row[idx[real_tip]]
                    exp_def = tip_rules.get(tip_val, None)

                    # NEW: if tip not listed in TIP_RULES, fall back to EXPECTED (if provided)
                    if exp_def is None:
                        exp_def = expected_fixed

                    if exp_def is None:
                        continue  # SKIP (no rule at all)

                    if not is_actual_valid(actual, exp_def):
                        invalid_oids.append(oid)
                else:
                    # Fixed EXPECTED mode
                    if expected_fixed is None:
                        continue  # SKIP
                    if not is_actual_valid(actual, expected_fixed):
                        invalid_oids.append(oid)

        # Export invalids (fast, chunked selection)
        cnt = len(invalid_oids)
        error_count_total += cnt

        if cnt > 0:
            lyr = f"lyr_{repl_safe(layer_name)}_{ts}"
            arcpy.management.MakeFeatureLayer(sj_out, lyr)

            oid_field = arcpy.Describe(lyr).OIDFieldName
            oid_sql = arcpy.AddFieldDelimiters(lyr, oid_field)

            first = True
            for chunk in chunk_list(invalid_oids, 900):
                where = f"{oid_sql} IN ({','.join(map(str, chunk))})"
                arcpy.management.SelectLayerByAttribute(
                    lyr,
                    "NEW_SELECTION" if first else "ADD_TO_SELECTION",
                    where
                )
                first = False

            arcpy.management.CopyFeatures(lyr, out_err)
            outputs.append(out_err)

            try:
                arcpy.management.Delete(lyr)
            except Exception:
                pass

        # Cleanup per layer
        try:
            arcpy.management.Delete(sj_out)
        except Exception:
            pass

    return {
        "validator": validator,
        "status": "OK",
        "error_count": error_count_total,
        "output_path": ";".join(outputs),
        "inputs": f"merge={merge_layer}; layers={len(layers)}",
        "notes": "optimized + ignore_rules + expected_ops",
        "duration_s": t.seconds(),
    }