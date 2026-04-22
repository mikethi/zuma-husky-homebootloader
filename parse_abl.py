#!/usr/bin/env python3
"""
parse_abl.py  –  ABL (Android Bootloader) binary analyser
Pixel "zuma / husky"  –  abl.bin extracted from FBPK v2 image

Usage:
    python3 parse_abl.py [--abl PATH]       # defaults to ./abl.bin

What this script does
─────────────────────
abl.bin is Google's Android Bootloader for the Pixel 8 / 8 Pro (Tensor G3 /
"zuma" / "ripcurrent").  It is the closest equivalent to U-Boot in the Pixel
boot chain:

  Samsung BL1 (bl1.bin)   ≈  U-Boot SPL          – runs from on-chip SRAM
  Google PBL  (pbl.bin)   ≈  U-Boot SPL stage 2  – initialises DRAM
  Google BL2  (bl2.bin)   ≈  U-Boot proper        – SoC/power bring-up
  Google ABL  (abl.bin)   ≈  U-Boot + distro-boot – fastboot, AVB, A/B, kernel launch
  ARM TF BL31 (bl31.bin)  ≈  ARM Trusted Firmware – EL3 runtime (SMC handler)

Like U-Boot, ABL is responsible for:
  • Selecting the active A/B slot
  • Verifying the kernel image (Android Verified Boot / libavb)
  • Building the kernel command line  (androidboot.* params)
  • Entering fastboot / recovery mode when requested
  • Handing off to the Linux kernel via "Starting Linux kernel …"

Unlike U-Boot, ABL is a proprietary LK (Little Kernel) derivative, compiled
for AArch64, and communicates with the TrustZone/GSA secure world via Trusty
IPC rather than a generic PSCI/SMC layer.

The binary is NOT a plain ELF – it appears to be a signed / packed flat image
(the first ~0x60 bytes are a signature / hash header, followed by a large
block of ARM64 machine code, and a dense ASCII string section starting around
offset 0x110000 which is what we mine here).

Output sections
───────────────
  1. Boot modes & reboot reasons  – strings that drive flow control
  2. Fastboot protocol            – FAIL/INFO/OKAY prefixes + OEM commands
  3. A/B slot handling            – slot selection / fallback logic
  4. Verified Boot (AVB)          – libavb integration & error paths
  5. Kernel cmdline               – every  androidboot.*  param injected
  6. Hardware / device identity   – product name, SoC, serial, build tag
  7. Source-file paths            – embedded assert paths expose code layout
  8. Interesting addresses        – load addresses, DRAM regions, heap refs
"""

import argparse
import re
import struct
import sys
from pathlib import Path

# ── tunables ─────────────────────────────────────────────────────────────────

DEFAULT_ABL   = Path(__file__).parent / "abl.bin"
MIN_STR_LEN   = 8          # minimum printable-ASCII run to call a "string"

# The dense ASCII region starts here; scanning only this window is ~100× faster
# than scanning the whole 1.8 MB binary and avoids false positives in ARM code.
STRINGS_START = 0x10E000
STRINGS_END   = 0x145000

# ── helpers ──────────────────────────────────────────────────────────────────

def extract_strings(data: bytes, start: int, end: int, min_len: int = MIN_STR_LEN):
    """Yield (offset, text) for every printable-ASCII run >= min_len in [start, end)."""
    window = data[start:end]
    for m in re.finditer(rb'[\x20-\x7e]{' + str(min_len).encode() + rb',}', window):
        yield start + m.start(), m.group().decode("ascii", errors="replace")


def section(title: str, items: list[tuple[int, str]], *, show_offsets: bool = True) -> None:
    print(f"\n{'─'*78}")
    print(f"  {title}")
    print(f"{'─'*78}")
    if not items:
        print("  (none found)")
        return
    for off, s in items:
        if show_offsets:
            print(f"  {off:#010x}  {s}")
        else:
            print(f"  {s}")


def matches(text: str, keywords: list[str]) -> bool:
    low = text.lower()
    return any(kw.lower() in low for kw in keywords)

# ── main ─────────────────────────────────────────────────────────────────────

def main() -> None:
    ap = argparse.ArgumentParser(description="Analyse abl.bin internals")
    ap.add_argument("--abl", type=Path, default=DEFAULT_ABL, metavar="PATH",
                    help=f"Path to abl.bin  (default: {DEFAULT_ABL})")
    ap.add_argument("--no-offsets", action="store_true",
                    help="Omit hex offsets from output")
    args = ap.parse_args()

    if not args.abl.exists():
        print(f"[ERROR] {args.abl} not found.  "
              f"Run extract_bootloader.py first.", file=sys.stderr)
        sys.exit(1)

    data = args.abl.read_bytes()
    size = len(data)
    print(f"[+] Loaded {args.abl}  ({size:#x}  {size:,} bytes)")

    # Detect the ASCII-rich zone automatically if defaults are wrong for a
    # different build by scanning 64 kB chunks for string density > 30 %.
    auto_start, auto_end = _find_string_zone(data)
    if auto_start != STRINGS_START:
        print(f"[!] Auto-detected string zone: {auto_start:#x} – {auto_end:#x}")
    s_start = auto_start
    s_end   = auto_end

    print(f"[+] Scanning string zone  {s_start:#x} – {s_end:#x}")
    all_strings = list(extract_strings(data, s_start, s_end))
    print(f"[+] Found {len(all_strings)} strings (>= {MIN_STR_LEN} chars)\n")

    show = not args.no_offsets

    # ── 1. Boot modes & reboot reasons ──────────────────────────────────────
    boot_kw = [
        "reboot,", "bootmode", "boot mode", "Fastboot Mode", "Recovery Mode",
        "FastBoot Mode", "Fastboot mode", "FastBoot mode",
        "boot-cmd", "avf_boot_mode", "force_normal_boot",
    ]
    section("1. BOOT MODES & REBOOT REASONS",
            [(o, s) for o, s in all_strings if matches(s, boot_kw)],
            show_offsets=show)

    # ── 2. Fastboot protocol ─────────────────────────────────────────────────
    fb_kw = [
        "FAIL", "INFO", "OKAY", "DATA",          # fastboot protocol prefixes
        "fastboot", "oem ", "boot-fastboot",
        "slot-fastboot", "force-fastboot",
        "version-bootloader", "version-baseband",
    ]
    section("2. FASTBOOT PROTOCOL (FAIL/INFO/OEM/…)",
            [(o, s) for o, s in all_strings if matches(s, fb_kw)],
            show_offsets=show)

    # ── 3. A/B slot handling ─────────────────────────────────────────────────
    ab_kw = [
        "slot_a", "slot_b", "active slot", "inactive slot",
        "boot_a", "boot_b", "slot suffix", "androidboot.slot",
        "slot-unbootable", "slot-fastboot-ok",
        "could not get slot", "switch slot",
        "decrement", "boot retry", "fastboot_ab",
    ]
    section("3. A/B SLOT HANDLING",
            [(o, s) for o, s in all_strings if matches(s, ab_kw)],
            show_offsets=show)

    # ── 4. Verified Boot / AVB ───────────────────────────────────────────────
    avb_kw = [
        "avb_", "AVB_", "vbmeta", "verified boot", "verifiedbootstate",
        "veritymode", "dm-verity", "avb_slot_verify", "libavb",
        "avb_menu_delay", "AVBf", "vbmeta_vendor", "vbmeta_system",
    ]
    section("4. VERIFIED BOOT / AVB",
            [(o, s) for o, s in all_strings if matches(s, avb_kw)],
            show_offsets=show)

    # ── 5. Kernel cmdline / androidboot.* params ─────────────────────────────
    cmd_kw = [
        "androidboot.", "bootargs", "kcmdline",
        "cmdline(full)", "Starting Linux",
    ]
    section("5. KERNEL CMDLINE / androidboot.* PARAMS",
            [(o, s) for o, s in all_strings if matches(s, cmd_kw)],
            show_offsets=show)

    # ── 6. Hardware / device identity ────────────────────────────────────────
    hw_kw = [
        "Pixel", "pixel", "husky", "zuma", "ripcurrent", "Ripcurrent",
        "Tensor", "gs401", "gs301", "gs201",
        "Serial number", "serial number", "Error getting serial",
        "ro.product", "device_info", "device_state", "model:",
        "LK build", "version-bootloader",
    ]
    section("6. HARDWARE / DEVICE IDENTITY",
            [(o, s) for o, s in all_strings if matches(s, hw_kw)],
            show_offsets=show)

    # ── 7. Embedded source-file paths ────────────────────────────────────────
    src_kw = [".c", ".h", "/lib/", "/include/", "lk/", "android/"]
    src = [(o, s) for o, s in all_strings
           if (s.endswith(".c") or s.endswith(".h")
               or any(k in s for k in ["/lib/", "lk/arch", "lk/dev", "lk/top"]))]
    section("7. EMBEDDED SOURCE-FILE PATHS  (reveals code layout)",
            src, show_offsets=show)

    # ── 8. Load addresses / memory regions ───────────────────────────────────
    mem_kw = [
        "text_offset", "load addr", "base addr", "entry point",
        "kernel heap", "secure dram", "bl31_dram", "sec_dram",
        "heap_grow", "mem_base", "kernel allocation",
        "physical address", "PT base address",
    ]
    section("8. LOAD ADDRESSES / MEMORY REGIONS",
            [(o, s) for o, s in all_strings if matches(s, mem_kw)],
            show_offsets=show)

    print(f"\n{'─'*78}")
    print("  DONE")
    print(f"{'─'*78}\n")


def _find_string_zone(data: bytes, chunk: int = 0x10000,
                       threshold: float = 0.30) -> tuple[int, int]:
    """Return (start, end) of the largest contiguous zone whose bytes that belong
    to printable-ASCII *strings* (runs of >= 8 consecutive printable chars)
    make up > threshold fraction of the block.  This avoids false positives in
    ARM64 machine-code sections where individual bytes happen to be in the
    printable range but do not form long runs."""
    best_start, best_end, cur_start = 0, 0, None
    _pat = re.compile(rb'[\x20-\x7e]{8,}')
    for off in range(0, len(data), chunk):
        block = data[off:off + chunk]
        string_bytes = sum(len(m.group()) for m in _pat.finditer(block))
        density = string_bytes / len(block)
        if density >= threshold:
            if cur_start is None:
                cur_start = off
            if off + chunk - cur_start > best_end - best_start:
                best_start, best_end = cur_start, off + chunk
        else:
            cur_start = None
    # Fall back to known defaults if auto-detection missed
    if best_end == 0:
        return STRINGS_START, STRINGS_END
    return best_start, min(best_end, len(data))


if __name__ == "__main__":
    main()
