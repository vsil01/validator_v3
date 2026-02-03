# Validator Config Wizard (Test)

Simple Tkinter desktop app for editing the core `config.json` values without touching code.

## Run

```bash
python wizard_app/app.py
```

## Desktop icon launcher

A ready-to-use `.desktop` launcher is included at `wizard_app/validator_config_wizard.desktop`.
Update the paths inside `Exec=` and `Icon=` if your repo lives elsewhere, then:

```bash
chmod +x wizard_app/validator_config_wizard.desktop
```

You can double-click it in a Linux desktop environment, or copy it to your desktop/applications
folder as needed.

## Fields

- Project name (`PROJECT`)
- Input GDB (`INPUT_GDB`)
- Scratch/Output GDB (`SCRATCH_GDB`)
- Results CSV (`RESULTS_CSV`)

The app reads/writes the repo-level `config.json` file.
