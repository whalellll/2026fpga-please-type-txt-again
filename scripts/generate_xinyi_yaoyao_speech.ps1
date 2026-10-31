param([Parameter(Mandatory=$true)][string]$OutputDirectory,
      [ValidateRange(1.0,1.2)][double]$SpeakingRate=1.0)
$ErrorActionPreference='Stop'
$repo=Split-Path -Parent $PSScriptRoot
$out=[IO.Path]::GetFullPath($OutputDirectory)
$allowed=@([IO.Path]::GetFullPath((Join-Path $repo 'build/picture-e42-20261025')),
 'E:\xinyi-board-20261025\e42-candidate')
if(!($allowed | Where-Object {$out.StartsWith($_+'\',[StringComparison]::OrdinalIgnoreCase)})){
 throw 'Use the explicit private build junction; no media or old asset writes'
}
if(Test-Path -LiteralPath $out){throw 'Preserve existing PCM and failed candidates'}
New-Item -ItemType Directory -Path $out | Out-Null
New-Item -ItemType Directory -Path (Join-Path $out 'move') | Out-Null
New-Item -ItemType Directory -Path (Join-Path $out 'preview') | Out-Null
Add-Type -AssemblyName System.Runtime.WindowsRuntime
$voice=[Windows.Media.SpeechSynthesis.SpeechSynthesizer,Windows.Media.SpeechSynthesis,ContentType=WindowsRuntime]::AllVoices |
 Where-Object {$_.DisplayName -eq 'Microsoft Yaoyao' -and $_.Language -eq 'zh-CN'}
if(!$voice){throw 'The already-installed offline Yaoyao voice is required; no online fallback'}
$asTask=[System.WindowsRuntimeSystemExtensions].GetMethods() |
 Where-Object {$_.Name -eq 'AsTask' -and $_.IsGenericMethod -and $_.GetParameters().Count -eq 1} |
 Select-Object -First 1
function Wait-LocalOperation($Operation,[Type]$Type){
 $task=$asTask.MakeGenericMethod($Type).Invoke($null,@($Operation))
 if(!$task.Wait(30000)){$Operation.Cancel();throw 'Bounded local synthesis/read exceeded30s'}
 return $task.Result
}
function Read-PcmWave([byte[]]$Data){
 if($Data.Length -lt 44 -or [Text.Encoding]::ASCII.GetString($Data,0,4) -ne 'RIFF' -or
    [Text.Encoding]::ASCII.GetString($Data,8,4) -ne 'WAVE'){throw 'Expected native PCM WAV'}
 $format=$null;$pcm=$null;$at=12
 while($at+8 -le $Data.Length){
  $tag=[Text.Encoding]::ASCII.GetString($Data,$at,4);$size=[BitConverter]::ToUInt32($Data,$at+4);$at+=8
  if([uint64]$at+$size -gt $Data.Length){throw 'WAV chunk exceeds stream'}
  if($tag -eq 'fmt '){
   if($size -lt 16){throw 'Short WAV format'}
   $format=@([BitConverter]::ToUInt16($Data,$at),[BitConverter]::ToUInt16($Data,$at+2),
    [BitConverter]::ToUInt32($Data,$at+4),[BitConverter]::ToUInt16($Data,$at+14))
  }
  if($tag -eq 'data'){$pcm=[byte[]]::new($size);[Array]::Copy($Data,$at,$pcm,0,$size)}
  $at+=$size+($size%2)
 }
 if(!$format -or $format[0] -ne 1 -or $format[1] -ne 1 -or $format[2] -ne 16000 -or
    $format[3] -ne 16 -or !$pcm -or $pcm.Length%2){throw 'Native16000Hz/S16/mono required; never resample'}
 return ,$pcm
}
function Trim-QuietEdges([byte[]]$Pcm){
 $first=-1;$last=-1
 for($i=0;$i -lt $Pcm.Length/2;$i++){
  if([Math]::Abs([int][BitConverter]::ToInt16($Pcm,2*$i)) -gt 32){
   if($first -lt 0){$first=$i};$last=$i
  }
 }
 if($first -lt 0){throw 'Synthesized silence'}
 $first=[Math]::Max(0,$first-240);$last=[Math]::Min($Pcm.Length/2-1,$last+240)
 $data=[byte[]]::new(2*($last-$first+1));[Array]::Copy($Pcm,2*$first,$data,0,$data.Length)
 return @{data=$data;first=$first;last=$last;source_samples=$Pcm.Length/2}
}
function Wave-FromPcm([byte[]]$Pcm){
 $stream=[IO.MemoryStream]::new();$writer=[IO.BinaryWriter]::new($stream)
 $writer.Write([Text.Encoding]::ASCII.GetBytes('RIFF'));$writer.Write([uint32]($Pcm.Length+36))
 $writer.Write([Text.Encoding]::ASCII.GetBytes('WAVEfmt '));$writer.Write([uint32]16)
 $writer.Write([uint16]1);$writer.Write([uint16]1);$writer.Write([uint32]16000);$writer.Write([uint32]32000)
 $writer.Write([uint16]2);$writer.Write([uint16]16);$writer.Write([Text.Encoding]::ASCII.GetBytes('data'))
 $writer.Write([uint32]$Pcm.Length);$writer.Write($Pcm);$writer.Flush();$data=$stream.ToArray()
 $writer.Dispose();$stream.Dispose();return ,$data
}
$words=[ordered]@{
 one='一';two='二';three='三';four='四';five='五';six='六';seven='七';eight='八';nine='九'
 king_red='帅';king_black='将';advisor='士';elephant='象';knight='马';rook='车';cannon='炮'
 pawn_red='兵';pawn_black='卒';forward='进';backward='退';horizontal='平';front='前';rear='后';middle='中'
}
$phrases=[ordered]@{cannon='炮二平五';knight='马二进三';rook='车九进一';black_knight='马八进七';front_rook='前车进一'}
$records=[ordered]@{};$previews=[ordered]@{};$over=@()
$speaker=[Windows.Media.SpeechSynthesis.SpeechSynthesizer]::new()
$speaker.Voice=$voice;$speaker.Options.SpeakingRate=$SpeakingRate
try {
 foreach($kind in @('token','phrase')){
  $items=if($kind -eq 'token'){$words}else{$phrases}
  foreach($name in $items.Keys){
   $text=$items[$name]
   # Chess ju1, using the same documented homophone as the existing assets.
   $spoken=$text.Replace('车','居')
   $stream=Wait-LocalOperation ($speaker.SynthesizeTextToStreamAsync($spoken)) ([Windows.Media.SpeechSynthesis.SpeechSynthesisStream])
   $reader=$null
   try {
    $reader=[Windows.Storage.Streams.DataReader,Windows.Storage.Streams,ContentType=WindowsRuntime]::new($stream.GetInputStreamAt(0))
    $loaded=Wait-LocalOperation ($reader.LoadAsync([uint32]$stream.Size)) ([uint32])
    $wav=[byte[]]::new($loaded);$reader.ReadBytes($wav)
   } finally {if($reader){$reader.Dispose()};$stream.Dispose()}
   $pcm=Read-PcmWave $wav;$trim=Trim-QuietEdges $pcm;$data=$trim.data
   $dest=if($kind -eq 'token'){'move/'+$name+'.pcm'}else{'preview/'+$name+'.pcm'}
   [IO.File]::WriteAllBytes((Join-Path $out $dest),$data)
   $wavName=if($kind -eq 'token'){'preview/token-'+$name+'.wav'}else{'preview/phrase-'+$name+'.wav'}
   [IO.File]::WriteAllBytes((Join-Path $out $wavName),(Wave-FromPcm $data))
   $row=[ordered]@{text=$text;spoken_text=$spoken;samples=$data.Length/2;bytes=$data.Length;duration_ms=$data.Length/32.0;
    sha256=(Get-FileHash -LiteralPath (Join-Path $out $dest) -Algorithm SHA256).Hash.ToLowerInvariant();
    source_samples=$trim.source_samples;first=$trim.first;last=$trim.last;wav=$wavName}
   if($kind -eq 'token'){
    $records[$name+'.pcm']=$row
    if($data.Length -gt 7680){$over+=$name}
   }else{$previews[$name]=$row}
  }
 }
 $max=0;foreach($clip in $records.Values){if($clip['samples'] -gt $max){$max=$clip['samples']}}
 $manifest=[ordered]@{schema='xinyi-yaoyao-offline-candidate-v1';format='s16le';sample_rate=16000;channels=1;
  voice=$voice.DisplayName;voice_id=$voice.Id;source='Installed Windows WinRT SpeechSynthesis';native_rate=$SpeakingRate;
  resampled=$false;interior_trimmed=$false;edge_threshold=32;edge_context_samples=240;token_max_samples=3840;
  phrase_tokens=4;priming_samples=64;max_payload_and_priming_ms=4*$max/16.0+4;
  original_helper_compatible=($over.Count -eq 0);over_budget=$over;files=$records;phrase_previews=$previews;
  automatically_played=$false;board_tested=$false;hearing_verified=$false;physical_1000ms_pass=$false;
  latency_scope='PCM duration only, excludes result scheduling/startup/device/cleanup.1s from result available to complete playback is not proven.'}
 [IO.File]::WriteAllText((Join-Path $out 'manifest.json'),($manifest|ConvertTo-Json -Depth 8)+"`n",[Text.UTF8Encoding]::new($false))
 Copy-Item -LiteralPath $PSCommandPath -Destination (Join-Path $out 'generate_xinyi_yaoyao_speech.ps1')
 Write-Output ('YAOYAO_OFFLINE_CANDIDATE tokens='+$records.Count+' over240ms='+$over.Count+' hardware_used=false autoplay=false')
} finally {$speaker.Dispose()}
