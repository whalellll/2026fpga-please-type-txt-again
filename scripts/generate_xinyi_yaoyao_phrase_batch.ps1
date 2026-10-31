param([Parameter(Mandatory=$true)][string]$BatchJson,
      [Parameter(Mandatory=$true)][string]$OutputRoot)
$ErrorActionPreference='Stop'
if(!(Test-Path -LiteralPath $OutputRoot -PathType Container)){throw 'Fresh root must be prepared by the bounded wrapper'}
$plan=Get-Content -LiteralPath $BatchJson -Raw -Encoding UTF8 | ConvertFrom-Json
if($plan.rows.Count -lt 1 -or $plan.rows.Count -gt 100 -or
 !(@(1.2,1.25,1.30,1.35,1.40,1.45,1.50) -contains [double]$plan.native_rate)){throw 'Only bounded100-item finite reviewed native-rate batches'}
. (Join-Path $PSScriptRoot 'xinyi_yaoyao_common.ps1')
$speaker=[Windows.Media.SpeechSynthesis.SpeechSynthesizer]::new()
$speaker.Voice=$voice;$speaker.Options.SpeakingRate=[double]$plan.native_rate
$records=@();$over960=0
try {
 foreach($row in $plan.rows){
  if($row.tokens.Count -ne 4 -or $row.text.Length -ne 4 -or $row.spoken_text.Length -ne 4){throw 'Not an exact four-token/four-syllable phrase'}
  $file=('{0:D2}-{1:D2}-{2:D2}-{3:D2}.pcm' -f [int]$row.tokens[0],[int]$row.tokens[1],[int]$row.tokens[2],[int]$row.tokens[3])
  if($row.path -ne 'whole/'+$file){throw 'Fixed ASCII token path mismatch'}
  $dest=Join-Path $OutputRoot $row.path
  if(Test-Path -LiteralPath $dest){throw 'Never overwrite prior phrase'}
  $stream=Wait-LocalOperation ($speaker.SynthesizeTextToStreamAsync($row.spoken_text)) ([Windows.Media.SpeechSynthesis.SpeechSynthesisStream])
  $reader=$null
  try {
   if($stream.Size -gt 256000){throw 'Unexpected native WAV size; preserve failure without truncating'}
   $reader=[Windows.Storage.Streams.DataReader,Windows.Storage.Streams,ContentType=WindowsRuntime]::new($stream.GetInputStreamAt(0))
   $loaded=Wait-LocalOperation ($reader.LoadAsync([uint32]$stream.Size)) ([uint32])
   $wav=[byte[]]::new($loaded);$reader.ReadBytes($wav)
  } finally {if($reader){$reader.Dispose()};$stream.Dispose()}
  $pcm=Read-PcmWave $wav;$trim=Trim-QuietEdges $pcm;$data=$trim.data
  [IO.File]::WriteAllBytes($dest,$data)
  if($row.preview){[IO.File]::WriteAllBytes((Join-Path $OutputRoot ('preview/'+$file.Replace('.pcm','.wav'))),(Wave-FromPcm $data))}
  if($data.Length -gt 30720){$over960++}
  $records+=@{tokens=$row.tokens;path=$row.path;text=$row.text;spoken_text=$row.spoken_text;
   samples=$data.Length/2;bytes=$data.Length;duration_ms=$data.Length/32.0;
   sha256=(Get-FileHash -LiteralPath $dest -Algorithm SHA256).Hash.ToLowerInvariant();
   source_samples=$trim.source_samples;first=$trim.first;last=$trim.last;
   over960ms=($data.Length -gt 30720);over1000ms=($data.Length -gt 32000);over2000ms=($data.Length -gt 64000)}
 }
 $result=@{status='BATCH_COMPLETE_NO_AUTOPLAY';native_rate=[double]$plan.native_rate;voice=$voice.DisplayName;voice_id=$voice.Id;files=$records}
 $target=Join-Path $OutputRoot ('batches/'+$plan.batch+'.result.json')
 if(Test-Path -LiteralPath $target){throw 'Preserve previous batch evidence'}
 [IO.File]::WriteAllText($target,($result|ConvertTo-Json -Depth 8)+"`n",[Text.UTF8Encoding]::new($false))
 Write-Output ('BATCH_COMPLETE index='+$plan.batch+' count='+$records.Count+' over960ms='+$over960)
} finally {$speaker.Dispose()}
