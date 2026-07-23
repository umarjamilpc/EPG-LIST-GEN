# EPG LIST GEN: Multi-Playlist EPG Harvester

Creates custom TV guide (EPG) files from multiple M3U playlists.
**Each GitHub secret = one EPG file.**

Based on [BuddyChewChew/multi-epg-light](https://github.com/BuddyChewChew/multi-epg-light).

## Secrets

| Secret | Purpose | Example |
|--------|---------|---------|
| `M3U_US` | Playlist URL | `https://.../us.m3u` → `epgs/us-epg.xml.gz` |
| `EPG_URLS` | EPG xml/xml.gz URL(s) | `https://iptv-epg.org/files/epg-xdbezrvvbu.xml.gz` |
| `EPG_USE_DEFAULTS` | Optional `1` to also merge lean built-in sources | `1` |

Rule: `M3U_<NAME>` → `epgs/<name>-epg.xml.gz`

Also map each `M3U_*` secret in `.github/workflows/update.yml` under `env:`.

## Schedule (free-tier friendly)

Runs **twice daily** (`00:00` and `12:00` UTC), plus manual `workflow_dispatch`.

## About [iptv-org/epg](https://github.com/iptv-org/epg)

Important findings:

- iptv-org **no longer hosts ready guide files** on `iptv-org.github.io` (old `/epg/guides/...` URLs are 404).
- [GUIDES.md](https://github.com/iptv-org/epg/blob/master/GUIDES.md) community hosts are mostly empty/unusable.
- The repo is a **grabber**, not a feed host. Matching `xmltv_id` values (`CNN.us@SD`, etc.) live in site channel lists such as:
  - `tvtv.us`
  - `tvguide.com`
  - `xumo.tv`
  - `ontvtonight.com`
  - `directv.com`
  - `distro.tv`
  - `tvpassport.com`

To use those you must run the grabber yourself (Docker/local/another always-on host), then point `EPG_URLS` at your generated `guide.xml.gz`. Running a full iptv-org grab for 1500+ channels every few hours on GitHub free Actions is not recommended (minutes + upstream rate limits).

## Recommended `EPG_URLS` for this project

Keep it lean (one strong source is enough):

```text
https://iptv-epg.org/files/epg-xdbezrvvbu.xml.gz
```

Optional small US packs from [epgshare01](https://epgshare01.online/epgshare01/) can be added, but avoid huge files like `epg_ripper_US_LOCALS1.xml.gz` / `ALL_SOURCES1` on free tier.

## Player URL

```text
https://raw.githubusercontent.com/umarjamilpc/EPG-LIST-GEN/main/epgs/us-epg.xml.gz
```

## Credits

Original project by [BuddyChewChew](https://github.com/BuddyChewChew/multi-epg-light).
Channel id conventions from [iptv-org/epg](https://github.com/iptv-org/epg).
