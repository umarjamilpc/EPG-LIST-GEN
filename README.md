# EPG LIST GEN

GitHub Actions project that builds TV guide (EPG) files for IPTV playlists and publishes them under `epgs/<CATEGORY>/`.

Based on ideas from [BuddyChewChew/multi-epg-light](https://github.com/BuddyChewChew/multi-epg-light). Guide data is grabbed with [iptv-org/epg](https://github.com/iptv-org/epg) (a grabber, not a public feed host).

**Live repo:** [umarjamilpc/EPG-LIST-GEN](https://github.com/umarjamilpc/EPG-LIST-GEN)

---

## Why README was overwritten before

The old Action did `git commit --amend` + `git push --force`. If a code/README commit landed while a ~20 minute build was running, the Action still had the old checkout and **force-pushed over** your commit.

**Fixed:** Actions now use a normal commit + `git pull --rebase` + regular `git push` (no amend, no force).

---

## What this repo does

1. Optionally runs the **iptv-org grabber** (controlled by secret `EPG_GRABBER`).
2. Saves the raw grab under `epgs/<CATEGORY>/grabber-raw-guide*.xml.gz`.
3. Filters that grab to your M3U → `grabber-epg.xml.gz` + grabber reports.
4. Downloads **`EPG_URLS`** (and M3U `url-tvg` if present) → `urls-epg.xml.gz` + urls reports.
5. Merges both (grabber wins on duplicate channels) → `epgs/<CATEGORY>/merge/merged-epg.xml.gz` (+ parts if large).
6. Commits `epgs/` without rewriting history.

**Player URL (US merged guide):**

```text
https://raw.githubusercontent.com/umarjamilpc/EPG-LIST-GEN/main/epgs/US/merge/merged-epg.xml.gz
```

---

## Schedule

| Trigger | When |
|---------|------|
| Cron | Every **12 hours**: `00:00` and `12:00` UTC |
| Manual | Actions → **Build US EPG (iptv-org)** → Run workflow |

Typical full grab: ~20 minutes. Timeout: 120 minutes.

---

## Secrets

GitHub → **Settings → Secrets and variables → Actions**

| Secret | Required | Values | Purpose |
|--------|----------|--------|---------|
| `M3U_US` | Yes | playlist URL | US M3U → folder `epgs/US/` |
| `EPG_GRABBER` | Recommended | `true` or `false` | Turn iptv-org grabber **on/off** |
| `EPG_URLS` | Optional | one URL per line | Extra XML/XML.GZ guide URLs |
| `EPG_USE_DEFAULTS` | Optional | `true` / `false` | Also merge built-in lean URL defaults (manual filter workflow) |

### `EPG_GRABBER`

| Value | Behavior |
|-------|----------|
| `true` (default if unset) | Clone iptv-org/epg, batched grab, write `grabber-raw-guide`, filter to `grabber-epg` |
| `false` | Skip grab steps; only use `EPG_URLS` (+ existing raw guides are ignored when false) |

```bash
# Enable
echo true | gh secret set EPG_GRABBER -R umarjamilpc/EPG-LIST-GEN

# Disable (URLs-only, much faster)
echo false | gh secret set EPG_GRABBER -R umarjamilpc/EPG-LIST-GEN
```

### Category folders from secret names

| Secret | Folder |
|--------|--------|
| `M3U_US` | `epgs/US/` |
| `M3U_UK` | `epgs/UK/` |

Rule: `M3U_<NAME>` → `epgs/<NAME>/`.  
Do **not** create a secret named `M3U_URL` (reserved / was wrongly creating `epgs/URL/`).

### `EPG_URLS`

Stored only as a GitHub secret (not in git). Wired into both workflows → `update_epg.py` → `parse_extra_epg_urls()`.

Recommended value:

```text
https://iptv-epg.org/files/epg-xdbezrvvbu.xml.gz
```

(Optional) you can also list the published raw grab URL; the Action prefers the local `grabber-raw-guide*.xml.gz` file when grabber ran in the same job.

---

## Output layout (`epgs/US/`)

```text
epgs/US/
  grabber-raw-guide.xml.gz     # Unfiltered iptv-org grab (or -part-01, -part-02 if split)
  grabber-epg.xml.gz           # Playlist-filtered from grabber only
  urls-epg.xml.gz              # Playlist-filtered from EPG_URLS / M3U urls only
  merge/
    merged-epg.xml.gz          # Combined guide for players (grabber priority, then urls)
    merged-epg-part-01.xml.gz  # Only if a single file would exceed ~40MB gz
  reports/
    grabber-matched.csv
    grabber-unmatched.txt
    grabber-duplicates.txt
    grabber-summary.txt
    urls-matched.csv
    urls-unmatched.txt
    urls-duplicates.txt
    urls-summary.txt
    merge-matched.csv
    merge-unmatched.txt
    merge-duplicates.txt
    merge-summary.txt
```

### File name meanings

| File | Meaning |
|------|---------|
| `grabber-raw-guide` | Full site grab before playlist filter |
| `grabber-epg` | Only channels from your M3U that matched the grabber |
| `urls-epg` | Only channels from your M3U that matched URL guides |
| `merge/merged-epg` | Final combined guide (use this in the player) |

Split parts use `-part-01`, `-part-02`, … when gzip size exceeds ~40 MB.

### Report columns (`*-matched.csv`)

| Column | Meaning |
|--------|---------|
| `tvg_id` | Id from your M3U |
| `epg_id_matched` | Id found in the EPG XML |
| `source` | Which file/URL supplied the data |
| `duplicate_sources` | Other sources that also had this channel |

---

## Workflows

### 1. `Build US EPG (iptv-org)` — scheduled

1. Resolve `EPG_GRABBER`  
2. If **true**: clone iptv-org → build channels → batched grab → `publish_guides.py` → `grabber-raw-guide*.xml.gz`  
3. Always: `update_epg.py` → grabber-epg + urls-epg + merge + reports  
4. Normal commit + rebase + push (keeps README/code safe)

### 2. `Update Multi EPG` — manual filter only

Skips the grabber job steps. Still respects `EPG_GRABBER` inside `update_epg.py` (whether to load existing `grabber-raw-guide` files).

---

## Pipeline scripts

| Script | Purpose |
|--------|---------|
| `build_us_channels.py` | Map playlist ids → iptv-org site channels (`PLAYLIST_URL` / `M3U_US`) |
| `split_channels_by_site.py` | One channels file per site |
| `run_batched_grab.sh` / `.ps1` | Per-site grab (avoids OOM) |
| `publish_guides.py` | Write `grabber-raw-guide*.xml.gz` |
| `update_epg.py` | Filter grabber + URLs, reports, merge |

### Repo tree (tracked)

```text
.github/workflows/
  build-us-epg.yml      # scheduled grab + filter
  update.yml            # manual filter-only
build_us_channels.py
split_channels_by_site.py
run_batched_grab.sh
run_batched_grab.ps1
publish_guides.py
update_epg.py
README.md
epgs/US/
  grabber-raw-guide.xml.gz
  grabber-epg.xml.gz          # after filter run
  urls-epg.xml.gz
  merge/merged-epg.xml.gz
  reports/...
```

---

## Matching logic

1. Exact `tvg-id` (case-insensitive)  
2. Alias without `@…` suffix  
3. Channel slug (before first `.`)

On merge, **grabber wins**; URL sources only fill channels the grabber missed. Programmes come only from the winning source per channel.

---

## Free-tier limits

| Setting | Value |
|---------|-------|
| Schedule | 12 hours |
| Days | 2 |
| Grab | Batched per site |
| Node heap | 1536 MB |
| Split | gz > ~40 MB |
| `tvtv.us` | Skipped (HTTP 403) |

Turn grabber **off** (`EPG_GRABBER=false`) to save Actions minutes when you only need URL guides.

---

## Manual runs

- Full rebuild: **Build US EPG (iptv-org)**  
- Filter/merge only: **Update Multi EPG (manual only)**  

---

## Local development

```powershell
pip install requests lxml
# ... clone iptv-org/epg and npm install if grabbing ...

$env:M3U_US = "https://your-playlist.m3u"
$env:PLAYLIST_URL = $env:M3U_US
$env:EPG_CATEGORY = "US"
$env:EPG_GRABBER = "true"
$env:EPG_URLS = "https://iptv-epg.org/files/epg-xdbezrvvbu.xml.gz"

python build_us_channels.py
python split_channels_by_site.py
powershell -File run_batched_grab.ps1
python publish_guides.py
python update_epg.py
```

---

## Adding another category (filter side)

1. Secret `M3U_UK` = playlist URL  
2. Add `M3U_UK: ${{ secrets.M3U_UK }}` under filter `env:` in workflows  
3. Outputs appear under `epgs/UK/` with the same file names  

iptv-org **grab** path is still US-oriented (`EPG_CATEGORY: US`) unless you extend the build workflow.

---

## Troubleshooting

| Symptom | Likely cause |
|---------|----------------|
| README/code vanished after Action | Fixed — was amend+force-push; pull latest `main` |
| Empty `grabber-epg` | `EPG_GRABBER=false`, or no matching ids / grab failed |
| Empty `urls-epg` | Missing `EPG_URLS` and no M3U `url-tvg` |
| `epgs/URL/` folder | Old bug from env `M3U_URL`; removed — use `PLAYLIST_URL` |
| OOM during grab | Keep batched grab; do not raise days/connections much |
