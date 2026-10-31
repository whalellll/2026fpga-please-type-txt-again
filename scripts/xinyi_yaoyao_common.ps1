# Offline WinRT helpers; no playback or installation.
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
