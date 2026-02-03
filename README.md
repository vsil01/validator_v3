# Spatial Validator (ArcPy)

## What you get
- 6 validators with the SAME interface: `main(cfg) -> dict`
- `runner.py` that runs all validators and appends a single results CSV

## Results CSV schema
Columns:
run_id, timestamp, project, validator, status, error_count, output_path, inputs, notes, duration_min

## Run
1) Copy this folder somewhere on your desktop folder
2) Edit `config_example.json` (paths + layer names)
3) Launch ArcGIS proenv.bat file (C:\Program Files\ArcGIS\Pro\bin\Python\Scripts\proenv)
4) Run:
   'C:\path_to_your_validator_folder'
3) Run:
   `python runner.py config_example.json`

