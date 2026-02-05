# Validator Config Wizard (Windows)

Tkinter desktop app for editing validator `config.json` and running `runner.py` without terminal usage.

## What it does

- Lets user fill these fields:
  - `PROJECT`
  - `INPUT_GDB`
  - `SCRATCH_GDB`
  - `RESULTS_CSV`
- Saves values to repo-level `config.json`
- Runs validator (`runner.py config.json`) from GUI button

## Run

### Option 1: Python

```bat
python wizard_app\app.py
```

### Option 2: Double-click launcher

```bat
wizard_app\validator_config_wizard.bat
```

## Create Windows shortcut (.lnk)

```powershell
powershell -ExecutionPolicy Bypass -File wizard_app\create_windows_shortcut.ps1
```

This creates `Validator Config Wizard.lnk` in `wizard_app` folder. Move it to Desktop if needed.
