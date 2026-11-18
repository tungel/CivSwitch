# esp32-ldn-civ7 — offline CivSwitch installer over Local Wireless (LDN)

![Console screen after a successful run](Screenshot_1.jpg)

An ESP32-S3 that joins the console's **Civ VII wireless lobby** and injects the
CivSwitch payload over **local wireless** — no PC, no USB HID typing, no Wi-Fi
or LAN access, and **no system-language or controller-layout changes**.

With the payload it also carries the full persistent installer (the 1 MB save
template), so one run does everything: exploit → installer → back to the normal
TCP loader on `:9026`.

## Why another board firmware?

`esp32-usb-pad` (the "net-pad") types the payload over a **USB HID keyboard**
and exposes a Wi-Fi web UI. It works for any game that needs autotyping, and it
is the right choice for future titles.

This firmware is **Civ VII specific** and is the recommended path today:

|                       | `esp32-usb-pad` (net-pad)                     | `esp32-ldn-civ7` (this)                                 |
|-----------------------|-----------------------------------------------|---------------------------------------------------------|
| Transport             | USB HID typing                                | Civ VII wireless lobby (LDN)                            |
| Console setup         | English/USB keyboard language, layout changes | none                                                    |
| PC required           | for the web UI / installer upload             | **no**                                                  |
| Network required      | Wi-Fi (console + board)                       | **none** (LDN only)                                     |
| Secrets               | —                                             | your own `prod.keys` (derived keys baked at build time) |
| Speed                 | ~7 minutes of typing                          | ~10-15 seconds                                          |
| Works for other games | yes (autotyping)                              | no (Civ VII only)                                       |

The LDN path matters when the console cannot reach the internet: a heavily
blocked DNS setup (e.g. 90DNS) makes the console refuse to stay online, so
anything that needs the console's LAN is unreliable. This firmware never leaves
the local-wireless link.

## Requirements

| Item       | Value                                                                                                                                                                                                                   |
|------------|-------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| Board      | ESP32-S3 (**16 MB** flash, 4 MB works if you shrink the storage partition) **or** ESP32-S2 (Wemos/LOLIN S2 Mini, `ESP32-S2FN4R2`, 4 MB flash: the stock partition map already ends at `0x310000`, so nothing to shrink) |
| Toolchain  | ESP-IDF **v6.1**, or nothing at all with `--docker` (official `espressif/idf:v6.1` image)                                                                                                                               |
| Host tools | Node.js (for `terser`), Python 3.10+                                                                                                                                                                                    |
| Console    | Switch 2, Civ VII **1.0.0 physical cartridge** (Switch 1 edition)                                                                                                                                                       |
| Keys       | your own `prod.keys`, dumped from your Switch 1                                                                                                                                                                         |
| Game state | `MULTIPLAYER → WIRELESS → CREATE GAME → HOST LOBBY`                                                                                                                                                                     |

`prod.keys` is **never committed** — `keys.h` is generated at build time and is
gitignored together with the payloads and blobs.

## One-click build + flash

### ESP32-S2 (recommended: vendored CivSwitchLDN installer, container build)

```sh
cd CivSwitch/esp32-ldn-civ7
rm -rf build-esp32s2-docker blobs main/keys.h main/chat_payload.h   # optional: start from scratch
KEYS=/path/to/prod.keys tools/build_s2_ldn.sh --port /dev/ttyACM0 --flash
```

Hold BOOT, tap RESET, release once `esptool` starts writing (on an S2 Mini nothing drives BOOT from
DTR/RTS, so *every* flash starts that way, not just the first). The wrapper pins `--docker
--target esp32s2` and the vendored `civswitchldn/` assets, so the console prints
`RUNNING INSTALLER (29255 bytes)` - byte-identical to what CivSwitchLDN writes from a PC. The host
needs Docker and Node.js only (`npm install` in `../installer-creator` supplies terser). Extra
arguments pass through (`--erase`, `--no-build`, `--docker <image>`), and `LDN=/path/CivSwitchLDN`
builds from a live checkout instead of the vendored copy.

### Underlying command (ESP32-S3, host ESP-IDF, or your own assets)

`tools/build_s2_ldn.sh` wraps `tools/build_and_flash.py`; call it directly for the S3, a sourced
host toolchain, or different asset inputs:

```sh
cd CivSwitch/esp32-ldn-civ7
source /path/to/esp-idf/export.sh      # idf.py on PATH
python3 tools/build_and_flash.py \
    --keys /path/to/prod.keys \
    --port /dev/cu.usbmodem1234 \
    --flash
```

What it does:

1. `main/keys.h` from your `prod.keys` (`tools/make_keys.py`);
2. `main/chat_payload.h` from the **shared `../core.js`** + the UDP installer
   channel (`tools/make_payload.py`) — so an upstream CivSwitch update is picked
   up by rerunning this command;
3. `blobs/blob_tpl.bin` (save template, base64) and `blobs/blob_apply.bin`
   (installer JS, base64) via `tools/make_install_blobs.py`;
4. `idf.py build`;
5. `esptool write-flash`: bootloader + partition table + app + both blobs.

Options: `--erase` (full chip erase first), `--no-build` (regenerate assets
only), `--core path` (use a different `core.js`), `--port $ESPPORT`.

`--core` and `--installer-dir` together decide what the one-shot installer is: `--core` selects the
JS the stage is built from, `--installer-dir` selects the directory that supplies `BLOCK`,
`compress_stage.js` and `save_template.bin` (default `../installer-creator`). Point it at
`../CivSwitchLDN/installer` to get installer blobs byte-identical to that launcher's (apply JS
29255 bytes, so the console prints `RUNNING INSTALLER (29255 bytes)`); `civswitchldn/` is exactly
that directory vendored into this repo. Two caveats about CivSwitchLDN's `BLOCK`: it has no
`XSTRIG.Civ7Save` delete guard, so it removes every file in `save:/saves/Single/` - move real saves
off the game first - and its `compress_stage.js` needs terser, which `make_install_blobs.py` finds
through `NODE_PATH=../installer-creator/node_modules` when the installer directory has none.

`CIVSWITCH_KEYS`, `CIVSWITCH_CORE` and `CIVSWITCH_INSTALLER_DIR` set those defaults for a whole
shell. CivSwitch's own `core.js` and `installer-creator/` stay untouched - they also feed the PC
installer - so after a CivSwitchLDN update, refresh the vendored copy with
`tools/vendor_civswitchldn.sh /path/to/CivSwitchLDN`, which reports what changed.

If `idf.py` is not on PATH the script sources the ESP-IDF environment itself, trying
`$CIVSWITCH_IDF_ENV`, then `$IDF_PATH/export.sh`, then the install recorded in
`~/.espressif/idf-env.json`; if none of them yields `idf.py` it stops with an error
before touching any generated asset. Outside the container, `esptool` is picked the same way (the
first python that has the module), so a system python without esptool is fine.

### No ESP-IDF on this machine: `--docker`

```sh
python3 tools/build_and_flash.py --docker --target esp32s2 \
    --keys /path/to/prod.keys --port /dev/ttyACM0 --flash
```

`idf.py` and `esptool` then run inside `espressif/idf:v6.1` (the tag tracks the IDF release this
firmware needs); the three asset steps stay on the host because node is not in the image. The repo
is mounted at the path it has on the host, the container runs as your uid with `HOME=/tmp`, and
`--port` becomes `--device` plus `--group-add <gid of the port>` so the container can open it.
Container builds go to `build-<target>-docker/` so they never mix with a host build directory.
Container flashes use the image's own `esptool` - a host python path never runs inside the image.
First use pulls ~4 GB. Override the image with `--docker espressif/idf:v6.1.1` or
`CIVSWITCH_IDF_IMAGE`.

macOS: docker has no USB passthrough. Build with `--docker`, then copy the `+ ... esptool ...`
line the script prints and run it on the host, or serve the port with `esp_rfc2217_server -p 4000
/dev/cu.usbmodem1234` and pass `--port 'rfc2217://host.docker.internal:4000?ign_set_control'`.

### Flashing by hand from the container

Use this when the one-click flash step fails to reach the chip. It is the same `esptool` call the
script makes, run straight in the image (the image's own `esptool`, not a host python -
`/usr/bin/python3` exists in that image but has no esptool):

```sh
docker run --rm -i -v $PWD:$PWD -w $PWD -u $(id -u):$(id -g) -e HOME=/tmp -e IDF_GIT_SAFE_DIR='*' \
  --device /dev/ttyACM0 --group-add $(stat -c %g /dev/ttyACM0) espressif/idf:v6.1 \
  esptool --chip esp32s2 -p /dev/ttyACM0 -b 115200 --before no-reset --after hard-reset \
  write-flash --flash-mode dio --flash-freq 80m --flash-size 4MB \
  0x1000   build-esp32s2-docker/bootloader/bootloader.bin \
  0x8000   build-esp32s2-docker/partition_table/partition-table.bin \
  0x10000  build-esp32s2-docker/esp32-ldn-civ7.bin \
  0x110000 blobs/blob_tpl.bin \
  0x290000 blobs/blob_apply.bin
```

`No serial data received` on the S2 (and on any S2 Mini clone with no auto-reset circuit) is
normal, not a wiring fault: DTR/RTS do nothing on the S2's ROM USB CDC, so esptool cannot pick the
boot mode. Hold **BOOT**, tap **RESET**, release BOOT, then flash with `--before no-reset`; check
`dmesg | tail` afterwards because download mode re-enumerates and may hand you a new `ttyACM1`
(then change both `--device` and `-p`). `ls -l /dev/serial/by-id/` before and after unplugging the
board confirms which ACM device is yours. Every flash needs the button dance while the firmware
uses that same ROM CDC.

The S3 board differs in three places: `--chip esp32s3`, bootloader at `0x0` instead of `0x1000`,
and `build-docker/` instead of `build-esp32s2-docker/` (plus your module's `--flash-size`).

### ESP32-S2 boards (S2 Mini)

Build it with the recipe at the top of this section, or without the CivSwitchLDN pinning:

```sh
python3 tools/build_and_flash.py --target esp32s2 \
    --keys /path/to/prod.keys --port /dev/ttyACM0 --flash
```

`--target esp32s2` builds into `build-esp32s2/` from `sdkconfig.defaults.esp32s2`
and writes the bootloader at `0x1000` (the S2 ROM looks there; the S3 uses `0x0`).
Everything else (partition map, blob offsets, app) is identical, so the two
builds coexist in one tree.

The S2 has no USB-Serial/JTAG and the S2 Mini has no USB-UART bridge: the USB-C
port *is* the chip's native USB, so the console uses the ROM USB CDC stack
(`CONFIG_ESP_CONSOLE_USB_CDC`). Nothing drives BOOT or RESET from DTR/RTS on that
port, so *every* flash (not just the first) starts by forcing ROM download: hold
`BOOT`, tap `RESET`, release `BOOT`. See "Flashing by hand from the container"
for the matching `--before no-reset` invocation.

What changes on S2 (the radio patch itself is unchanged: the S2 prebuilt
`esp_wifi` libraries export every internal symbol this firmware uses, verified
against `build-esp32s2/esp32-ldn-civ7.map`):

- single core at 240 MHz instead of two → expect ~3 k token/s (S3 measures 4.8 k);
  `send_beacons()` (up to 100 raw TX frames per 100 ms) runs without a second core
  to absorb it, so watch for `beacon tx FAIL` on a crowded channel;
- the heap is the tight one: internal heap after this app is ~49 KB on S2 vs ~232 KB on S3.
  The dynamic RX/TX pools (pokeldn keeps 64+64) allocate on demand, so a beacon burst can ask
  for more than the S2 has. `sdkconfig.defaults.esp32s2` therefore enables the module's
  in-package PSRAM plus `SPIRAM_TRY_ALLOCATE_WIFI_LWIP` (S2 PSRAM is DMA capable) so those
  allocations have somewhere to go. pokeldn ships no PSRAM and no console at all; on a
  PSRAM-less module (`ESP32-S2FH4`) drop both `CONFIG_ESP_WIFI_DYNAMIC_*_BUFFER_NUM` to 16.
  `CONFIG_SPIRAM_IGNORE_NOTFOUND=y` means a board without PSRAM still boots;
- logging goes to the USB CDC console, which can stall if nothing drains it. For cable-free use
  (USB power bank) set `CONFIG_ESP_CONSOLE_NONE=y` and `CONFIG_LOG_DEFAULT_LEVEL_NONE=y`, which
  is what pokeldn does;
- app image 651 KB (S3: 667 KB) in the same 1 MB factory partition;
- no second console output: if the CDC enumeration misbehaves, wire a UART-to-USB
  bridge to `GPIO4` (TX) / `GPIO3` (RX) and set `CONFIG_ESP_CONSOLE_UART_DEFAULT`.

After flashing, **press RESET** on the board (esptool's reset can leave the chip
in ROM download mode).

## Run it

1. Start Civ VII and open `MULTIPLAYER → WIRELESS → CREATE GAME → HOST LOBBY`.
2. Power the board (USB power is enough; it does not need to be plugged into
   the console).
3. The board scans, joins, authenticates and sends the payload automatically.
4. The console shows (see the screenshot):

```text
esp32-ldn-civ7 by sean
CivSwitch 1.0 by Gezine
UDP PAYLOAD CHANNEL :9027
UDP header tpl=1406 js=36 (nak)
UDP header tpl=1406 js=36 (nak)
UDP header tpl=1406 js=36 (nak)
RUNNING INSTALLER (...)
INSTALL DONE - reboot, Load Game
INSTALLER RETURNED
leaving ldn network.
switching to TCP loader :9026
Awaiting payload at <console-ip>:9026
```

5. From here either:
   - keep using the loader (`python3 send_js.py <ip> 9026 payload.js`), or
   - restart the game and pick **Load Game** → the persistent `XSTRIG.Civ7Save`
     starts the loader again.

Each run needs a **fresh game**: the payload replaces the game's UI
(`document.body.innerHTML=''`), so the lobby cannot be reused.

## How it works

```text
scan LDN advertisements (channels 1/6/11)
  → derive advertise_key from prod.keys (AES-ECB + SHA-256)
  → decrypt the advertisement (AES-CTR, SHA-256 verified) → server_random
  → data key (CCMP) = KDF(server_random + Civ VII passphrase)
  → associate to the hidden SSID (no 4-way handshake, keys installed manually)
  → LDN authentication (challenge HMAC-SHA256)
  → IP from the host's advertisement (169.254.x.y)
  → ARP warmup, FireCONN → NetWelcome
  → 20 chat messages (core.js + UDP receiver), 0.2 s apart
  → console evals the payload and binds UDP :9027
  → board streams the installer (template + apply JS) over LDN in one pass
  → console NAKs only the missing chunks; the board resends just those
  → console starts the installer as soon as the last chunk arrives
  → console writes XSTRIG.Civ7Save, commits, then switches to the TCP loader :9026
```

## Layout

```text
esp32-ldn-civ7/
  CMakeLists.txt
  partitions.csv           app 1 MB + 2 MB storage for the installer blobs
  sdkconfig.defaults
  main/
    main.c                 scan/associate/auth/IP, drives civ7 + installer
    civ7.c/.h              Civ VII LDN protocol (transport, FireCONN, NetChat)
    installer.c/.h         streams the installer over UDP :9027
    private_wifi.h         ESP-IDF v6.1 wpa_funcs ABI (no 4-way handshake)
  tools/
    build_and_flash.py     one-click
    make_keys.py           prod.keys -> main/keys.h (gitignored)
    make_payload.py        ../core.js -> main/chat_payload.h (gitignored)
    make_install_blobs.py  installer -> blobs/ (gitignored)
    udp_loader.js          the UDP channel spliced into core.js
  blobs/                   generated
```

## Troubleshooting

| Symptom                              | Cause                                             |
|--------------------------------------|---------------------------------------------------|
| `assoc attempt N did not associate`  | lobby closed / wrong channel; re-create the lobby |
| `LDN authentication failed`          | wrong `prod.keys` or the lobby changed            |
| `no FireRPLY/NetWelcome`             | the console left the lobby; restart the game      |
| `UDP incomplete missT=...`           | the board is re-sending; check `rx=` growth       |
| `binding failed` / `udp bind failed` | port 9027 already in use in the game              |
| Console shows nothing                | the chat XSS did not render; check the lobby chat |
| Board not detected by esptool        | hold BOOT, tap RESET, release BOOT                |

## Notes

- `prod.keys` and everything derived from it (`main/keys.h`) stay offline.
- The installer blob contains the save template from `installer-creator`; it is
  regenerated from the repo, not copied around.
- The board never connects to your Wi-Fi in this firmware; after the run it is
  idle. Reset it for another attempt.

## Credits & license

This firmware ports the local-wireless path from these projects. Their licenses
apply to the ported parts; check them before redistributing a binary:

| Project                                                    | What was used                                          | License      |
|------------------------------------------------------------|--------------------------------------------------------|--------------|
| [CivSwitch](https://github.com/Gezine/CivSwitch)           | payload, save template, installer design               | MIT          |
| [CivSwitchLDN](https://github.com/ItsNerisma/CivSwitchLDN) | LDN/Civ VII protocol flow, constants                   | GPL-3.0-only |
| [Kinnay LDN](https://github.com/kinnay/LDN)                | key derivation, advertisement/auth format              | GPL-3.0      |
| [pokeldn](https://github.com/Decryptu/pokeldn)             | ESP32 `wpa_funcs` patch for handshake-less association | AGPL-3.0     |

`prod.keys` is never part of this repository; delete `main/keys.h`, `blobs/` and
`build/` before sharing a tree that was built on your own console.
