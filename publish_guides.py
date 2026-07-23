"""
Merge site guides and publish to epgs/.
If compressed size exceeds MAX_GZ_BYTES, split into multiple part files.
"""
from __future__ import annotations

import gzip
import re
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parent
IN_DIR = ROOT / "iptv-org-work" / "site_guides"
EPGS = ROOT / "epgs"
WORK = ROOT / "iptv-org-work"

# Keep under GitHub soft limit with room to spare
MAX_GZ_BYTES = 40 * 1024 * 1024

CHANNEL_RE = re.compile(rb"<channel\b.*?</channel>", re.DOTALL)
PROG_RE = re.compile(rb"<programme\b.*?</programme>", re.DOTALL)
ID_RE = re.compile(rb'\bid="([^"]+)"')
CH_ATTR_RE = re.compile(rb'\bchannel="([^"]+)"')


def load_gz(path: Path) -> bytes:
    raw = path.read_bytes()
    if path.suffix == ".gz" or raw[:2] == b"\x1f\x8b":
        return gzip.decompress(raw)
    return raw


def write_guide(channels: list[bytes], programmes: list[bytes], out_gz: Path) -> tuple[int, int, int]:
    tmp = out_gz.with_suffix(".xml")
    with tmp.open("wb") as out:
        out.write(b'<?xml version="1.0" encoding="UTF-8"?>\n')
        out.write(b'<tv generator-info-name="iptv-org-epg-github">\n')
        for block in channels:
            out.write(block)
            out.write(b"\n")
        for block in programmes:
            out.write(block)
            out.write(b"\n")
        out.write(b"</tv>\n")
    with tmp.open("rb") as src, gzip.open(out_gz, "wb", compresslevel=6) as dst:
        shutil.copyfileobj(src, dst, length=1024 * 1024)
    size = out_gz.stat().st_size
    tmp.unlink(missing_ok=True)
    return len(channels), len(programmes), size


def collect_from_files(files: list[Path]):
    seen: set[bytes] = set()
    channels: list[bytes] = []
    programmes: list[bytes] = []
    for path in files:
        print(f"load {path.name}", flush=True)
        raw = load_gz(path)
        for block in CHANNEL_RE.findall(raw):
            m = ID_RE.search(block)
            if not m:
                continue
            cid = m.group(1)
            if cid in seen:
                continue
            seen.add(cid)
            channels.append(block)
        for block in PROG_RE.findall(raw):
            m = CH_ATTR_RE.search(block)
            if not m or m.group(1) not in seen:
                continue
            programmes.append(block)
        del raw
    return channels, programmes


def main() -> None:
    EPGS.mkdir(exist_ok=True)
    WORK.mkdir(exist_ok=True)

    # Remove old generated iptvorg parts
    for old in EPGS.glob("us-iptvorg-guide*.xml.gz"):
        old.unlink()

    files = sorted(IN_DIR.glob("*.xml.gz"))
    if not files:
        raise SystemExit(f"No site guides in {IN_DIR}")

    # Try single file first
    channels, programmes = collect_from_files(files)
    out = EPGS / "us-iptvorg-guide.xml.gz"
    c, p, size = write_guide(channels, programmes, out)
    print(f"single file: channels={c} programmes={p} size={size}", flush=True)

    if size <= MAX_GZ_BYTES:
        print(f"OK under limit ({MAX_GZ_BYTES} bytes): {out}", flush=True)
        return

    print(f"Size {size} exceeds {MAX_GZ_BYTES}; splitting by site packs...", flush=True)
    out.unlink(missing_ok=True)

    # Split into packs of sites until each gz <= limit
    packs: list[list[Path]] = []
    current: list[Path] = []
    for path in files:
        trial = current + [path]
        ch, pr = collect_from_files(trial)
        tmp = WORK / "_split_trial.xml.gz"
        _, _, sz = write_guide(ch, pr, tmp)
        if current and sz > MAX_GZ_BYTES:
            packs.append(current)
            current = [path]
        else:
            current = trial
        tmp.unlink(missing_ok=True)
    if current:
        packs.append(current)

    for i, pack in enumerate(packs, start=1):
        ch, pr = collect_from_files(pack)
        part = EPGS / f"us-iptvorg-guide-{i:02d}.xml.gz"
        c, p, size = write_guide(ch, pr, part)
        print(f"part {i}: files={[x.name for x in pack]} channels={c} programmes={p} size={size}", flush=True)
        if size > MAX_GZ_BYTES:
            print(f"WARNING: part {i} still large ({size}); consider fewer sites/days", flush=True)

    print(f"Wrote {len(packs)} split guide file(s)", flush=True)


if __name__ == "__main__":
    main()
