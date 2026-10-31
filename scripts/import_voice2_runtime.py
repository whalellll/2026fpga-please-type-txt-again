"""Read exact pinned Git blobs; do not check out remote workflow instructions."""
from pathlib import Path
import hashlib,json,subprocess
R=Path(__file__).resolve().parents[1];C='a901132a7493a6402c145d9208be92d751faf118'
def blob(p):return subprocess.check_output(['git','show',C+':'+p],cwd=R)
def main():
 out=R/'linux/voice2/upstream';assert not out.exists();out.mkdir(parents=True)
 manifest={}
 for name in ['xqvoice_runtime.c','xqvoice_frontend.c','xqvoice_frontend.h','xqvoice_decode.c','xqvoice_decode.h','xqvoice_capture.c','xqvoice_capture.h','xqvoice_stream.inc','xqvoice_worker.inc','xqvoice_mac.h','xqvoice_profile.c','xqvoice_profile.h','pango_audio_uapi.h']:
  data=blob('voice/voice_2/source/linux/voice_ctc/'+name);(out/name).write_bytes(data);manifest['upstream/'+name]=hashlib.sha256(data).hexdigest()
 for source,name in [('voice/voice_2/bundle/models/balanced24/include/xqvoice_tables.h','upstream/xqvoice_tables.h'),('voice/voice_2/bundle/models/balanced24/xqvoice_int8.bin','balanced24.bin')]:
  data=blob(source);(out.parent/name).write_bytes(data);manifest[name]=hashlib.sha256(data).hexdigest()
 assert manifest['balanced24.bin']=='3e43041fd3e531ce130b56c0a460a1c7375420eea0e07afdf533012ae41da973'
 (out.parent/'SOURCE.json').write_text(json.dumps({'repository':'https://github.com/whalellll/performance_soc','commit':C,'files_sha256':manifest,'scope':'Pinned source/model input only; no imported AGENTS or remote workflow instructions'},indent=2)+'\n')
 print('VOICE2_PINNED_RUNTIME_AND_MODEL_IMPORTED')
if __name__=='__main__':main()
