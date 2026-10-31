param([string]$OutputDirectory='linux/boot/v2_1_sd/rootfs_payloads/picture/pcm',
      [string]$Voice='Microsoft Huihui Desktop')
$ErrorActionPreference='Stop'
$repo=Split-Path -Parent $PSScriptRoot
$out=[IO.Path]::GetFullPath((Join-Path $repo $OutputDirectory))
if (Test-Path -LiteralPath $out) { throw "Refusing to overwrite PCM set: $out" }
Add-Type -AssemblyName System.Speech
$words=[ordered]@{
 zero='零';one='一';two='二';three='三';four='四';five='五';six='六';seven='七';eight='八';nine='九'
 ten='十';hundred='百';thousand='千';point='点';red='红方';black='黑方';king_red='帅';king_black='将'
 advisor='士';elephant='象';knight='马';rook='车';cannon='炮';pawn_red='兵';pawn_black='卒'
 forward='进';backward='退';horizontal='平';front='前';rear='后';middle='中'
 welcome='进入正常下棋界面';newgame='重新开始';winrate='胜率';percent='百分之';think='思考用时';seconds='秒'
}
$speaker=[System.Speech.Synthesis.SpeechSynthesizer]::new()
try {
 $speaker.SelectVoice($Voice)
 $format=[System.Speech.AudioFormat.SpeechAudioFormatInfo]::new(
   16000,[System.Speech.AudioFormat.AudioBitsPerSample]::Sixteen,
   [System.Speech.AudioFormat.AudioChannel]::Mono)
 New-Item -ItemType Directory -Path $out | Out-Null
 $records=[ordered]@{}
 foreach ($name in $words.Keys) {
  $stream=[IO.MemoryStream]::new()
  try {
   $speaker.SetOutputToAudioStream($stream,$format)
   # Huihui rejects SAPI pinyin phonemes. Use a documented homophone for
   # the chess reading ju1; preserve the original character in metadata.
   $spoken=if($name -eq 'rook') { '居' } else { $words[$name] }
   $speaker.Speak($spoken)
   $data=$stream.ToArray()
  } finally { $stream.Dispose() }
  if (!$data.Length -or $data.Length%2 -or $data.Length -gt 320000) { throw "Bad raw PCM size: $name" }
  $path=Join-Path $out ($name+'.pcm')
  [IO.File]::WriteAllBytes($path,$data)
  $records[$name+'.pcm']=@{bytes=$data.Length;sha256=(Get-FileHash -LiteralPath $path -Algorithm SHA256).Hash.ToLowerInvariant();text=$words[$name];spoken_text=$spoken}
 }
 $manifest=[ordered]@{contract_version=1;format='s16le';sample_rate=16000;channels=1;
  voice=$Voice;source='Windows System.Speech';board_validated=$false;files=$records}
 [IO.File]::WriteAllText((Join-Path $out 'manifest.json'),($manifest|ConvertTo-Json -Depth 6)+"`n",[Text.UTF8Encoding]::new($false))
 Write-Output "PICTURE_SPEECH_ASSETS_PASS clips=$($records.Count) board_validated=false"
} finally { $speaker.Dispose() }
