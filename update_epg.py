import copy
import csv
import glob
import gzip
import io
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

# Keep under GitHub soft file-size limit with room to spare
MAX_GZ_BYTES = 40 * 1024 * 1024

DEFAULT_URLS = [
    "https://iptv-epg.org/files/epg-xdbezrvvbu.xml.gz",
    "https://epgshare01.online/epgshare01/epg_ripper_US2.xml.gz",
    "https://epgshare01.online/epgshare01/epg_ripper_US_SPORTS1.xml.gz",
    "https://epgshare01.online/epgshare01/epg_ripper_DUMMY_CHANNELS.xml.gz",
    "https://epgshare01.online/epgshare01/epg_ripper_WHALETVPLUS1.xml.gz",
]

# Env aliases used by grab scripts — not playlist category secrets
RESERVED_M3U_KEYS = {"M3U_URL"}


def env_bool(name: str, default: bool = True) -> bool:
    raw = (os.getenv(name) or "").strip().lower()
    if not raw:
        return default
    if raw in {"1", "true", "yes", "on"}:
        return True
    if raw in {"0", "false", "no", "off"}:
        return False
    return default


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
        if key in RESERVED_M3U_KEYS:
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


def local_grabber_sources(category: str):
    """Raw guides produced by the iptv-org grabber for this category."""
    patterns = [
        os.path.join(EPGS_ROOT, category, "grabber-raw-guide*.xml.gz"),
    ]
    paths = []
    for pat in patterns:
        paths.extend(glob.glob(pat))
    seen, out = set(), []
    for p in sorted(set(paths)):
        ap = os.path.abspath(p)
        if ap not in seen:
            seen.add(ap)
            out.append(f"file://{ap}")
    return out


def load_sources(urls):
    sources = []
    for url in urls:
        root = fetch_and_parse(url)
        if root is not None:
            sources.append((source_label(url), root))
    return sources


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

    chosen_source = {}
    duplicate_sources = {}
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
            if playlist_id not in chosen_source:
                continue
            # Only keep programmes from the winning (first) source for this channel
            if chosen_source[playlist_id] != src_label:
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


def write_reports(category_dir: str, stats: dict, prefix: str):
    """Write reports/<prefix>-matched.csv etc."""
    reports = Path(category_dir) / "reports"
    reports.mkdir(parents=True, exist_ok=True)

    matched_csv = reports / f"{prefix}-matched.csv"
    with matched_csv.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(
            f, fieldnames=["tvg_id", "epg_id_matched", "source", "duplicate_sources"]
        )
        writer.writeheader()
        writer.writerows(stats["matched"])

    unmatched_txt = reports / f"{prefix}-unmatched.txt"
    unmatched_txt.write_text(
        "\n".join(stats["unmatched"]) + ("\n" if stats["unmatched"] else ""),
        encoding="utf-8",
    )

    dup_txt = reports / f"{prefix}-duplicates.txt"
    lines = []
    for pid, info in stats["duplicates"].items():
        lines.append(f"{pid}\tprimary={info['primary']}\talso_in={';'.join(info['also_in'])}")
    dup_txt.write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")

    summary = reports / f"{prefix}-summary.txt"
    summary.write_text(
        "\n".join(
            [
                f"kind={prefix}",
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

    print(f"[{prefix}] Reports under {reports}")
    print(f"  {matched_csv.name}")
    print(f"  {unmatched_txt.name} ({len(stats['unmatched'])} unmatched)")
    print(f"  {dup_txt.name} ({len(stats['duplicates'])} duplicates)")
    print(f"  {summary.name}")


def root_to_gzip_bytes(root: ET.Element) -> bytes:
    buf = io.BytesIO()
    tree = ET.ElementTree(root)
    raw = io.BytesIO()
    tree.write(raw, encoding="utf-8", xml_declaration=True)
    with gzip.GzipFile(fileobj=buf, mode="wb", compresslevel=6) as gz:
        gz.write(raw.getvalue())
    return buf.getvalue()


def split_root_by_channels(root: ET.Element, max_parts_hint: int = 2) -> list[ET.Element]:
    channels = list(iter_children(root, "channel"))
    programmes = list(iter_children(root, "programme"))
    if not channels:
        return [root]

    # Binary-search-ish: grow part count until each part gz fits (cap at 20)
    for n_parts in range(1, 21):
        if n_parts == 1:
            parts_channels = [channels]
        else:
            size = (len(channels) + n_parts - 1) // n_parts
            parts_channels = [channels[i : i + size] for i in range(0, len(channels), size)]

        roots = []
        oversized = False
        for ch_list in parts_channels:
            ids = {c.get("id") for c in ch_list}
            part = ET.Element("tv", dict(root.attrib))
            for c in ch_list:
                part.append(copy.deepcopy(c))
            for p in programmes:
                if p.get("channel") in ids:
                    part.append(copy.deepcopy(p))
            gz = root_to_gzip_bytes(part)
            if len(gz) > MAX_GZ_BYTES and len(ch_list) > 1:
                oversized = True
                break
            roots.append(part)
        if not oversized:
            if n_parts > 1:
                print(f"  split into {len(roots)} part(s) to stay under {MAX_GZ_BYTES} bytes")
            return roots
        if n_parts == 1 and max_parts_hint:
            continue
    return roots  # last attempt even if oversized


def write_epg_files(root: ET.Element, out_dir: Path, basename: str) -> list[Path]:
    """
    Write basename.xml.gz, or basename-part-01.xml.gz ... if over size limit.
    Removes previous matching files first.
    """
    out_dir.mkdir(parents=True, exist_ok=True)
    for old in out_dir.glob(f"{basename}.xml.gz"):
        old.unlink()
    for old in out_dir.glob(f"{basename}-part-*.xml.gz"):
        old.unlink()

    parts = split_root_by_channels(root)
    written = []
    if len(parts) == 1:
        path = out_dir / f"{basename}.xml.gz"
        data = root_to_gzip_bytes(parts[0])
        path.write_bytes(data)
        written.append(path)
        print(f"  saved {path} ({len(data)} bytes)")
    else:
        for i, part in enumerate(parts, start=1):
            path = out_dir / f"{basename}-part-{i:02d}.xml.gz"
            data = root_to_gzip_bytes(part)
            path.write_bytes(data)
            written.append(path)
            print(f"  saved {path} ({len(data)} bytes)")
    return written


def log_stats_sample(label: str, kind: str, stats: dict, valid_ids: set):
    print(
        f"[{label}/{kind}] Matched {len(stats['matched'])}/{len(valid_ids)} channels, "
        f"{stats['programme_count']} programmes, "
        f"{len(stats['duplicates'])} with multi-source duplicates."
    )
    print(f"[{label}/{kind}] --- matched sample (tvg_id | source) ---")
    for row in stats["matched"][:20]:
        print(f"[{label}/{kind}]   {row['tvg_id']} | {row['source']}")
    print(f"[{label}/{kind}] --- unmatched sample ---")
    for pid in stats["unmatched"][:20]:
        print(f"[{label}/{kind}]   {pid}")


def process_category(name: str, data: dict, extra_urls: list[str], use_defaults: bool, grabber_on: bool):
    category_dir = Path(EPGS_ROOT) / name
    category_dir.mkdir(parents=True, exist_ok=True)
    merge_dir = category_dir / "merge"
    valid_ids = data["ids"]

    # --- Grabber sources (local raw guides from iptv-org Action) ---
    grabber_urls = local_grabber_sources(name) if grabber_on else []
    if grabber_on and not grabber_urls:
        print(f"[{name}] Grabber ON but no grabber-raw-guide*.xml.gz found under {category_dir}")
    elif not grabber_on:
        print(f"[{name}] Grabber OFF (EPG_GRABBER=false) — skipping grabber EPG.")

    grabber_sources = load_sources(grabber_urls) if grabber_urls else []
    grabber_root = None
    grabber_stats = None
    if grabber_sources:
        print(f"[{name}] Building grabber-filtered EPG from {len(grabber_sources)} file(s)...")
        grabber_root, grabber_stats = build_filtered_epg(grabber_sources, valid_ids)
        log_stats_sample(name, "grabber", grabber_stats, valid_ids)
        write_reports(str(category_dir), grabber_stats, "grabber")
        write_epg_files(grabber_root, category_dir, "grabber-epg")
    else:
        # Remove stale grabber outputs when grabber produced nothing this run
        for old in category_dir.glob("grabber-epg*.xml.gz"):
            old.unlink()

    # --- URL sources (EPG_URLS secret + M3U header / provider guesses + optional defaults) ---
    url_list = []
    for u in extra_urls:
        if u not in url_list:
            url_list.append(u)
    for u in data.get("epg_urls") or []:
        if u not in url_list:
            url_list.append(u)
    if use_defaults:
        print(f"[{name}] EPG_USE_DEFAULTS enabled — merging lean DEFAULT_URLS into urls-epg.")
        for u in DEFAULT_URLS:
            if u not in url_list:
                url_list.append(u)
    elif not url_list:
        print(f"[{name}] No EPG_URLS / M3U url-tvg — skipping urls-epg (set EPG_URLS or EPG_USE_DEFAULTS=true).")

    print(f"[{name}] Loading {len(url_list)} URL EPG source(s)...")
    url_sources = load_sources(url_list) if url_list else []
    urls_root = None
    urls_stats = None
    if url_sources:
        print(f"[{name}] Building urls-filtered EPG...")
        urls_root, urls_stats = build_filtered_epg(url_sources, valid_ids)
        log_stats_sample(name, "urls", urls_stats, valid_ids)
        write_reports(str(category_dir), urls_stats, "urls")
        write_epg_files(urls_root, category_dir, "urls-epg")
    else:
        print(f"[{name}] No URL EPG sources loaded.")
        for old in category_dir.glob("urls-epg*.xml.gz"):
            old.unlink()

    # --- Merge: grabber first (priority), then urls fill gaps ---
    merge_sources = []
    if grabber_root is not None:
        merge_sources.append(("grabber-epg", grabber_root))
    if urls_root is not None:
        merge_sources.append(("urls-epg", urls_root))

    if not merge_sources:
        print(f"[{name}] Nothing to merge — no grabber or urls EPG.")
        return

    print(f"[{name}] Building merge EPG ({len(merge_sources)} input(s), grabber wins on duplicates)...")
    merge_root, merge_stats = build_filtered_epg(merge_sources, valid_ids)
    log_stats_sample(name, "merge", merge_stats, valid_ids)
    write_reports(str(category_dir), merge_stats, "merge")
    write_epg_files(merge_root, merge_dir, "merged-epg")

    # Clean leftover legacy filenames if any remain
    for legacy in ("epg.xml.gz",):
        p = category_dir / legacy
        if p.exists():
            print(f"[{name}] Removing legacy {p.name}")
            p.unlink()
    for pat in ("iptvorg-guide*.xml.gz", "us-*-epg.xml.gz"):
        for old in category_dir.glob(pat):
            print(f"[{name}] Removing legacy {old.name}")
            old.unlink()


def main():
    playlists = load_playlists()
    if not playlists:
        print("CRITICAL: No M3U_* secrets found.")
        return

    grabber_on = env_bool("EPG_GRABBER", default=True)
    use_defaults = env_bool("EPG_USE_DEFAULTS", default=False)
    print(f"Found {len(playlists)} playlist(s): {', '.join(p['name'] for p in playlists)}")
    print(f"EPG_GRABBER={'true' if grabber_on else 'false'}")

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

    for name, data in playlist_data.items():
        process_category(name, data, extra_urls, use_defaults, grabber_on)

    print("Multi-playlist EPG generation complete.")


if __name__ == "__main__":
    main()
