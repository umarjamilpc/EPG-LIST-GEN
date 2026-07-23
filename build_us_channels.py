"""
Build a deduplicated iptv-org channels.xml for US playlist ids.
One site entry per playlist channel (priority sites first) to keep grab small.
"""
from __future__ import annotations

import os
import re
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent
EPG_DIR = ROOT / "iptv-org-epg"
OUT_DIR = ROOT / "iptv-org-work"
OUT_DIR.mkdir(exist_ok=True)

# Prefer PLAYLIST_URL (not M3U_*) so update_epg.py does not treat it as a category secret.
M3U_URL = (
    os.environ.get("PLAYLIST_URL")
    or os.environ.get("M3U_US")
    or os.environ.get("M3U_URL")
    or "https://iptv-org.github.io/iptv/countries/us.m3u"
)
CHANNELS_OUT = OUT_DIR / "us.channels.xml"
REPORT_OUT = OUT_DIR / "us_channels_report.txt"

# Prefer US-friendly sites that use xmltv_id like CNN.us@SD
# Skip tvtv.us — currently returns HTTP 403 from this network/Actions
SITE_PRIORITY = [
    "tvguide.com",
    "tvpassport.com",
    "xumo.tv",
    "ontvtonight.com",
    "pluto.tv",
    "plex.tv",
    "i.mjh.nz",
    "watch.whaletvplus.com",
    "distro.tv",
    "gatotv.com",
    "epg.iptvx.one",
    "watchyour.tv",
]

SKIP_SITES = {"tvtv.us"}


def fetch_tvg_ids(url: str) -> set[str]:
    print(f"Downloading {url}", flush=True)
    req = urllib.request.Request(url, headers={"User-Agent": "epg-list-gen/1.0"})
    with urllib.request.urlopen(req, timeout=60) as resp:
        text = resp.read().decode("utf-8", "ignore")
    ids = {m.group(1).strip() for m in re.finditer(r'tvg-id="([^"]*)"', text) if m.group(1).strip()}
    print(f"Found {len(ids)} unique tvg-id values", flush=True)
    return ids


def site_rank(site: str) -> int:
    try:
        return SITE_PRIORITY.index(site)
    except ValueError:
        return 10_000


ATTR_RE = re.compile(r"<channel\b(?P<attrs>[^>]*)>(?P<body>.*?)</channel>", re.DOTALL)


def parse_attrs(attr_blob: str) -> dict[str, str]:
    return {k: v for k, v in re.findall(r'(\w+)="([^"]*)"', attr_blob)}


def main() -> None:
    wanted = fetch_tvg_ids(M3U_URL)
    wanted_lower = {w.lower(): w for w in wanted}
    for w in list(wanted):
        base = re.sub(r"@.*$", "", w)
        wanted_lower.setdefault(base.lower(), w)

    # playlist_id -> best channel record
    best: dict[str, dict] = {}

    files = sorted((EPG_DIR / "sites").glob("*/*.channels.xml"))
    print(f"Scanning {len(files)} site files", flush=True)

    for path in files:
        data = path.read_text(encoding="utf-8", errors="ignore")
        for m in ATTR_RE.finditer(data):
            attrs = parse_attrs(m.group("attrs"))
            xmltv = attrs.get("xmltv_id", "").strip()
            if not xmltv:
                continue
            key = xmltv.lower()
            base = re.sub(r"@.*$", "", key)
            playlist_id = wanted_lower.get(key) or wanted_lower.get(base)
            if not playlist_id:
                continue
            site = attrs.get("site", "")
            site_id = attrs.get("site_id", "")
            lang = attrs.get("lang", "en") or "en"
            if not site or not site_id:
                continue
            if site in SKIP_SITES:
                continue
            rec = {
                "site": site,
                "site_id": site_id,
                "lang": lang,
                "xmltv_id": xmltv,
                "body": (m.group("body").strip() or xmltv),
                "rank": site_rank(site),
            }
            prev = best.get(playlist_id)
            if prev is None or rec["rank"] < prev["rank"]:
                best[playlist_id] = rec

    by_site: dict[str, int] = {}
    with CHANNELS_OUT.open("w", encoding="utf-8") as out:
        out.write('<?xml version="1.0" encoding="UTF-8"?>\n<channels>\n')
        for playlist_id in sorted(best.keys(), key=str.lower):
            rec = best[playlist_id]
            # Use playlist tvg-id as xmltv_id so output matches M3U exactly
            out.write(
                f'  <channel site="{rec["site"]}" lang="{rec["lang"]}" '
                f'xmltv_id="{playlist_id}" site_id="{rec["site_id"]}">{rec["body"]}</channel>\n'
            )
            by_site[rec["site"]] = by_site.get(rec["site"], 0) + 1
        out.write("</channels>\n")

    unmatched = sorted(wanted - set(best.keys()))
    lines = [
        f"playlist_ids={len(wanted)}",
        f"matched={len(best)}",
        f"unmatched={len(unmatched)}",
        "by_site:",
    ]
    for site, n in sorted(by_site.items(), key=lambda x: (-x[1], x[0])):
        lines.append(f"  {site}: {n}")
    lines.append("unmatched_sample:")
    lines.extend(f"  {x}" for x in unmatched[:40])
    REPORT_OUT.write_text("\n".join(lines) + "\n", encoding="utf-8")

    print(f"Wrote {len(best)} channels -> {CHANNELS_OUT}", flush=True)
    print(f"Matched {len(best)} / {len(wanted)}", flush=True)
    print(f"Report -> {REPORT_OUT}", flush=True)
    for site, n in sorted(by_site.items(), key=lambda x: (-x[1], x[0]))[:12]:
        print(f"  {site}: {n}", flush=True)


if __name__ == "__main__":
    main()
