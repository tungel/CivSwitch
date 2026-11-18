# Vendored CivSwitchLDN installer assets

Copied from https://github.com/ItsNerisma/CivSwitchLDN at commit
`1be5ad55985bb13ff8e05dfcecbc9cc822e86b6f` (branch `main`, vendored 2026-11-18) so the one-shot
installer the ESP32 serves is byte-identical to what that launcher writes, with no second checkout.

| file                | sha256                                                             | upstream path                 |
|---------------------|--------------------------------------------------------------------|-------------------------------|
| `core.js`           | `c386ed8635ea0f39f5a69b6d1b86f7235557a5f5e8ea8c62366d0d3d21a42cf1` | `payloads/core.js`            |
| `install.py`        | `0bc9a184efc42c8d0b929c24bb8a94a21af78941c6ccee97c6c57e57a42191fb` | `installer/install.py`        |
| `compress_stage.js` | `2c02d3c9f9a6db1f30c58deb50b8e50a7e1f18f10e86ee4e20da13de7c805f5a` | `installer/compress_stage.js` |
| `save_template.bin` | `32fa8a0d6dd0a480d8e541e63ea44c4619bc6f7be4282cfc3cb6a4f6d305dfae` | `installer/save_template.bin` |

`tools/build_s2_ldn.sh` uses this directory by default; `tools/build_and_flash.py` alone keeps using
`../installer-creator`. Result: apply JS 29255 bytes, stage hex 23218 chars, so the console prints
`RUNNING INSTALLER (29255 bytes)`.

Two differences from `../installer-creator` worth knowing:

- Its `BLOCK` has no `XSTRIG.Civ7Save` delete guard - the installer removes **every** file in
  `save:/saves/Single/`. Move real saves off the game first.
- `compress_stage.js` needs terser; `make_install_blobs.py` points `NODE_PATH` at
  `../installer-creator/node_modules` when this directory has none, so one `npm install` there
  covers both.

Refresh from a checkout (reports what changed):

```sh
tools/vendor_civswitchldn.sh /path/to/CivSwitchLDN
```
