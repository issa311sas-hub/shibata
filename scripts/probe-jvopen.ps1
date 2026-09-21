# Bounded diagnostic of the accumulated-data interface; never exports training rows.
param([Parameter(Mandatory)][ValidatePattern('^[0-9]{14}-[0-9]{14}$')][string]$FromTime,
      [Parameter(Mandatory)][string]$OutputPath,
      [switch]$Capture)
$ErrorActionPreference='Stop'
$parts=$FromTime.Split('-')
$culture=[Globalization.CultureInfo]::InvariantCulture
$begin=[DateTime]::ParseExact($parts[0],'yyyyMMddHHmmss',$culture)
$end=[DateTime]::ParseExact($parts[1],'yyyyMMddHHmmss',$culture)
if ($end -le $begin -or ($end-$begin).TotalDays -gt 1) { throw 'Probe window must be positive and at most one day' }
$stream=[IO.File]::Open([IO.Path]::GetFullPath($OutputPath),[IO.FileMode]::CreateNew)
$jv=$null
$report=[ordered]@{purpose='historical_access_probe_only';dataspec='RACE';fromtime=$FromTime;option=1;started_at=[DateTimeOffset]::UtcNow.ToString('o');training_ready=$false}
try {
  $jv=New-Object -ComObject JVDTLab.JVLink
  $report.init_code=$jv.JVInit('UNKNOWN')
  if ($report.init_code -ne 0) { throw "JVInit failed: $($report.init_code)" }
  [int]$readCount=0; [int]$downloadCount=0; [string]$lastTimestamp=''
  $report.open_code=$jv.JVOpen('RACE',$FromTime,1,[ref]$readCount,[ref]$downloadCount,[ref]$lastTimestamp)
  $report.read_count=$readCount
  $report.download_count=$downloadCount
  $report.last_file_timestamp=$lastTimestamp
  $report.total_read_kb=$jv.m_TotalReadFilesize
  if ($Capture -and $report.open_code -eq 0) {
    if ($readCount -gt 30 -or $report.total_read_kb -gt 16384) { throw 'Capture exceeds 30 files or 16 MiB' }
    $folder=[IO.Path]::GetFullPath($OutputPath)+'.records'
    New-Item -ItemType Directory -Path $folder -ErrorAction Stop | Out-Null
    $report.records=@(); $report.complete=$false
    $timer=[Diagnostics.Stopwatch]::StartNew()
    while ($timer.Elapsed.TotalSeconds -lt 90 -and $report.records.Count -lt 20000) {
      [object]$buffer=[byte[]]::new(110000); $filename=''
      $code=$jv.JVGets([ref]$buffer,110000,[ref]$filename)
      if ($code -eq 0) { $report.complete=$true; break }
      if ($code -eq -1) { continue }
      if ($code -eq -3) { Start-Sleep -Milliseconds 250; continue }
      if ($code -lt 0) { throw "JVGets failed: $code" }
      if ($buffer -isnot [byte[]] -or $buffer.Length -lt $code) { throw 'Invalid byte buffer' }
      $name='record-{0:D4}.bin' -f $report.records.Count
      $recordPath=Join-Path $folder $name
      $recordStream=[IO.File]::Open($recordPath,[IO.FileMode]::CreateNew)
      try { $recordStream.Write($buffer,0,$code) } finally { $recordStream.Dispose() }
      $report.records += [ordered]@{file=$name;source_file=$filename;size=$code;retrieved_at=[DateTimeOffset]::UtcNow.ToString('o');sha256=(Get-FileHash -LiteralPath $recordPath -Algorithm SHA256).Hash.ToLowerInvariant()}
    }
    if (-not $report.complete) { throw 'Bounded capture stopped before EOF' }
  }
} catch { $report.error=$_.Exception.Message }
finally {
  if ($null -ne $jv) {
    try { $report.close_code=$jv.JVClose() } catch { $report.close_error=$_.Exception.Message }
    [void][Runtime.InteropServices.Marshal]::FinalReleaseComObject($jv)
  }
  $report.finished_at=[DateTimeOffset]::UtcNow.ToString('o')
  $json=$report | ConvertTo-Json -Depth 4
  $bytes=[Text.Encoding]::UTF8.GetBytes($json)
  try { $stream.Write($bytes,0,$bytes.Length) } finally { $stream.Dispose() }
  [pscustomobject]$report | Select-Object dataspec,fromtime,open_code,read_count,total_read_kb,complete,error,close_code | ConvertTo-Json
}
if ($report.error -or $report.close_error) { exit 1 }

