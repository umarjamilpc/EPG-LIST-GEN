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
    'https://epg.pw/api/epg.xml?lang=en&timezone=VVMvRWFzdGVybg%3D%3D&date=20260405&channel_id=464981',
    'https://github.com/BuddyChewChew/xumo-playlist-generator/raw/refs/heads/main/playlists/xumo_epg.xml.gz',
    'https://raw.githubusercontent.com/matthuisman/i.mjh.nz/refs/heads/master/PlutoTV/all.xml'
]


def sanitize_name(name):
    """Keep only safe filename characters."""
    cleaned = re.sub(r'[^a-zA-Z0-9_-]+', '-', name.strip().lower()).strip('-')
    return cleaned or "playlist"


def load_playlists():
    """
    Each GitHub secret = one EPG file.

    Secret name pattern:  M3U_<FILENAME>
    Secret value:         https://.../playlist.m3u

    Example:
      Secret M3U_HOME   = https://example.com/home.m3u   -> epgs/home-epg.xml.gz
      Secret M3U_SPORTS = https://example.com/sports.m3u -> epgs/sports-epg.xml.gz
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
    """Download an M3U and extract tvg-id values."""
    tvg_ids = set()
    print(f"[{label}] Downloading M3U...")
    try:
        response = requests.get(m3u_url, timeout=30)
        if response.status_code != 200:
            print(f"[{label}] Failed to download M3U: {response.status_code}")
            return None

        pattern = re.compile(r'tvg-id="([^"]+)"')
        matches = pattern.findall(response.text)
        for val in matches:
            tvg_ids.add(val)

        print(f"[{label}] Mapped {len(tvg_ids)} channels from playlist.")
        return tvg_ids
    except Exception as e:
        print(f"[{label}] Error fetching M3U: {e}")
        return None


def sanitize_xml_bytes(content):
    """Strip bytes that are illegal in XML 1.0 but keep valid whitespace."""
    return re.sub(rb'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]', b'', content)


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
        print(f"  ! Error: {e}")
        return None


def fetch_and_parse(url):
    try:
        print(f"Fetching EPG: {url.split('/')[-1]}")
        response = requests.get(url, timeout=60)
        if response.status_code != 200:
            return None
        content = response.content
        if url.endswith('.gz'):
            content = gzip.decompress(content)
        return parse_xml(content, url)
    except Exception as e:
        print(f"  ! Error: {e}")
        return None


def build_filtered_epg(epg_roots, valid_ids):
    """Filter pre-fetched EPG roots down to channels/programmes in valid_ids."""
    master_root = ET.Element('tv', {"generator-info-name": "EPG-LIST-GEN-Multi"})

    for epg_data in epg_roots:
        for channel in epg_data.findall('channel'):
            if channel.get('id') in valid_ids:
                master_root.append(channel)

        for prog in epg_data.findall('programme'):
            if prog.get('channel') in valid_ids:
                title = prog.find('title')
                if title is not None and title.text in ['NHL Hockey', 'Live: NFL Football']:
                    sub = prog.find('sub-title')
                    if sub is not None and sub.text:
                        title.text = f"{title.text} {sub.text}"
                master_root.append(prog)

    return master_root


def main():
    playlists = load_playlists()
    if not playlists:
        print("CRITICAL: No M3U_* secrets found.")
        print("Create one secret per file, e.g. M3U_HOME = https://example.com/home.m3u")
        print("Then map it in .github/workflows/update.yml under env:")
        return

    print(f"Found {len(playlists)} playlist(s): {', '.join(p['name'] for p in playlists)}")

    # Resolve channel IDs for every playlist first
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

    # Download each EPG source once, then filter per playlist
    print("Downloading shared EPG sources...")
    epg_roots = []
    for url in URLS:
        epg_data = fetch_and_parse(url)
        if epg_data is not None:
            epg_roots.append(epg_data)

    if not epg_roots:
        print("Stopping process: no EPG sources could be downloaded.")
        return

    for name, valid_ids in playlist_ids.items():
        output_file = os.path.join(OUTPUT_DIR, f"{name}-epg.xml.gz")
        print(f"[{name}] Building filtered EPG ({len(valid_ids)} channel ids)...")
        master_root = build_filtered_epg(epg_roots, valid_ids)
        tree = ET.ElementTree(master_root)
        with gzip.open(output_file, 'wb') as f:
            tree.write(f, encoding='utf-8', xml_declaration=True)
        print(f"[{name}] Saved {output_file}")

    print("Multi-playlist EPG generation complete.")


if __name__ == "__main__":
    main()
