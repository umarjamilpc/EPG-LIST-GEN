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

URLS = [
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
    'http://mains.services/xmltv.php?username=tmo247line&password=65s4d64vgfdfbae4',
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
    'https://raw.githubusercontent.com/matthuisman/i.mjh.nz/refs/heads/master/PlutoTV/all.xml'
]


def sanitize_name(name):
    """Keep only safe filename characters."""
    cleaned = re.sub(r'[^a-zA-Z0-9_-]+', '-', name.strip().lower()).strip('-')
    return cleaned or "playlist"


def normalize_id(value):
    """Normalize channel IDs for comparison."""
    if not value:
        return ""
    return value.strip().lower()


def load_playlists():
    """
    Each GitHub secret = one EPG file.

    Secret name pattern:  M3U_<FILENAME>
    Secret value:         https://.../playlist.m3u
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


def get_tvg_ids_from_remote_m3u(m3u_url, label):
    """Download an M3U and extract channel id values."""
    tvg_ids = set()
    print(f"[{label}] Downloading M3U...")
    try:
        response = requests.get(m3u_url, timeout=60)
        if response.status_code != 200:
            print(f"[{label}] Failed to download M3U: {response.status_code}")
            return None

        text = response.text
        # Support double/single quotes and common alternate attributes
        patterns = [
            r'tvg-id="([^"]*)"',
            r"tvg-id='([^']*)'",
            r'channel-id="([^"]*)"',
            r"channel-id='([^']*)'",
            r'tvg_id="([^"]*)"',
            r"tvg_id='([^']*)'",
        ]
        for pattern in patterns:
            for val in re.findall(pattern, text, flags=re.IGNORECASE):
                cleaned = val.strip()
                if cleaned:
                    tvg_ids.add(cleaned)

        if not tvg_ids:
            print(f"[{label}] No tvg-id/channel-id values found in M3U.")
            # Show a small raw sample to help debug playlist format
            sample_lines = [ln for ln in text.splitlines() if ln.startswith("#EXTINF")][:3]
            for ln in sample_lines:
                print(f"[{label}] EXTINF sample: {ln[:240]}")
            return None

        sample = sorted(tvg_ids)[:10]
        print(f"[{label}] Mapped {len(tvg_ids)} unique channel ids from playlist.")
        print(f"[{label}] Sample playlist ids: {sample}")
        return tvg_ids
    except Exception as e:
        print(f"[{label}] Error fetching M3U: {e}")
        return None


def sanitize_xml_bytes(content):
    """Strip bytes that are illegal in XML 1.0 but keep valid whitespace."""
    return re.sub(rb'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]', b'', content)


def local_tag(tag):
    """Strip XML namespace from a tag if present."""
    if isinstance(tag, str) and "}" in tag:
        return tag.rsplit("}", 1)[-1]
    return tag


def parse_xml(content, url):
    """Try strict stdlib parse first, fall back to lxml recovery, then sanitize + retry."""
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
        print(f"Fetching EPG: {url.split('/')[-1]}")
        response = requests.get(url, timeout=90)
        if response.status_code != 200:
            print(f"  ! HTTP {response.status_code}")
            return None
        content = response.content
        if url.endswith('.gz') or response.headers.get("Content-Type", "").lower().find("gzip") >= 0:
            try:
                content = gzip.decompress(content)
            except OSError:
                pass
        return parse_xml(content, url)
    except Exception as e:
        print(f"  ! Error: {e}")
        return None


def iter_children(root, tag_name):
    """Find children by local tag name, ignoring XML namespaces."""
    for child in list(root):
        if local_tag(child.tag) == tag_name:
            yield child


def build_filtered_epg(epg_roots, valid_ids):
    """Filter pre-fetched EPG roots down to channels/programmes in valid_ids."""
    master_root = ET.Element('tv', {"generator-info-name": "EPG-LIST-GEN-Multi"})
    # Case-insensitive ID set
    wanted = {normalize_id(i) for i in valid_ids if normalize_id(i)}
    matched_channel_ids = set()
    channel_count = 0
    programme_count = 0

    for epg_data in epg_roots:
        for channel in iter_children(epg_data, "channel"):
            cid = channel.get("id") or ""
            if normalize_id(cid) in wanted:
                master_root.append(copy.deepcopy(channel))
                matched_channel_ids.add(cid)
                channel_count += 1

        for prog in iter_children(epg_data, "programme"):
            cid = prog.get("channel") or ""
            if normalize_id(cid) in wanted:
                prog_copy = copy.deepcopy(prog)
                title = None
                for child in list(prog_copy):
                    if local_tag(child.tag) == "title":
                        title = child
                        break
                if title is not None and title.text in ["NHL Hockey", "Live: NFL Football"]:
                    sub = None
                    for child in list(prog_copy):
                        if local_tag(child.tag) == "sub-title":
                            sub = child
                            break
                    if sub is not None and sub.text:
                        title.text = f"{title.text} {sub.text}"
                master_root.append(prog_copy)
                programme_count += 1

    return master_root, channel_count, programme_count, matched_channel_ids


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
        print("Create one secret per file, e.g. M3U_HOME = https://example.com/home.m3u")
        print("Then map it in .github/workflows/update.yml under env:")
        return

    print(f"Found {len(playlists)} playlist(s): {', '.join(p['name'] for p in playlists)}")

    playlist_ids = {}
    for playlist in playlists:
        name = playlist["name"]
        ids = get_tvg_ids_from_remote_m3u(playlist["url"], name)
        if ids:
            playlist_ids[name] = ids
        else:
            print(f"[{name}] Skipping — M3U filter is required to stay under GitHub size limits.")

    if not playlist_ids:
        print("Stopping process: no valid playlists to process.")
        return

    print("Downloading shared EPG sources...")
    epg_roots = []
    for url in URLS:
        epg_data = fetch_and_parse(url)
        if epg_data is not None:
            epg_roots.append(epg_data)

    if not epg_roots:
        print("Stopping process: no EPG sources could be downloaded.")
        return

    epg_samples = collect_epg_id_samples(epg_roots)
    print(f"Loaded {len(epg_roots)} EPG source file(s). Sample EPG channel ids: {epg_samples}")

    for name, valid_ids in playlist_ids.items():
        output_file = os.path.join(OUTPUT_DIR, f"{name}-epg.xml.gz")
        print(f"[{name}] Building filtered EPG ({len(valid_ids)} playlist ids)...")
        master_root, channel_count, programme_count, matched_ids = build_filtered_epg(epg_roots, valid_ids)
        print(f"[{name}] Matched {len(matched_ids)} unique channels, {channel_count} channel nodes, {programme_count} programmes.")
        if not matched_ids:
            print(f"[{name}] WARNING: Zero matches. Playlist ids do not overlap current EPG sources.")
            print(f"[{name}] Playlist sample: {sorted(valid_ids)[:10]}")
            print(f"[{name}] EPG sample: {epg_samples}")
            print(f"[{name}] Fix: update URLS in update_epg.py to sources that use the same channel ids as your M3U.")

        tree = ET.ElementTree(master_root)
        with gzip.open(output_file, 'wb') as f:
            tree.write(f, encoding='utf-8', xml_declaration=True)
        print(f"[{name}] Saved {output_file}")

    print("Multi-playlist EPG generation complete.")


if __name__ == "__main__":
    main()
