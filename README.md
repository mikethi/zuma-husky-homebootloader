# zuma-husky-homebootloader

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
