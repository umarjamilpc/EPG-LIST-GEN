# Batched iptv-org grab by site (low memory)
$ErrorActionPreference = "Stop"
$env:NODE_OPTIONS = "--max-old-space-size=1536"

$epg = "e:\CURSOR\EPG-LIST\iptv-org-epg"
$bySite = "e:\CURSOR\EPG-LIST\iptv-org-work\by_site"
$outDir = "e:\CURSOR\EPG-LIST\iptv-org-work\site_guides"
New-Item -ItemType Directory -Force -Path $outDir | Out-Null

# Largest / most useful first
$sites = @(
  "tvpassport.com",
  "pluto.tv",
  "xumo.tv",
  "tvguide.com",
  "plex.tv",
  "i.mjh.nz",
  "watchyour.tv",
  "gatotv.com",
  "ontvtonight.com",
  "watch.whaletvplus.com",
  "distro.tv",
  "mi.tv"
)

Set-Location $epg

foreach ($site in $sites) {
  $safe = ($site -replace '[^a-zA-Z0-9._-]+', '_')
  $channels = Join-Path $bySite "$safe.channels.xml"
  if (-not (Test-Path $channels)) {
    Write-Host "SKIP missing $channels"
    continue
  }
  $outXml = Join-Path $outDir "$safe.xml"
  $outGz = Join-Path $outDir "$safe.xml.gz"
  if ((Test-Path $outGz) -and ((Get-Item $outGz).Length -gt 1000)) {
    Write-Host "SKIP already have $safe"
    continue
  }
  Write-Host "=== GRAB $site ==="
  npm run grab --- --channels="$channels" --output="$outXml" --gzip="$outGz" --days=1 --maxConnections=2 --timeout=20000
  if ($LASTEXITCODE -ne 0) {
    Write-Host "WARN grab failed for $site exit=$LASTEXITCODE"
  }
}

Write-Host "All site grabs finished"
