"""Close the experimental RAM deployment record without accepting M0/P23."""
import hashlib,json
from datetime import datetime,timezone
from pathlib import Path
HERE=Path(__file__).resolve().parent;REPO=HERE.parents[1]
OUT=REPO/'docs/validation/picture-p21-runtime-20261020';BUILD=REPO/'build/picture-p21-native'
def read(p):return json.loads(p.read_text())
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
installed={line.split()[1]:line.split()[0] for line in (OUT/'native-installed-final.sha256.txt').read_text().splitlines()}
targets={'/usr/bin/xiangqi-pikafish-gui':BUILD/'gui-r07/xiangqi-pikafish-gui',
         '/run/xq-native/xq-native-worker':BUILD/'rv32-r05/xq-native-worker',
         '/run/xq-golden-probe-r04':BUILD/'probe-rv32-r04/xq-golden-probe'}
assert all(installed[name]==sha(path) for name,path in targets.items())
assert read(OUT/'golden-device-r04.json')['status']=='PASS'
replay=read(OUT/'native-device-replay.json');assert replay['status']=='PASS'
regression=read(OUT/'regression-r04.json');assert regression['status']=='PASS'
for group in ('source_files_sha256','test_files_sha256','linux_files_sha256'):
    assert all(sha(REPO/name)==digest for name,digest in regression[group].items())
gui=(OUT/'native-gui-final.log.txt').read_text()
assert 'XQ_PICTURE_MODE rv32-driver-quantized-mac' in gui and 'camera=background' in gui
assert 'XQ LINUX PIKAFISH READY' in gui
assert not any(word in gui for word in ('XQ_MODEL_REQUEST','token=','crc=','frame='))
worker=(BUILD/'native-worker-final.private.log').read_text().splitlines()[0]
assert worker=='XQ_NATIVE_READY models=3 backend=rv32-driver-quantized-mac EXPERIMENTAL'
(OUT/'native-worker-ready.txt').write_text(worker+'\n')
record=dict(schema_version=1,status='RAM_DEPLOYED_EXPERIMENTAL',recorded_utc=datetime.now(timezone.utc).isoformat(),
    scope='Running native experimental GUI and model service; NOT production, M0, cold boot or game acceptance',
    backend='rv32-driver-quantized-mac',model_count=3,gui_pid=999,model_worker_pid=954,
    gui_ready=True,engine_ready=True,models_ready=True,background_capture=True,
    installed_sha256=installed,device_layers_80_pass=True,offline_native_rgb565_fen_pass=True,
    offline_single_input_total_ms=replay['stats']['total_ms'],latency_5s_pass=False,
    live_gui_capture_ipc_cancel_restart_smoke=True,
    live_camera_observation='Fresh GUI capture still dark green noise; no visible chessboard',
    live_camera_positive_recognition=False,live_games_accepted=0,board_move_self_heal_accepted=False,
    voice_config='full',voice_volume=100,voice_short_phrase_helper_pass=True,voice_helper_underflows=2,
    human_hid_hdmi_audio_acceptance='deferred',piece_fit_enabled=False,model_manual_geometry_enabled=False,
    full_integer_pipeline=False,production_ready=False,m0_accepted=False,
    cold_boot_candidate=str((BUILD/'ram-r07').relative_to(REPO)),cold_boot_board_validated=False,
    persistent_install=False,sd_written=False,flash_written=False,new_rtl_or_pnr=False,pushed=False,tagged=False,
    remaining=['M0 labels, golden CPU backend and fresh independent acceptance',
               'Camera upstream initialization versus optical/scene problem',
               'Model work budget plus CPU/driver/FP64 performance',
               'P22 delivered piece-fit/manual fallback integration and full M5 closeout',
               'P23 three physical games, board movement recovery and P50/P95',
               'P24 cold-RAM boot and any separately authorized persistent installation'],
    evidence={p.name:sha(p) for p in [OUT/'golden-device-r04.json',OUT/'device-golden-binding.json',
        OUT/'native-device-replay.json',OUT/'regression-r04.json',OUT/'native-rootfs-r07.json',
        OUT/'native-gui-final.log.txt',OUT/'native-worker-ready.txt']})
dest=OUT/'native-ram-deployment.json';assert not dest.exists();dest.write_text(json.dumps(record,indent=2)+'\n')
print('NATIVE_RAM_DEPLOYMENT_RECORDED gui=ready models=3 backend=driver acceptance=EXPERIMENTAL')
