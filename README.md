# EPG LIST GEN

Builds EPG on GitHub Actions with [iptv-org/epg](https://github.com/iptv-org/epg), then filters to your M3U.

## Schedule
Every **12 hours** (`00:00` and `12:00` UTC) + manual run.

## Secrets
| Secret | Purpose |
|--------|---------|
| `M3U_US` | Playlist URL → category folder `epgs/US/` |
| `EPG_URLS` | Optional extra EPG xml/xml.gz URLs |

Folder name comes from the secret suffix: `M3U_US` → `US`, `M3U_UK` → `UK`.

## Outputs (`epgs/US/`)
| Path | Meaning |
|------|---------|
| `epgs/US/epg.xml.gz` | Filtered guide for your playlist |
| `epgs/US/iptvorg-guide.xml.gz` | Raw iptv-org grab (or `-01`, `-02` if split) |
| `epgs/US/reports/matched.csv` | Channels that got EPG (`tvg_id`, source, duplicates) |
| `epgs/US/reports/unmatched.txt` | Playlist `tvg-id`s with no EPG |
| `epgs/US/reports/duplicates.txt` | Same channel found in multiple sources |
| `epgs/US/reports/summary.txt` | Counts |

## Player URL
```text
https://raw.githubusercontent.com/umarjamilpc/EPG-LIST-GEN/main/epgs/US/epg.xml.gz
```

## Free-tier limits
- 2 days of programmes
- Batched per-site grabs
- Auto-split if `.gz` > 40MB
- Node heap 1536MB
