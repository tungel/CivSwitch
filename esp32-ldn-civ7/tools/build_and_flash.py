#!/usr/bin/env python3
"""One-click build (and optional flash) for esp32-ldn-civ7.

  python3 tools/build_and_flash.py --keys prod.keys --port /dev/cu.usbmodemXXXX --flash

Steps:
  1. main/keys.h        from prod.keys        (make_keys.py)
  2. main/chat_payload.h from ../core.js       (make_payload.py)
  3. blobs/*.bin        from installer-creator (make_install_blobs.py)
  4. idf.py build
  5. esptool write-flash (bootloader, partition table, app, template, apply JS)

Requires the ESP-IDF environment to be sourced (`. $IDF_PATH/export.sh`) and node.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
CIV = os.path.dirname(ROOT)
BLOBS = os.path.join(ROOT, "blobs")

APP_OFF = 0x10000
TPL_OFF = 0x110000
APPLY_OFF = 0x290000

# espressif/idf ships the IDF release of the same name with all toolchains and the python env
# baked in; its entrypoint activates them, so a bare `idf.py` works. Node is not in the image,
# which is why the asset steps above always run on the host.
IDF_IMAGE = os.environ.get("CIVSWITCH_IDF_IMAGE", "espressif/idf:v6.1")

# S2 boots its bootloader at 0x1000 (S3 at 0x0) and ships 4 MB modules; the partition map above
# ends at 0x310000, so both targets share partitions.csv and the blob offsets.
TARGETS = {
    "esp32s3": {"chip": "esp32s3", "build": "build", "boot_off": "0x0", "flash_size": "16MB",
                "defaults": None},
    "esp32s2": {"chip": "esp32s2", "build": "build-esp32s2", "boot_off": "0x1000", "flash_size": "4MB",
                "defaults": "sdkconfig.defaults.esp32s2"},
}


def run(cmd, **kw):
    print("+", " ".join(cmd), flush=True)
    return subprocess.run(cmd, check=True, **kw)


def idf_prefix(target):
    """Command prefix that makes idf.py runnable, or None if there is no way to reach it.

    Sourcing export.sh is the documented setup, but running this script without it is the common
    mistake: fall back to sourcing it for the build, from $CIVSWITCH_IDF_ENV, $IDF_PATH, or the
    install recorded in ~/.espressif/idf-env.json. A candidate only counts if idf.py resolves
    afterwards, so a broken export.sh is reported instead of swallowed.
    """
    if shutil.which("idf.py"):
        return []
    probe = 'src="$1"; shift; . "$src" >/dev/null 2>&1; command -v idf.py >/dev/null'
    cands = [os.environ.get("CIVSWITCH_IDF_ENV", ""),
             os.path.join(os.environ.get("IDF_PATH", ""), "export.sh"),
             os.path.join(_installed_idf() or "", "export.sh")]
    seen, uniq = set(), []
    for c in cands:
        r = os.path.realpath(c) if c else ""
        if r and r not in seen and os.path.exists(r):
            seen.add(r)
            uniq.append(c)
    err = ""
    for src in uniq:
        r = subprocess.run(["bash", "-c", probe, "probe", src], capture_output=True, text=True)
        if r.returncode == 0:
            print("idf.py not on PATH; sourcing", src)
            return ["bash", "-c", 'src="$1"; shift; . "$src" >/dev/null 2>&1 || exit 3; exec "$@"',
                    "idf-env", src]
        err = subprocess.run(["bash", "-c", '. "%s"' % src], capture_output=True, text=True).stderr
        print("W: %s did not put idf.py on PATH" % src, file=sys.stderr)
        if re.search(r"virtual environment|install script|no installed versions", err, re.I):
            # tools were never installed for this python: say exactly what fixes it
            print("   fix: (cd %s && ./install.sh %s), then rerun this command"
                  % (os.path.dirname(src), target), file=sys.stderr)
    if err.strip():
        print(err.strip()[-600:], file=sys.stderr)
    return None


def docker_prefix(image, port):
    """Command prefix that runs one command in the IDF container, or None.

    The repo is mounted at the same path so the absolute paths passed to idf.py and esptool are
    valid inside the container; HOME=/tmp because -u makes the container run as the host user.
    """
    if not shutil.which("docker"):
        print("E: --docker needs docker on PATH", file=sys.stderr)
        return None
    pre = ["docker", "run", "--rm", "-i", "-v", ROOT + ":" + ROOT, "-w", ROOT,
           "-u", "%d:%d" % (os.getuid(), os.getgid()), "-e", "HOME=/tmp",
           "-e", "IDF_GIT_SAFE_DIR=*"]
    if port and os.path.exists(port):
        pre += ["--device", port, "--group-add", str(os.stat(port).st_gid)]
    return pre + [image]


def _installed_idf():
    """IDF checkout recorded by install.sh, newest entry wins."""
    try:
        with open(os.path.expanduser("~/.espressif/idf-env.json"), encoding="utf-8") as f:
            inst = json.load(f).get("idfInstalled", {})
        for entry in reversed(list(inst.values())):
            p = entry.get("path", "")
            if os.path.exists(os.path.join(p, "export.sh")):
                return p
    except (OSError, ValueError):
        pass
    return None


def esptool_launcher(py, prefix):
    """Command prefix for esptool, or None if this environment has none.

    In container mode there is nothing to probe: the IDF image puts esptool on PATH, and a host
    interpreter path must never be tried inside it (/usr/bin/python3 exists there but has no
    esptool, so probing it silently resolves to a python that cannot flash).
    """
    if prefix[:1] in (["docker"], ["podman"]):
        return ["esptool"]
    cands = ([py] if py != sys.executable else []) + [sys.executable, "python3"]
    for cand in cands:
        if subprocess.run(prefix + [cand, "-m", "esptool", "--version"],
                          capture_output=True).returncode == 0:
            return [cand, "-m", "esptool"]
    exe = shutil.which("esptool")
    return [exe] if exe else [sys.executable, "-m", "esptool"]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--keys", default=os.environ.get("CIVSWITCH_KEYS", os.path.join(ROOT, "prod.keys")),
                    help="path to prod.keys (required unless main/keys.h exists)")
    ap.add_argument("--core", default=os.environ.get("CIVSWITCH_CORE", os.path.join(CIV, "core.js")),
                    help="shared CivSwitch core.js")
    ap.add_argument("--port", default=os.environ.get("ESPPORT", ""),
                    help="serial port for flashing, e.g. /dev/cu.usbmodemXXXX")
    ap.add_argument("--target", default="esp32s3", choices=sorted(TARGETS),
                    help="board target (esp32s2 = S2 Mini, native-USB console)")
    ap.add_argument("--flash", action="store_true", help="flash after building")
    ap.add_argument("--erase", action="store_true", help="erase the whole flash first")
    ap.add_argument("--installer-dir", default=os.environ.get("CIVSWITCH_INSTALLER_DIR", ""),
                    help="installer-creator override (BLOCK, STAGER, save_template, compress_stage),"
                         " e.g. ../CivSwitchLDN/installer for assets identical to that launcher")
    ap.add_argument("--no-build", action="store_true", help="skip idf.py build")
    ap.add_argument("--docker", nargs="?", const="", default=None, metavar="IMAGE",
                    help="run idf.py and esptool in a container (default %s); the assets still "
                         "build on the host because node is not in the image" % IDF_IMAGE)
    args = ap.parse_args()
    tgt = TARGETS[args.target]
    # a container build gets its own dir: the CMakeCache of a host build names host toolchain paths
    build = os.path.join(ROOT, tgt["build"] + ("-docker" if args.docker is not None else ""))

    idf = None
    if args.docker is not None:
        if args.no_build:
            print("E: --docker and --no-build contradict each other", file=sys.stderr)
            return 2
        idf = docker_prefix(args.docker or IDF_IMAGE, args.port)
        if idf is None:
            return 2
    elif not args.no_build:
        idf = idf_prefix(args.target)
        if idf is None:
            print("E: cannot run idf.py. Source the ESP-IDF environment first, e.g.\n"
                  "     . $IDF_PATH/export.sh\n"
                  "   or point CIVSWITCH_IDF_ENV / IDF_PATH at a working install, or pass --no-build.",
                  file=sys.stderr)
            return 2

    py = sys.executable
    keys_h = os.path.join(ROOT, "main", "keys.h")
    if os.path.exists(args.keys):
        run([py, os.path.join(HERE, "make_keys.py"), args.keys])
    elif os.path.exists(keys_h):
        print("using existing main/keys.h")
    else:
        print("E: no prod.keys found (pass --keys)", file=sys.stderr)
        return 1

    run([py, os.path.join(HERE, "make_payload.py"), args.core])
    blobs = [py, os.path.join(HERE, "make_install_blobs.py"), args.core, os.path.join(ROOT, "blobs")]
    if args.installer_dir:
        blobs.append(args.installer_dir)
    run(blobs)

    if not args.no_build:
        cmd = idf + ["idf.py", "-B", build]
        if tgt["defaults"]:
            cmd += ["-DSDKCONFIG=" + os.path.join(build, "sdkconfig"),
                    "-DSDKCONFIG_DEFAULTS=" + tgt["defaults"]]
        if not os.path.exists(os.path.join(build, "sdkconfig")):
            run(cmd + ["set-target", args.target], cwd=ROOT)
        run(cmd + ["build"], cwd=ROOT)

    if not args.flash:
        print("build only; pass --flash --port PORT to flash")
        return 0

    if not args.port:
        print("E: --port is required with --flash", file=sys.stderr)
        return 1

    launcher = esptool_launcher(py, idf or [])
    if launcher is None:
        return 2
    esp = (idf or []) + launcher
    common = ["--chip", tgt["chip"], "-p", args.port, "-b", "460800",
              "--before", "default-reset", "--after", "hard-reset"]
    if args.erase:
        run(esp + common + ["erase-flash"])
    run(esp + common + ["write-flash", "--flash-mode", "dio", "--flash-freq", "80m",
                   "--flash-size", tgt["flash_size"],
                   tgt["boot_off"], os.path.join(build, "bootloader", "bootloader.bin"),
                   "0x8000", os.path.join(build, "partition_table", "partition-table.bin"),
                   hex(APP_OFF), os.path.join(build, "esp32-ldn-civ7.bin"),
                   hex(TPL_OFF), os.path.join(BLOBS, "blob_tpl.bin"),
                   hex(APPLY_OFF), os.path.join(BLOBS, "blob_apply.bin")])
    print("flashed. Press RESET on the board, then create the wireless lobby.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
