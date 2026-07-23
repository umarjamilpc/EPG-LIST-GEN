import copy
import csv
import glob
import gzip
import os
import re
import xml.etree.ElementTree as ET
from pathlib import Path

import requests

try:
    from lxml import etree as lxml_etree
    HAS_LXML = True
except ImportError:
    HAS_LXML = False

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
EPGS_ROOT = os.path.join(BASE_DIR, "epgs")
os.makedirs(EPGS_ROOT, exist_ok=True)

DEFAULT_URLS = [
    "https://iptv-epg.org/files/epg-xdbezrvvbu.xml.gz",
    "https://epgshare01.online/epgshare01/epg_ripper_US2.xml.gz",
    "https://epgshare01.online/epgshare01/epg_ripper_US_SPORTS1.xml.gz",
    "https://epgshare01.online/epgshare01/epg_ripper_DUMMY_CHANNELS.xml.gz",
    "https://epgshare01.online/epgshare01/epg_ripper_WHALETVPLUS1.xml.gz",
]


def category_from_secret_key(key: str) -> str:
    """M3U_US -> US (preserve case for folder name)."""
    suffix = key[len("M3U_") :] if key.startswith("M3U_") else key
    cleaned = re.sub(r"[^a-zA-Z0-9_-]+", "-", suffix.strip()).strip("-")
    return cleaned or "playlist"


def normalize_id(value):
    return (value or "").strip().lower()


def id_aliases(value):
    aliases = set()
    raw = normalize_id(value)
    if not raw:
        return aliases
    aliases.add(raw)
    base = re.sub(r"@.*$", "", raw)
    if base:
        aliases.add(base)
    return aliases


def channel_slug(value):
    raw = normalize_id(value)
    raw = re.sub(r"@.*$", "", raw)
    if not raw:
        return ""
    return raw.split(".", 1)[0]


def load_playlists():
    playlists = []
    for key, value in sorted(os.environ.items()):
        if not key.startswith("M3U_"):
            continue
        url = (value or "").strip()
        if not url:
            continue
        cat = category_from_secret_key(key)
        playlists.append({"key": key, "name": cat, "url": url})
    return playlists


def parse_extra_epg_urls():
    raw = (os.getenv("EPG_URLS") or "").strip()
    if not raw:
        return []
    return [p.strip() for p in re.split(r"[\n,]+", raw) if p.strip().startswith("http")]


def extract_tvg_urls(m3u_text):
    urls = []
    header = "\n".join(m3u_text.splitlines()[:5])
    for attr in ("url-tvg", "x-tvg-url", "tvg-url"):
        for match in re.finditer(rf'{attr}=["\']([^"\']+)["\']', header, flags=re.IGNORECASE):
            for part in match.group(1).split(","):
                part = part.strip()
                if part.startswith("http"):
                    urls.append(part)
    seen, out = set(), []
    for u in urls:
        if u not in seen:
            seen.add(u)
            out.append(u)
    return out


def guess_provider_epg_urls(m3u_url):
    urls = []
    if "get.php" in m3u_url:
        urls.append(m3u_url.replace("get.php", "xmltv.php"))
    return urls


def get_playlist_data(m3u_url, label):
    print(f"[{label}] Downloading M3U...")
    try:
        response = requests.get(m3u_url, timeout=60)
        if response.status_code != 200:
            print(f"[{label}] Failed to download M3U: {response.status_code}")
            return None
        text = response.text
        tvg_urls = extract_tvg_urls(text)
        for u in guess_provider_epg_urls(m3u_url):
            if u not in tvg_urls:
                tvg_urls.append(u)
                print(f"[{label}] Also trying provider EPG guess: {u}")
        if tvg_urls:
            print(f"[{label}] Found {len(tvg_urls)} EPG url(s) from M3U/provider:")
            for u in tvg_urls:
                print(f"[{label}]   - {u}")
        else:
            print(f"[{label}] No url-tvg/x-tvg-url found in M3U header.")

        tvg_ids = set()
        for pattern in (
            r'tvg-id="([^"]*)"',
            r"tvg-id='([^']*)'",
            r'channel-id="([^"]*)"',
            r"channel-id='([^']*)'",
        ):
            for val in re.findall(pattern, text, flags=re.IGNORECASE):
                cleaned = val.strip()
                if cleaned:
                    tvg_ids.add(cleaned)
        if not tvg_ids:
            print(f"[{label}] No tvg-id values found in M3U.")
            return None
        print(f"[{label}] Mapped {len(tvg_ids)} unique channel ids.")
        print(f"[{label}] Sample playlist ids: {sorted(tvg_ids)[:10]}")
        return {"ids": tvg_ids, "epg_urls": tvg_urls}
    except Exception as e:
        print(f"[{label}] Error fetching M3U: {e}")
        return None


def sanitize_xml_bytes(content):
    return re.sub(rb"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]", b"", content)


def local_tag(tag):
    if isinstance(tag, str) and "}" in tag:
        return tag.rsplit("}", 1)[-1]
    return tag


def parse_xml(content, label):
    try:
        return ET.fromstring(content)
    except ET.ParseError:
        pass
    if HAS_LXML:
        try:
            root_lxml = lxml_etree.fromstring(content, parser=lxml_etree.XMLParser(recover=True))
            return ET.fromstring(lxml_etree.tostring(root_lxml))
        except Exception:
            pass
    try:
        return ET.fromstring(sanitize_xml_bytes(content))
    except ET.ParseError as e:
        print(f"  ! Error parsing {label}: {e}")
        return None


def source_label(url_or_path: str) -> str:
    if url_or_path.startswith("file://"):
        return Path(url_or_path[len("file://") :]).name
    return url_or_path.rstrip("/").split("/")[-1] or url_or_path


def fetch_and_parse(url):
    try:
        if url.startswith("file://"):
            path = url[len("file://") :]
            print(f"Loading local EPG: {path}")
            with open(path, "rb") as f:
                content = f.read()
            if path.endswith(".gz"):
                content = gzip.decompress(content)
            return parse_xml(content, path)
        print(f"Fetching EPG: {url}")
        response = requests.get(url, timeout=300)
        if response.status_code != 200:
            print(f"  ! HTTP {response.status_code}")
            return None
        content = response.content
        print(f"  downloaded {len(content)} bytes")
        if url.endswith(".gz") or "gzip" in response.headers.get("Content-Type", "").lower():
            try:
                content = gzip.decompress(content)
                print(f"  decompressed to {len(content)} bytes")
            except OSError:
                pass
        return parse_xml(content, url)
    except Exception as e:
        print(f"  ! Error: {e}")
        return None


def local_iptvorg_sources(category: str | None = None):
    patterns = []
    if category:
        patterns.append(os.path.join(EPGS_ROOT, category, "iptvorg-guide*.xml.gz"))
        patterns.append(os.path.join(EPGS_ROOT, category, "*-iptvorg-guide*.xml.gz"))
    patterns.append(os.path.join(EPGS_ROOT, "us-iptvorg-guide*.xml.gz"))
    patterns.append(os.path.join(EPGS_ROOT, "*", "iptvorg-guide*.xml.gz"))
    paths = []
    for pat in patterns:
        paths.extend(glob.glob(pat))
    # unique preserve order
    seen, out = set(), []
    for p in sorted(set(paths)):
        ap = os.path.abspath(p)
        if ap not in seen:
            seen.add(ap)
            out.append(f"file://{ap}")
    return out


def iter_children(root, tag_name):
    for child in list(root):
        if local_tag(child.tag) == tag_name:
            yield child


def build_alias_maps(playlist_ids):
    alias_map, slug_map = {}, {}
    for pid in playlist_ids:
        for alias in id_aliases(pid):
            alias_map.setdefault(alias, pid)
        slug = channel_slug(pid)
        if slug:
            slug_map.setdefault(slug, pid)
    for pid in playlist_ids:
        alias_map[normalize_id(pid)] = pid
    return alias_map, slug_map


def resolve_playlist_id(epg_id, alias_map, slug_map):
    for alias in id_aliases(epg_id):
        if alias in alias_map:
            return alias_map[alias]
    slug = channel_slug(epg_id)
    if slug and slug in slug_map:
        return slug_map[slug]
    return None


def build_filtered_epg(epg_sources, playlist_ids):
    """
    epg_sources: list of (source_label, root)
    Returns master_root, stats dict with matched/unmatched/duplicates info.
    """
    master_root = ET.Element("tv", {"generator-info-name": "EPG-LIST-GEN-Multi"})
    alias_map, slug_map = build_alias_maps(playlist_ids)

    # playlist_id -> first winning source
    chosen_source = {}
    # playlist_id -> [sources that also matched]
    duplicate_sources = {}
    # playlist_id -> epg channel id used for first match
    chosen_epg_id = {}
    programme_count = 0
    channel_count = 0

    for src_label, epg_data in epg_sources:
        for channel in iter_children(epg_data, "channel"):
            epg_id = channel.get("id") or ""
            playlist_id = resolve_playlist_id(epg_id, alias_map, slug_map)
            if not playlist_id:
                continue
            if playlist_id in chosen_source:
                if src_label != chosen_source[playlist_id]:
                    duplicate_sources.setdefault(playlist_id, [])
                    if src_label not in duplicate_sources[playlist_id]:
                        duplicate_sources[playlist_id].append(src_label)
                continue
            node = copy.deepcopy(channel)
            node.set("id", playlist_id)
            master_root.append(node)
            chosen_source[playlist_id] = src_label
            chosen_epg_id[playlist_id] = epg_id
            channel_count += 1

        for prog in iter_children(epg_data, "programme"):
            epg_id = prog.get("channel") or ""
            playlist_id = resolve_playlist_id(epg_id, alias_map, slug_map)
            if not playlist_id:
                continue
            # Only keep programmes for channels we accepted, from any matched source id
            if playlist_id not in chosen_source:
                continue
            node = copy.deepcopy(prog)
            node.set("channel", playlist_id)
            title = sub = None
            for child in list(node):
                tag = local_tag(child.tag)
                if tag == "title" and title is None:
                    title = child
                elif tag == "sub-title" and sub is None:
                    sub = child
            if title is not None and title.text in ["NHL Hockey", "Live: NFL Football"]:
                if sub is not None and sub.text:
                    title.text = f"{title.text} {sub.text}"
            master_root.append(node)
            programme_count += 1

    unmatched = sorted(set(playlist_ids) - set(chosen_source.keys()))
    matched_rows = [
        {
            "tvg_id": pid,
            "epg_id_matched": chosen_epg_id.get(pid, ""),
            "source": chosen_source[pid],
            "duplicate_sources": ";".join(duplicate_sources.get(pid, [])),
        }
        for pid in sorted(chosen_source.keys(), key=str.lower)
    ]
    return master_root, {
        "channel_count": channel_count,
        "programme_count": programme_count,
        "matched": matched_rows,
        "unmatched": unmatched,
        "duplicates": {
            pid: {"primary": chosen_source[pid], "also_in": sources}
            for pid, sources in sorted(duplicate_sources.items())
            if sources
        },
    }


def write_reports(category_dir: str, stats: dict):
    reports = Path(category_dir) / "reports"
    reports.mkdir(parents=True, exist_ok=True)

    matched_csv = reports / "matched.csv"
    with matched_csv.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(
            f, fieldnames=["tvg_id", "epg_id_matched", "source", "duplicate_sources"]
        )
        writer.writeheader()
        writer.writerows(stats["matched"])

    unmatched_txt = reports / "unmatched.txt"
    unmatched_txt.write_text(
        "\n".join(stats["unmatched"]) + ("\n" if stats["unmatched"] else ""),
        encoding="utf-8",
    )

    dup_txt = reports / "duplicates.txt"
    lines = []
    for pid, info in stats["duplicates"].items():
        lines.append(f"{pid}\tprimary={info['primary']}\talso_in={';'.join(info['also_in'])}")
    dup_txt.write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")

    summary = reports / "summary.txt"
    summary.write_text(
        "\n".join(
            [
                f"matched_channels={len(stats['matched'])}",
                f"unmatched_channels={len(stats['unmatched'])}",
                f"duplicate_channels={len(stats['duplicates'])}",
                f"channel_nodes={stats['channel_count']}",
                f"programmes={stats['programme_count']}",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    print(f"Reports written to {reports}")
    print(f"  matched:   {matched_csv}")
    print(f"  unmatched: {unmatched_txt} ({len(stats['unmatched'])})")
    print(f"  duplicates:{dup_txt} ({len(stats['duplicates'])})")


def main():
    playlists = load_playlists()
    if not playlists:
        print("CRITICAL: No M3U_* secrets found.")
        return

    print(f"Found {len(playlists)} playlist(s): {', '.join(p['name'] for p in playlists)}")
    extra_urls = parse_extra_epg_urls()
    if extra_urls:
        print(f"Loaded {len(extra_urls)} extra EPG url(s) from EPG_URLS secret.")

    playlist_data = {}
    for playlist in playlists:
        name = playlist["name"]
        data = get_playlist_data(playlist["url"], name)
        if not data:
            print(f"[{name}] Skipping — M3U filter is required.")
            continue
        playlist_data[name] = data

    if not playlist_data:
        print("Stopping process: no valid playlists to process.")
        return

    use_defaults = (os.getenv("EPG_USE_DEFAULTS") or "").strip().lower() in {"1", "true", "yes"}

    for name, data in playlist_data.items():
        category_dir = os.path.join(EPGS_ROOT, name)
        os.makedirs(category_dir, exist_ok=True)

        local_urls = local_iptvorg_sources(name)
        all_epg_urls = list(local_urls)
        for u in extra_urls:
            if u not in all_epg_urls:
                all_epg_urls.append(u)
        for u in data.get("epg_urls") or []:
            if u not in all_epg_urls:
                all_epg_urls.append(u)
        if not all_epg_urls or use_defaults:
            if not all_epg_urls:
                print(f"[{name}] No local/secret EPG sources — using DEFAULT_URLS.")
            for u in DEFAULT_URLS:
                if u not in all_epg_urls:
                    all_epg_urls.append(u)

        print(f"[{name}] Loading {len(all_epg_urls)} EPG source(s)...")
        epg_sources = []
        for url in all_epg_urls:
            root = fetch_and_parse(url)
            if root is not None:
                epg_sources.append((source_label(url), root))

        if not epg_sources:
            print(f"[{name}] Stopping — no EPG sources loaded.")
            continue

        valid_ids = data["ids"]
        print(f"[{name}] Building filtered EPG ({len(valid_ids)} playlist ids)...")
        master_root, stats = build_filtered_epg(epg_sources, valid_ids)
        print(
            f"[{name}] Matched {len(stats['matched'])}/{len(valid_ids)} channels, "
            f"{stats['programme_count']} programmes, "
            f"{len(stats['duplicates'])} with multi-source duplicates."
        )

        # Log first 20 matched / unmatched to Actions console
        print(f"[{name}] --- matched sample (tvg_id | source) ---")
        for row in stats["matched"][:20]:
            print(f"[{name}]   {row['tvg_id']} | {row['source']}")
        print(f"[{name}] --- unmatched sample ---")
        for pid in stats["unmatched"][:20]:
            print(f"[{name}]   {pid}")
        if stats["duplicates"]:
            print(f"[{name}] --- duplicates sample ---")
            for i, (pid, info) in enumerate(stats["duplicates"].items()):
                if i >= 10:
                    break
                print(f"[{name}]   {pid} primary={info['primary']} also={info['also_in']}")

        write_reports(category_dir, stats)

        output_file = os.path.join(category_dir, "epg.xml.gz")
        tree = ET.ElementTree(master_root)
        with gzip.open(output_file, "wb") as f:
            tree.write(f, encoding="utf-8", xml_declaration=True)
        print(f"[{name}] Saved {output_file}")

    print("Multi-playlist EPG generation complete.")


if __name__ == "__main__":
    main()
