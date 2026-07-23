# EPG LIST GEN

Builds US EPG on **GitHub Actions** with [iptv-org/epg](https://github.com/iptv-org/epg), then filters to your M3U.

## Free-tier settings
- **Once daily** at 06:00 UTC (+ manual run)
- **2 days** of programmes only (`EPG_DAYS=2`)
- Batched per-site grabs (avoids OOM)
- Auto-split if a guide `.gz` exceeds **40MB**
- Node heap capped at **1536MB**

## Secrets
| Secret | Required | Purpose |
|--------|----------|---------|
| `M3U_US` | yes | Playlist URL → `epgs/us-epg.xml.gz` |
| `EPG_URLS` | no | Optional extra xml/xml.gz URLs |

## Outputs
| File | Meaning |
|------|---------|
| `epgs/us-iptvorg-guide.xml.gz` | Raw iptv-org grab (or `-01`, `-02` if split) |
| `epgs/us-epg.xml.gz` | Filtered to your playlist |

## Player URL
```text
https://raw.githubusercontent.com/umarjamilpc/EPG-LIST-GEN/main/epgs/us-epg.xml.gz
```

## Workflow
**Actions → Build US EPG (iptv-org) → Run workflow**
