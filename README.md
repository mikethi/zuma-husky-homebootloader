# zuma-husky-homebootloader

DFCONFIG

CONFIG_ARM=y
CONFIG_ARCH_EXYNOS=y              # Tensor G3 is Samsung-derived, not Qualcomm
CONFIG_SYS_TEXT_BASE=0xA0800000   # from bl2.bin — staging area before kernel hand-off
CONFIG_SYS_MALLOC_LEN=0x2000000   # 32 MB heap (same ballpark as SDM845)
CONFIG_SYS_LOAD_ADDR=0x80080000   # arm64 standard TEXT_OFFSET above DRAM base
CONFIG_SYS_BOOTM_LEN=0x4000000
CONFIG_IDENT_STRING=" husky-zuma-ripcurrent"  # from abl.bin string: "ripcurrent-16.4-14540574"
CONFIG_NR_DRAM_BANKS=2

CONFIG_CMD_FASTBOOT=y
CONFIG_USB_GADGET=y
CONFIG_USB_GADGET_VENDOR_NUM=0x18D1   # Google VID — confirmed at abl offset 0x30158
CONFIG_USB_GADGET_PRODUCT_NUM=0x4EE7  # Google fastboot PID — confirmed at 0x88422

CONFIG_ANDROID_BOOT_IMAGE=y
CONFIG_CMD_ABOOTIMG=y
CONFIG_ANDROID_AB=y

CONFIG_MMC_HS400_ES=y
CONFIG_DM_SCSI=y                  # UFS via 13200000.ufs (from fstab.husky)



-----------------------------------------------------------------------------------------------------

#HUSKY.H
#=========


#ifndef __HUSKY_H
#define __HUSKY_H

/* DRAM — confirmed: pbl.bin + bl31.bin both embed these */
#define CONFIG_SYS_SDRAM_BASE    0x80000000UL   /* bank 0 base — in pbl/bl2/bl31 */
#define CONFIG_SYS_SDRAM_SIZE    0x200000000ULL /* 8 GB (husky) */

/* Second DRAM bank — bl31.bin has 0x0000000880000000 as a 64-bit constant */
#define DRAM_BANK1_BASE          0x880000000ULL  /* NOT 0x100000000 like SDM845 */
                                                 /* Tensor G3 maps it at 34 GB  */

/* U-Boot text/stack */
#define CONFIG_SYS_INIT_SP_ADDR  (CONFIG_SYS_TEXT_BASE - 0x10)

/* Kernel / DTB / ramdisk staging — same arm64 convention */
#define KERNEL_LOAD_ADDR         0x80080000      /* text_offset from abl format str */
#define DTB_LOAD_ADDR            0x81000000
#define INITRD_LOAD_ADDR         0x84000000

/* Secure DRAM — abl.bin: "secure dram base 0x%lx, size 0x%zx" */
/* bl2 shows carve-outs up through 0x92800000 before usable DRAM */
#define SECURE_DRAM_BASE         0x88800000      /* from bl2.bin aligned constants */
#define SECURE_DRAM_SIZE         0x09A00000      /* ~154 MB TZ/BL31/GSA reservation */

/* UFS host — from fstab.husky: /dev/block/platform/13200000.ufs */
#define UFS_BASE                 0x13200000

/* USB — VID/PID confirmed in abl.bin binary */
#define USB_VID                  0x18D1          /* Google */
#define USB_PID_FASTBOOT         0x4EE7

/* Boot command */
#define CONFIG_BOOTCOMMAND \
    "abootimg addr $loadaddr; bootm $loadaddr"

#endif /* __HUSKY_H */

-------------------------------------------------------------------------------------------------------



Tools for extracting and inspecting Pixel 8 / 8 Pro (`zuma` / `husky`) bootloader images.

## Repository path

Use an absolute repository path:

```text
/absolute/path/to/zuma-husky-homebootloader
```

## Extract FBPK bootloader partitions

`extract_bootloader.py` expects the input image at:

```text
~/bootloader-husky-ripcurrent-16.4-14540574.img
```

Run with a heredoc command block:

```bash
cat <<'EOF' | bash
REPO_DIR="/absolute/path/to/zuma-husky-homebootloader"
cd "$REPO_DIR"
python3 extract_bootloader.py
EOF
```

Output is written to:

```text
~/bootloader-extract/
```

## Analyze `abl.bin`

Run with a heredoc command block:

```bash
cat <<'EOF' | bash
REPO_DIR="/absolute/path/to/zuma-husky-homebootloader"
cd "$REPO_DIR"
python3 parse_abl.py --abl ~/bootloader-extract/abl.bin
EOF
```
