# Requires installed 64-bit JV-Link. No credentials accepted or printed.
# A fresh output directory is mandatory. EOF is not an atomic-snapshot guarantee.
param(
  [Parameter(Mandatory)][ValidateSet('0B12','0B15','0B41')][string]$DataSpec,
  [Parameter(Mandatory)][ValidatePattern('^[0-9]{16}$')][string]$RaceKey,
  [Parameter(Mandatory)][string]$OutputDirectory
)
$ErrorActionPreference = 'Stop'
$probeOutput = [IO.Path]::GetFullPath($OutputDirectory)
New-Item -ItemType Directory -Path $probeOutput -ErrorAction Stop | Out-Null
$probe = [ordered]@{ purpose='bounded_single_race_capture'; transport='JVGets_byte_array'; dataspec=$DataSpec; race_key=$RaceKey; started_at=[DateTimeOffset]::UtcNow.ToString('o'); records=0; complete=$false; files=@() }
$jv = $null
try {
  $jv = New-Object -ComObject JVDTLab.JVLink
  $probe.init_code = $jv.JVInit('UNKNOWN')
  if ($probe.init_code -ne 0) { throw ('JVInit failed: ' + $probe.init_code) }
  $probe.open_code = $jv.JVRTOpen($probe.dataspec, $probe.race_key)
  if ($probe.open_code -ne 0) { throw ('JVRTOpen failed: ' + $probe.open_code) }
  $timer = [Diagnostics.Stopwatch]::StartNew()

  while ($timer.Elapsed.TotalSeconds -lt 30 -and $probe.records -lt 2000) {
    [object]$buffer = [byte[]]::new(110000)
    [int]$bufferSize = 110000
    $filename = ''
    $code = $jv.JVGets([ref]$buffer, $bufferSize, [ref]$filename)
    if ($code -eq 0) { $probe.complete=$true; break }
    if ($code -eq -1) { continue }
    if ($code -eq -3) { Start-Sleep -Milliseconds 250; continue }
    if ($code -lt 0) { throw ('JVGets failed: ' + $code) }
    if ($buffer -isnot [byte[]]) { throw "JVGets did not return a managed byte array" }; $bytes = $buffer
    if ($bytes.Length -lt $code) { throw 'JVGets length mismatch' }
    $recordPath = Join-Path $probeOutput ('record-{0:D4}.bin' -f $probe.records)
    $stream = [IO.File]::Open($recordPath, [IO.FileMode]::CreateNew)
    try { $stream.Write($bytes, 0, $code) } finally { $stream.Dispose() }
    $probe.files += [ordered]@{ file=[IO.Path]::GetFileName($recordPath); retrieved_at=[DateTimeOffset]::UtcNow.ToString("o"); size=$code; sha256=(Get-FileHash -Algorithm SHA256 -LiteralPath $recordPath).Hash.ToLowerInvariant() }; $probe.records++
  }
  if (-not $probe.complete) { throw 'Bounded read stopped before EOF' }
} catch { $probe.error = $_.Exception.Message }
finally {
  if ($null -ne $jv) {
    try { $probe.close_code=$jv.JVClose(); if ($probe.close_code -ne 0) { $probe.error="JVClose failed" } } catch { $probe.close_error=$_.Exception.Message }
    [void][Runtime.InteropServices.Marshal]::FinalReleaseComObject($jv)
  }
  $probe.finished_at=[DateTimeOffset]::UtcNow.ToString('o')
  $probe | ConvertTo-Json -Depth 4 | Set-Content -Encoding utf8 (Join-Path $probeOutput 'probe.json')
  [pscustomobject]$probe | Select-Object dataspec,race_key,records,complete,init_code,open_code,close_code,error | ConvertTo-Json
}
if ($probe.error -or $probe.close_error -or -not $probe.complete) { exit 1 }
