"""
Stream-merge multiple XMLTV files into one gzip without loading everything at once.
Keeps a channel-id set in memory only (small).
"""
from __future__ import annotations

import gzip
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent
IN_DIR = ROOT / "iptv-org-work" / "site_guides"
OUT_XML = ROOT / "iptv-org-work" / "us-guide.xml"
OUT_GZ = ROOT / "iptv-org-work" / "us-guide.xml.gz"

CHANNEL_RE = re.compile(rb"<channel\b.*?</channel>", re.DOTALL)
PROG_RE = re.compile(rb"<programme\b.*?</programme>", re.DOTALL)
ID_RE = re.compile(rb'\bid="([^"]+)"')
CH_ATTR_RE = re.compile(rb'\bchannel="([^"]+)"')


def main() -> None:
    # Prefer gzip outputs only to avoid double-counting xml+gz pairs
    gz_files = sorted(IN_DIR.glob("*.xml.gz"))
    xml_files = sorted(IN_DIR.glob("*.xml"))
    files = gz_files if gz_files else xml_files
    if not files:
        raise SystemExit(f"No guides in {IN_DIR}")

    seen_channels: set[bytes] = set()
    channel_count = 0
    programme_count = 0

    with OUT_XML.open("wb") as out:
        out.write(b"<?xml version=\"1.0\" encoding=\"UTF-8\"?>\n")
        out.write(b'<tv generator-info-name="iptv-org-epg-batched">\n')

        # Pass 1: channels
        for path in files:
            print(f"channels from {path.name}", flush=True)
            raw = path.read_bytes()
            if path.suffix == ".gz" or raw[:2] == b"\x1f\x8b":
                raw = gzip.decompress(raw)
            for block in CHANNEL_RE.findall(raw):
                m = ID_RE.search(block)
                if not m:
                    continue
                cid = m.group(1)
                if cid in seen_channels:
                    continue
                seen_channels.add(cid)
                out.write(block)
                out.write(b"\n")
                channel_count += 1
            del raw

        # Pass 2: programmes (only for known channels)
        for path in files:
            print(f"programmes from {path.name}", flush=True)
            raw = path.read_bytes()
            if path.suffix == ".gz" or raw[:2] == b"\x1f\x8b":
                raw = gzip.decompress(raw)
            for block in PROG_RE.findall(raw):
                m = CH_ATTR_RE.search(block)
                if not m or m.group(1) not in seen_channels:
                    continue
                out.write(block)
                out.write(b"\n")
                programme_count += 1
            del raw

        out.write(b"</tv>\n")

    print(f"Writing gzip {OUT_GZ}", flush=True)
    with OUT_XML.open("rb") as src, gzip.open(OUT_GZ, "wb", compresslevel=6) as dst:
        while True:
            chunk = src.read(1024 * 1024)
            if not chunk:
                break
            dst.write(chunk)

    print(f"Done channels={channel_count} programmes={programme_count}", flush=True)
    print(f"XML={OUT_XML.stat().st_size} GZ={OUT_GZ.stat().st_size}", flush=True)


if __name__ == "__main__":
    main()
