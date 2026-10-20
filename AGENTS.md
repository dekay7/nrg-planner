# Development

- Integration: `custom_components/nrg/`; tests: `tests/`.
- Follow the [checks](README.md#development) and [release workflow](README.md#releases).
- Preserve Observation defaults, explicit control permissions, and user settings/learning across updates.
- Use invented fixtures. Keep credentials and household data out of source, logs, and commits.
- Regenerate UI, translations, dashboards, and handbook with `python -B tools/build_ui.py`; do not hand-edit generated files.
- Publish releases only when explicitly requested. Keep version values aligned and never move published tags.
