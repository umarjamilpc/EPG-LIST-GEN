import copy
import os
import gzip
import re
import xml.etree.ElementTree as ET
import requests

try:
    from lxml import etree as lxml_etree
    HAS_LXML = True
except ImportError:
    HAS_LXML = False

# Paths
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
OUTPUT_DIR = os.path.join(BASE_DIR, "epgs")
os.makedirs(OUTPUT_DIR, exist_ok=True)

# Fallback sources (used if M3U has no url-tvg / x-tvg-url)
DEFAULT_URLS = [
    'https://epgshare01.online/epgshare01/epg_ripper_US2.xml.gz',
    'https://epgshare01.online/epgshare01/epg_ripper_US_LOCALS1.xml.gz',
    'https://epgshare01.online/epgshare01/epg_ripper_CA2.xml.gz',
    'https://epgshare01.online/epgshare01/epg_ripper_UK1.xml.gz',
    'https://epgshare01.online/epgshare01/epg_ripper_MX1.xml.gz',
    'https://epgshare01.online/epgshare01/epg_ripper_AU1.xml.gz',
    'https://epgshare01.online/epgshare01/epg_ripper_IE1.xml.gz',
    'https://epgshare01.online/epgshare01/epg_ripper_DE1.xml.gz',
    'https://epgshare01.online/epgshare01/epg_ripper_ZA1.xml.gz',
    'https://epgshare01.online/epgshare01/epg_ripper_SV1.xml.gz',
    'https://epgshare01.online/epgshare01/epg_ripper_IT1.xml.gz',
    'https://epgshare01.online/epgshare01/epg_ripper_US_SPORTS1.xml.gz',
    'https://epgshare01.online/epgshare01/epg_ripper_FANDUEL1.xml.gz',
    'https://iptv-epg.org/files/epg-il.xml.gz',
    'https://raw.githubusercontent.com/BuddyChewChew/My-Streams/refs/heads/main/Backup/epg.xml',
    'https://raw.githubusercontent.com/BuddyChewChew/whiplash-epg/main/epg.xml',
    'https://github.com/BuddyChewChew/tcl-playlist-generator/raw/refs/heads/main/tcl_epg.xml',
    'https://github.com/matthuisman/i.mjh.nz/raw/refs/heads/master/nzau/epg.xml.gz',
    'https://epgshare01.online/epgshare01/epg_ripper_DUMMY_CHANNELS.xml.gz',
    'https://raw.githubusercontent.com/BuddyChewChew/localnow-playlist-generator/refs/heads/main/epg.xml',
    'https://github.com/matthuisman/i.mjh.nz/raw/master/Plex/all.xml.gz',
    'https://raw.githubusercontent.com/BuddyChewChew/dummy-epg-project/refs/heads/main/epg.xml',
    'https://github.com/matthuisman/i.mjh.nz/raw/master/Roku/all.xml',
    'https://github.com/BuddyChewChew/xumo-playlist-generator/raw/refs/heads/main/playlists/xumo_epg.xml.gz',
    'https://raw.githubusercontent.com/matthuisman/i.mjh.nz/refs/heads/master/PlutoTV/all.xml',
]


def sanitize_name(name):
    cleaned = re.sub(r'[^a-zA-Z0-9_-]+', '-', name.strip().lower()).strip('-')
    return cleaned or "playlist"


def normalize_id(value):
    if not value:
        return ""
    return value.strip().lower()


def id_aliases(value):
    """
    Build match aliases for a channel id.

    Example: CNN.us@SD -> {cnn.us@sd, cnn.us}
    """
    aliases = set()
    raw = normalize_id(value)
    if not raw:
        return aliases
    aliases.add(raw)
    # Strip quality / feed suffix: @SD, @HD, @East, etc.
    base = re.sub(r'@.*$', '', raw)
    if base:
        aliases.add(base)
    return aliases


def load_playlists():
    """
    Each GitHub secret = one EPG file.
    Secret name: M3U_<FILENAME>  Value: m3u URL
    """
    playlists = []
    prefix = "M3U_"
    for key, value in sorted(os.environ.items()):
        if not key.startswith(prefix):
            continue
        url = (value or "").strip()
        if not url:
            continue
        name = sanitize_name(key[len(prefix):])
        if not name:
            continue
        playlists.append({"name": name, "url": url})
    return playlists


def parse_extra_epg_urls():
    """Optional global secret EPG_URLS (comma or newline separated)."""
    raw = (os.getenv("EPG_URLS") or "").strip()
    if not raw:
        return []
    parts = re.split(r'[\n,]+', raw)
    return [p.strip() for p in parts if p.strip().startswith("http")]


def extract_tvg_urls(m3u_text):
    """Extract url-tvg / x-tvg-url links from M3U header."""
    urls = []
    header = "\n".join(m3u_text.splitlines()[:5])
    for attr in ("url-tvg", "x-tvg-url", "tvg-url"):
        for match in re.finditer(rf'{attr}=["\']([^"\']+)["\']', header, flags=re.IGNORECASE):
            for part in match.group(1).split(","):
                part = part.strip()
                if part.startswith("http"):
                    urls.append(part)
    # Dedupe preserve order
    seen = set()
    out = []
    for u in urls:
        if u not in seen:
            seen.add(u)
            out.append(u)
    return out


def get_playlist_data(m3u_url, label):
    """Download M3U and return tvg-ids + embedded EPG urls."""
    print(f"[{label}] Downloading M3U...")
    try:
        response = requests.get(m3u_url, timeout=60)
        if response.status_code != 200:
            print(f"[{label}] Failed to download M3U: {response.status_code}")
            return None

        text = response.text
        tvg_urls = extract_tvg_urls(text)
        if tvg_urls:
            print(f"[{label}] Found {len(tvg_urls)} EPG url(s) in M3U header:")
            for u in tvg_urls:
                print(f"[{label}]   - {u}")
        else:
            print(f"[{label}] No url-tvg/x-tvg-url found in M3U header.")

        tvg_ids = set()
        patterns = [
            r'tvg-id="([^"]*)"',
            r"tvg-id='([^']*)'",
            r'channel-id="([^"]*)"',
            r"channel-id='([^']*)'",
        ]
        for pattern in patterns:
            for val in re.findall(pattern, text, flags=re.IGNORECASE):
                cleaned = val.strip()
                if cleaned:
                    tvg_ids.add(cleaned)

        if not tvg_ids:
            print(f"[{label}] No tvg-id values found in M3U.")
            sample_lines = [ln for ln in text.splitlines() if ln.startswith("#EXTINF")][:3]
            for ln in sample_lines:
                print(f"[{label}] EXTINF sample: {ln[:240]}")
            return None

        print(f"[{label}] Mapped {len(tvg_ids)} unique channel ids.")
        print(f"[{label}] Sample playlist ids: {sorted(tvg_ids)[:10]}")
        return {"ids": tvg_ids, "epg_urls": tvg_urls}
    except Exception as e:
        print(f"[{label}] Error fetching M3U: {e}")
        return None


def sanitize_xml_bytes(content):
    return re.sub(rb'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]', b'', content)


def local_tag(tag):
    if isinstance(tag, str) and "}" in tag:
        return tag.rsplit("}", 1)[-1]
    return tag


def parse_xml(content, url):
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
        print(f"  ! Error parsing {url.split('/')[-1]}: {e}")
        return None


def fetch_and_parse(url):
    try:
        print(f"Fetching EPG: {url}")
        response = requests.get(url, timeout=90)
        if response.status_code != 200:
            print(f"  ! HTTP {response.status_code}")
            return None
        content = response.content
        if url.endswith('.gz') or "gzip" in response.headers.get("Content-Type", "").lower():
            try:
                content = gzip.decompress(content)
            except OSError:
                pass
        return parse_xml(content, url)
    except Exception as e:
        print(f"  ! Error: {e}")
        return None


def iter_children(root, tag_name):
    for child in list(root):
        if local_tag(child.tag) == tag_name:
            yield child


def build_alias_map(playlist_ids):
    """
    Map every alias -> preferred playlist tvg-id.
    Exact ids win over stripped aliases.
    """
    alias_map = {}
    # First pass: base aliases
    for pid in playlist_ids:
        for alias in id_aliases(pid):
            alias_map.setdefault(alias, pid)
    # Second pass: exact ids overwrite
    for pid in playlist_ids:
        alias_map[normalize_id(pid)] = pid
    return alias_map


def resolve_playlist_id(epg_id, alias_map):
    for alias in id_aliases(epg_id):
        if alias in alias_map:
            return alias_map[alias]
    return None


def build_filtered_epg(epg_roots, playlist_ids):
    """Filter EPG and rewrite channel ids to match playlist tvg-id values."""
    master_root = ET.Element('tv', {"generator-info-name": "EPG-LIST-GEN-Multi"})
    alias_map = build_alias_map(playlist_ids)
    matched_playlist_ids = set()
    channel_count = 0
    programme_count = 0
    seen_channels = set()

    for epg_data in epg_roots:
        for channel in iter_children(epg_data, "channel"):
            epg_id = channel.get("id") or ""
            playlist_id = resolve_playlist_id(epg_id, alias_map)
            if not playlist_id:
                continue
            if playlist_id in seen_channels:
                continue
            node = copy.deepcopy(channel)
            node.set("id", playlist_id)
            master_root.append(node)
            seen_channels.add(playlist_id)
            matched_playlist_ids.add(playlist_id)
            channel_count += 1

        for prog in iter_children(epg_data, "programme"):
            epg_id = prog.get("channel") or ""
            playlist_id = resolve_playlist_id(epg_id, alias_map)
            if not playlist_id:
                continue
            node = copy.deepcopy(prog)
            node.set("channel", playlist_id)
            title = None
            sub = None
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

    return master_root, channel_count, programme_count, matched_playlist_ids


def collect_epg_id_samples(epg_roots, limit=10):
    samples = []
    for epg_data in epg_roots:
        for channel in iter_children(epg_data, "channel"):
            cid = channel.get("id")
            if cid:
                samples.append(cid)
                if len(samples) >= limit:
                    return samples
    return samples


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
    all_epg_urls = list(extra_urls)

    for playlist in playlists:
        name = playlist["name"]
        data = get_playlist_data(playlist["url"], name)
        if not data:
            print(f"[{name}] Skipping — M3U filter is required.")
            continue
        playlist_data[name] = data
        for u in data["epg_urls"]:
            if u not in all_epg_urls:
                all_epg_urls.append(u)

    if not playlist_data:
        print("Stopping process: no valid playlists to process.")
        return

    # If no urls came from M3U/secret, fall back to defaults
    if not all_epg_urls:
        print("No M3U/secret EPG urls found — using built-in DEFAULT_URLS.")
        all_epg_urls = list(DEFAULT_URLS)
    else:
        # Still include defaults as secondary sources
        for u in DEFAULT_URLS:
            if u not in all_epg_urls:
                all_epg_urls.append(u)

    print(f"Downloading {len(all_epg_urls)} EPG source(s)...")
    epg_roots = []
    for url in all_epg_urls:
        epg_data = fetch_and_parse(url)
        if epg_data is not None:
            epg_roots.append(epg_data)

    if not epg_roots:
        print("Stopping process: no EPG sources could be downloaded.")
        return

    epg_samples = collect_epg_id_samples(epg_roots)
    print(f"Loaded {len(epg_roots)} EPG source file(s). Sample EPG channel ids: {epg_samples}")

    for name, data in playlist_data.items():
        valid_ids = data["ids"]
        output_file = os.path.join(OUTPUT_DIR, f"{name}-epg.xml.gz")
        print(f"[{name}] Building filtered EPG ({len(valid_ids)} playlist ids)...")
        master_root, channel_count, programme_count, matched_ids = build_filtered_epg(epg_roots, valid_ids)
        print(f"[{name}] Matched {len(matched_ids)} channels, {programme_count} programmes.")
        if not matched_ids:
            print(f"[{name}] WARNING: Zero matches.")
            print(f"[{name}] Playlist sample: {sorted(valid_ids)[:10]}")
            print(f"[{name}] EPG sample: {epg_samples}")
            print(f"[{name}] Fix options:")
            print(f"[{name}]   1) Ensure M3U header has url-tvg=... pointing to matching EPG")
            print(f"[{name}]   2) Add secret EPG_URLS with xml/xml.gz links that use your tvg-id values")

        tree = ET.ElementTree(master_root)
        with gzip.open(output_file, 'wb') as f:
            tree.write(f, encoding='utf-8', xml_declaration=True)
        print(f"[{name}] Saved {output_file}")

    print("Multi-playlist EPG generation complete.")


if __name__ == "__main__":
    main()
