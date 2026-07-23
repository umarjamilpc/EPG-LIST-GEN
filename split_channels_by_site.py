"""Split us.channels.xml into per-site files for low-memory batched grabs."""
from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SRC = ROOT / "iptv-org-work" / "us.channels.xml"
OUT = ROOT / "iptv-org-work" / "by_site"
OUT.mkdir(parents=True, exist_ok=True)

ATTR_RE = re.compile(r"<channel\b(?P<attrs>[^>]*)>(?P<body>.*?)</channel>", re.DOTALL)


def main() -> None:
    text = SRC.read_text(encoding="utf-8")
    buckets: dict[str, list[str]] = {}
    for m in ATTR_RE.finditer(text):
        attrs = dict(re.findall(r'(\w+)="([^"]*)"', m.group("attrs")))
        site = attrs.get("site", "unknown")
        buckets.setdefault(site, []).append(m.group(0))

    manifest = []
    for site, rows in sorted(buckets.items(), key=lambda x: (-len(x[1]), x[0])):
        safe = re.sub(r"[^a-zA-Z0-9._-]+", "_", site)
        path = OUT / f"{safe}.channels.xml"
        with path.open("w", encoding="utf-8") as f:
            f.write('<?xml version="1.0" encoding="UTF-8"?>\n<channels>\n')
            for row in rows:
                f.write(f"  {row}\n")
            f.write("</channels>\n")
        manifest.append(f"{site}\t{len(rows)}\t{path}")
        print(f"{site}: {len(rows)} -> {path.name}", flush=True)

    (OUT / "manifest.txt").write_text("\n".join(manifest) + "\n", encoding="utf-8")
    print(f"Wrote {len(buckets)} site files", flush=True)


if __name__ == "__main__":
    main()
