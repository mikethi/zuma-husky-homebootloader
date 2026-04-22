#!/usr/bin/env python3
"""
FBPK v2 bootloader image extractor
Pixel "zuma / husky" – no root required

Usage:
    Place bootloader-husky-ripcurrent-16.4-14540574.img in your home directory (~)
    then run:  python3 extract_bootloader.py

Output folder:  ~/bootloader-extract/
Algorithm doc:  ~/bootloader-extract/ALGORITHM.txt
"""

import shutil
import struct
import sys
from pathlib import Path

# ── constants ────────────────────────────────────────────────────────────────
IMAGE_NAME   = "bootloader-husky-ripcurrent-16.4-14540574.img"
OUT_DIR_NAME = "bootloader-extract"

FBPK_MAGIC        = b"FBPK"
FBPK_HEADER_SIZE  = 0x68          # 104 bytes – main header
FBPK_ENTRY_SIZE   = 0x68          # 104 bytes – each entry record
ENTRY_NAME_OFFSET = 0x0C          # byte offset of name inside an entry
ENTRY_NAME_LEN    = 0x4C          # max name length (up to +0x58)
ENTRY_DOFF_OFFSET = 0x58          # uint64 LE – payload offset in file
ENTRY_DSIZ_OFFSET = 0x60          # uint64 LE – payload size in bytes
ENTRY_TYPE_OFFSET = 0x08          # uint32 LE – entry type
VALID_ENTRY_TYPES = {1, 2}

ALGORITHM_TEXT = """\
╔══════════════════════════════════════════════════════════════════════════════╗
║         FBPK v2  –  Pixel bootloader container  –  parse / extract          ║
╠══════════════════════════════════════════════════════════════════════════════╣
║                                                                              ║
║  CONTAINER HEADER  (0x68 bytes, offset 0x00)                                 ║
║  ┌──────────┬──────┬──────────────────────────────────────────────────────┐  ║
║  │ offset   │ size │ field                                                │  ║
║  ├──────────┼──────┼──────────────────────────────────────────────────────┤  ║
║  │ 0x00     │  4   │ magic        – ASCII "FBPK"                          │  ║
║  │ 0x04     │  4   │ version      – uint32 LE  (2 for this image)         │  ║
║  │ 0x08     │  4   │ entry_count  – uint32 LE  (112 for this image)       │  ║
║  │ 0x0C     │  4   │ (reserved / file-size hint)                          │  ║
║  │ 0x10     │ 16   │ platform     – null-padded ASCII  ("zuma")           │  ║
║  │ 0x20     │ 32   │ build_id     – null-padded ASCII  ("ripcurrent-…")   │  ║
║  │ 0x40     │ 40   │ (reserved zeros)                                     │  ║
║  └──────────┴──────┴──────────────────────────────────────────────────────┘  ║
║                                                                              ║
║  ENTRY TABLE  (entry_count × 0x68 bytes, starting at offset 0x68)           ║
║  Each entry record is 0x68 bytes:                                            ║
║  ┌──────────┬──────┬──────────────────────────────────────────────────────┐  ║
║  │ +0x00    │  4   │ flags / index  (uint32 LE)                           │  ║
║  │ +0x04    │  4   │ extra field    (uint32 LE, 0 in most entries)        │  ║
║  │ +0x08    │  4   │ type           (uint32 LE:                           │  ║
║  │          │      │   0 = raw / partition-table block                   │  ║
║  │          │      │   1 = firmware blob (ELF / flat binary)             │  ║
║  │          │      │   2 = UFS firmware update package)                  │  ║
║  │ +0x0C    │ 76   │ name           (null-terminated ASCII string)        │  ║
║  │ +0x58    │  8   │ data_offset    (uint64 LE – byte offset in file)     │  ║
║  │ +0x60    │  8   │ data_size      (uint64 LE – payload length in bytes) │  ║
║  └──────────┴──────┴──────────────────────────────────────────────────────┘  ║
║                                                                              ║
║  EXTRACTION ALGORITHM                                                        ║
║  1. Read 4-byte magic at offset 0 → must be "FBPK".                         ║
║  2. Read entry_count (uint32 LE) at offset 0x08.                            ║
║  3. Read platform (bytes 0x10-0x1F) and build_id (bytes 0x20-0x3F).         ║
║  4. For each entry i  in  range(entry_count):                                ║
║       a. entry_base = 0x68  +  i × 0x68                                     ║
║       b. name       = entry_base + 0x0C  (null-terminated string)           ║
║       c. data_offset= uint64 LE at entry_base + 0x58                        ║
║       d. data_size  = uint64 LE at entry_base + 0x60                        ║
║       e. if data_size > 0 and data_offset > 0:                              ║
║              output_file = <name>.bin                                        ║
║              write file[data_offset : data_offset + data_size]              ║
║                                                                              ║
║  PARTITION MAP (this specific build)                                         ║
║   ufs           – UFS device descriptor / partition-table metadata          ║
║   partition:0‒3 – raw GPT partition-table blocks (one per UFS namespace)    ║
║   bl1 / bl1_a/b – Boot ROM second-stage loader  (Samsung BL1)               ║
║   pbl / pbl_a/b – Primary Boot Loader                                        ║
║   bl2 / bl2_a/b – Secondary Boot Loader                                      ║
║   abl / abl_a/b – Android Bootloader  (fastboot / recovery entry)           ║
║   bl31          – ARM Trusted Firmware BL31  (EL3 runtime firmware)         ║
║   tzsw          – TrustZone secure-world image                               ║
║   gsa           – Google Security chip Application firmware                  ║
║   gsa_bl1       – GSA first-stage loader                                     ║
║   ldfw          – Late-dispatch firmware                                     ║
║   gcf / gcf_a/b – Google Compute Firmware                                    ║
║   ufsfwupdate   – UFS firmware update payload                                ║
║   dpm_a/b       – Dynamic Power Manager                                      ║
║   dram_train    – DRAM training blob                                         ║
║   blenv         – Bootloader environment / variables partition               ║
║   vbmeta_*      – Android Verified Boot metadata (AVB)                      ║
║   boot_a/b      – Android boot partition placeholder                         ║
║   (and more A/B slot mirrors of the above)                                   ║
╚══════════════════════════════════════════════════════════════════════════════╝
"""

# ── helpers ──────────────────────────────────────────────────────────────────

def die(msg: str) -> None:
    print(f"[ERROR] {msg}", file=sys.stderr)
    sys.exit(1)


def parse_cstr(buf: bytes, offset: int, max_len: int) -> str:
    raw = buf[offset:offset + max_len]
    return raw.split(b"\x00")[0].decode("ascii", errors="replace")


def is_plausible_name(name: str) -> bool:
    if not name:
        return False
    allowed = set("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789:_-.")
    return all(ch in allowed for ch in name)


# ── main ─────────────────────────────────────────────────────────────────────

def main() -> None:
    home = Path.home()

    # 1. Locate image in ~
    src = home / IMAGE_NAME
    if not src.exists():
        die(
            f"{src} not found.\n"
            f"       Place {IMAGE_NAME} in your home directory and re-run."
        )

    # 2. Create output directory
    out_dir = home / OUT_DIR_NAME
    out_dir.mkdir(parents=True, exist_ok=True)
    print(f"[+] Output directory : {out_dir}")

    # 3. Copy image into work directory (leaves original intact)
    work_img = out_dir / IMAGE_NAME
    if not work_img.exists():
        print(f"[+] Copying image    : {src} → {work_img}")
        shutil.copy2(src, work_img)
    else:
        print(f"[+] Image already present in {out_dir}")

    # 4. Read image
    data = work_img.read_bytes()
    file_size = len(data)
    print(f"[+] Image size       : {file_size:#x}  ({file_size:,} bytes)")

    # 5. Validate FBPK magic
    if data[:4] != FBPK_MAGIC:
        die(f"Bad magic {data[:4]!r} – expected b'FBPK'")

    version, entry_count = struct.unpack_from("<II", data, 0x04)
    platform = parse_cstr(data, 0x10, 16)
    build_id = parse_cstr(data, 0x20, 32)

    print(f"[+] FBPK version     : {version}")
    print(f"[+] Platform         : {platform}")
    print(f"[+] Build            : {build_id}")
    print(f"[+] Entry count      : {entry_count}")

    # 6. Parse entries and extract payloads
    extracted = 0
    skipped   = 0
    seen_names: dict[str, int] = {}

    for i in range(entry_count):
        base = FBPK_HEADER_SIZE + i * FBPK_ENTRY_SIZE
        if base + FBPK_ENTRY_SIZE > file_size:
            print(f"[!] Entry {i} out of bounds – truncated image?")
            break

        entry_type = struct.unpack_from("<I", data, base + ENTRY_TYPE_OFFSET)[0]
        name = parse_cstr(data, base + ENTRY_NAME_OFFSET, ENTRY_NAME_LEN)
        data_offset, data_size = struct.unpack_from("<QQ", data, base + ENTRY_DOFF_OFFSET)

        if (
            entry_type not in VALID_ENTRY_TYPES
            and not name
            and data_offset == 0
            and data_size == 0
        ):
            break

        if (
            entry_type not in VALID_ENTRY_TYPES
            or not is_plausible_name(name)
            or data_size == 0
            or data_offset == 0
        ):
            skipped += 1
            continue

        if data_offset + data_size > file_size:
            print(f"[!] Entry '{name}' claims offset {data_offset:#x}+{data_size:#x}"
                  f" exceeds file size – skipping")
            skipped += 1
            continue

        # Handle duplicate names (e.g. "ufs" appears twice)
        count = seen_names.get(name, 0)
        seen_names[name] = count + 1
        out_name = f"{name}.bin" if count == 0 else f"{name}_{count}.bin"
        out_path = out_dir / out_name

        payload = data[data_offset:data_offset + data_size]
        out_path.write_bytes(payload)
        print(f"  [{i:3d}] {name:<24s}  offset={data_offset:#010x}  size={data_size:#010x}  → {out_name}")
        extracted += 1

    # 7. Write algorithm documentation
    algo_path = out_dir / "ALGORITHM.txt"
    algo_path.write_text(ALGORITHM_TEXT, encoding="utf-8")
    print(f"\n[+] Algorithm doc    : {algo_path}")
    print(f"[+] Extracted        : {extracted} partitions  ({skipped} skipped)")
    print(f"[+] Done – all files in {out_dir}")


if __name__ == "__main__":
    main()
