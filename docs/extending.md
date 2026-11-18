# Extending

[← README](../README.md)

- **New file type:** list its suffix in `glazed/io.py`, then map it to a Blender
  importer in `IMPORTERS`, or to an `Asset` subclass in `LOADERS`, in
  `glazed/render/assets.py`. For the preview, map it to a three.js loader in
  `LOADERS` in `glazed/preview.html`.
- **New asset type:** subclass `Asset`, build its objects in `__init__`, and
  override `paint()`.
- **New domain guide for the skill:** add a Markdown file to
  `skills/glazed-render/references/` and list it in `SKILL.md`.
