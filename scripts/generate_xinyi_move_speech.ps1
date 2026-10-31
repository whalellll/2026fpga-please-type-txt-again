param([Parameter(Mandatory=$true)][string]$OutputDirectory,
      [int]$Rate=5)
$ErrorActionPreference='Stop'
if($Rate -lt 0 -or $Rate -gt 8){throw 'Rate outside reviewed finite range'}
$repo=Split-Path -Parent $PSScriptRoot
$source=Join-Path $repo 'linux/boot/v2_1_sd/rootfs_payloads/picture/pcm/manifest.json'
$inputManifest=Get-Content -LiteralPath $source -Raw -Encoding UTF8 | ConvertFrom-Json
$out=[IO.Path]::GetFullPath($OutputDirectory)
if(Test-Path -LiteralPath $out){throw 'Refusing to overwrite speech assets'}
New-Item -ItemType Directory -Path $out | Out-Null
Add-Type -AssemblyName System.Speech
$speaker=[System.Speech.Synthesis.SpeechSynthesizer]::new()
$names=@('one','two','three','four','five','six','seven','eight','nine',
 'king_red','king_black','advisor','elephant','knight','rook','cannon',
 'pawn_red','pawn_black','forward','backward','horizontal','front','rear','middle')
$records=[ordered]@{};$failed=@()
try {
 $speaker.SelectVoice($inputManifest.voice);$speaker.Rate=$Rate
 $format=[System.Speech.AudioFormat.SpeechAudioFormatInfo]::new(16000,
  [System.Speech.AudioFormat.AudioBitsPerSample]::Sixteen,[System.Speech.AudioFormat.AudioChannel]::Mono)
 foreach($name in $names){
  $stream=[IO.MemoryStream]::new()
  try {$speaker.SetOutputToAudioStream($stream,$format)
   $speaker.Speak($inputManifest.files.($name+'.pcm').spoken_text);$raw=$stream.ToArray()
  } finally {$stream.Dispose()}
  # Remove only quiet boundaries; preserve every interior sample. 15 ms of
  # original context on each edge protects consonants and vowel decay.
  $first=-1;$last=-1
  for($i=0;$i -lt $raw.Length/2;$i++){
   if([Math]::Abs([int][BitConverter]::ToInt16($raw,2*$i)) -gt 32){
    if($first -lt 0){$first=$i};$last=$i
   }
  }
  if($first -lt 0){throw "Silent token: $name"}
  $first=[Math]::Max(0,$first-240);$last=[Math]::Min($raw.Length/2-1,$last+240)
  $data=[byte[]]::new(2*($last-$first+1));[Array]::Copy($raw,2*$first,$data,0,$data.Length)
  $path=Join-Path $out ($name+'.pcm');[IO.File]::WriteAllBytes($path,$data)
  $records[$name+'.pcm']=[ordered]@{samples=$data.Length/2;bytes=$data.Length;
   sha256=(Get-FileHash -LiteralPath $path -Algorithm SHA256).Hash.ToLowerInvariant();
   spoken_text=$inputManifest.files.($name+'.pcm').spoken_text;
   source_samples=$raw.Length/2;first=$first;last=$last}
  if($data.Length -gt 7680){$failed+=$name}
 }
} finally {$speaker.Dispose()}
$manifest=[ordered]@{schema='xinyi-move-pcm-v1';format='s16le';sample_rate=16000;channels=1;
 voice=$inputManifest.voice;native_rate=$Rate;edge_threshold=32;edge_context_samples=240;
 token_max_samples=3840;phrase_tokens=4;priming_samples=64;
 max_payload_and_priming_ms=964;board_tested=$false;
 source_manifest_sha256=(Get-FileHash -LiteralPath $source -Algorithm SHA256).Hash.ToLowerInvariant();
 files=$records;over_budget=$failed}
[IO.File]::WriteAllText((Join-Path $out 'manifest.json'),($manifest|ConvertTo-Json -Depth 8)+"`n",[Text.UTF8Encoding]::new($false))
if($failed.Count){throw ('Over-budget tokens retained: '+($failed -join ','))}
Write-Output "MOVE_PCM_GENERATED tokens=$($records.Count) max_ms=964 hardware_used=false"
