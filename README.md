# EPG LIST GEN: Multi-Playlist EPG Harvester

Creates custom TV guide (EPG) files from multiple M3U playlists.
**Each GitHub secret = one EPG file.**

Based on [BuddyChewChew/multi-epg-light](https://github.com/BuddyChewChew/multi-epg-light).

## How secrets work

| GitHub Secret Name | Secret Value (M3U URL) | Output File |
|--------------------|------------------------|-------------|
| `M3U_HOME` | `https://example.com/home.m3u` | `epgs/home-epg.xml.gz` |
| `M3U_SPORTS` | `https://example.com/sports.m3u` | `epgs/sports-epg.xml.gz` |
| `M3U_KIDS` | `https://example.com/kids.m3u` | `epgs/kids-epg.xml.gz` |

Rule: secret name is `M3U_<FILENAME>` → file is `epgs/<filename>-epg.xml.gz`

---

## Setup example

### 1. Create secrets (one per playlist)

In [EPG-LIST-GEN](https://github.com/umarjamilpc/EPG-LIST-GEN):
**Settings → Secrets and variables → Actions → New repository secret**

**Secret 1**
- Name: `M3U_HOME`
- Value: `https://your-server.com/playlists/home.m3u`

**Secret 2**
- Name: `M3U_SPORTS`
- Value: `https://your-server.com/playlists/sports.m3u`

**Secret 3**
- Name: `M3U_KIDS`
- Value: `https://your-server.com/playlists/kids.m3u`

### 2. Map those secrets in the workflow

Open `.github/workflows/update.yml` and keep matching lines under `env:`:

```yaml
env:
  M3U_HOME: ${{ secrets.M3U_HOME }}
  M3U_SPORTS: ${{ secrets.M3U_SPORTS }}
  M3U_KIDS: ${{ secrets.M3U_KIDS }}
```

If you add a new secret later (e.g. `M3U_MOVIES`), add one more line:

```yaml
  M3U_MOVIES: ${{ secrets.M3U_MOVIES }}
```

### 3. Enable workflow write access
1. **Settings → Actions → General**
2. **Workflow permissions** → **Read and write permissions**
3. Save

### 4. Run it
**Actions → Update Multi EPG → Run workflow**

---

## Player URLs (from the example above)

```text
https://raw.githubusercontent.com/umarjamilpc/EPG-LIST-GEN/main/epgs/home-epg.xml.gz
https://raw.githubusercontent.com/umarjamilpc/EPG-LIST-GEN/main/epgs/sports-epg.xml.gz
https://raw.githubusercontent.com/umarjamilpc/EPG-LIST-GEN/main/epgs/kids-epg.xml.gz
```

---

## Customizing EPG sources

If a guide is empty, edit `URLS = [...]` in `update_epg.py` and add sources that match your playlist `tvg-id` values.

---

## Credits
Original project by [BuddyChewChew](https://github.com/BuddyChewChew/multi-epg-light).
