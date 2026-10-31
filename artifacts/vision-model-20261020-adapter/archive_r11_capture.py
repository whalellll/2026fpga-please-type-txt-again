"""Archive redacted capture/build evidence; raw photos and IPC remain in build/."""
import hashlib
import json
import re
from pathlib import Path

HERE=Path(__file__).resolve().parent
REPO=HERE.parents[1]
BUILD=REPO/'build/picture-r11-20261022'
OUT=REPO/'docs/validation/picture-r11-offline-20261022'


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    live=(BUILD/'live-capture-identity-r01.log').read_text()
    identity=re.search(r'XQ_CAPTURE_IDENTITY_PASS token=(\d+) frame=(\d+) crc=([0-9a-f]{8}) bytes=(\d+) lit=(\d+) snapshot_frame_matches=1',live)
    request=re.search(r'XQ_MODEL_REQUEST token=(\d+) frame=(\d+) crc=([0-9a-f]{8}) backend=rv32-driver-quantized-mac',live)
    assert identity and request and identity.group(1,2,3)==request.group(1,2,3)
    assert int(identity[4])==1843200 and int(identity[5])>1280
    assert 'XQ_PICTURE_CAPTURE_RETRY attempt=1 code=-3 status=00002101' in live
    assert not re.search(r'XQ_PICTURE_CAPTURE_RETRY attempt=[23]\b',live)
    progress=(BUILD/'native-progress-r02.log').read_text()
    stage=re.search(r'XQ_NATIVE_STAGE board_done ms=(\d+) jobs=(\d+)',progress)
    assert stage and int(stage[2])==1508
    gui=BUILD/'target-r01/gui/xiangqi-pikafish-gui'
    reconstruction=(BUILD/'gui-ram-reconstruction-r01.log').read_text()
    assert sha(gui)+'  /tmp/xq-gui-r11' in reconstruction
    assert 'XQ_GUI_DELTA_PASS' in reconstruction
    start=(BUILD/'gui-ram-start-r01.log').read_text()
    assert 'XQ_R11_GUI_RAM_READY' in start and 'XQ LINUX PIKAFISH STOPPED' in start
    elf=(BUILD/'target-r01/gui/elf-inspection.txt').read_text()
    assert 'ELF32' in elf and 'RISC-V' in elf and 'rv32i2p1_m2p0_a2p1' in elf
    assert (BUILD/'target-r01/gui/engine-objects-before.sha256').read_bytes()==(BUILD/'target-r01/gui/engine-objects-after.sha256').read_bytes()
    assert 'XQ_CAMERA_EXEC_TEST_PASS' in (BUILD/'camera-exec-r01/host.log').read_text()
    source_names=['linux/vision/xq_camera_capture_retry.c','linux/vision/xq_camera_retry.h',
        'linux/vision/xq_camera.c','linux/vision/xq_camera_linux.c','linux/vision/xq_picture_gui.inc',
        'linux/vision/xq_picture_model.inc','linux/vision/xq_camera_capture.c',
        'linux/vision/test_capture_recovery.c','linux/vision/test_picture_gui.c',
        'linux/vision/build_roi_candidate.sh','artifacts/vision-model-20261020-adapter/runtime/xq_camera_exec.c',
        'artifacts/vision-model-20261020-adapter/test_camera_exec.c']
    logs=['live-capture-identity-r01.log','native-progress-r02.log','gui-ram-reconstruction-r01.log',
        'gui-ram-start-r01.log','gui-delta-upload-r01.log','capture-checker-upload-r01.log',
        'target-r01/gui/elf-inspection.txt','camera-exec-r01/host.log']
    result=dict(status='RAM_CAPTURE_RECOVERY_AND_NATIVE_MODEL_INPUT_PASS',hardware_used=True,
        scope='one software-triggered real camera recovery and native board-model execution; no full recognition or physical Space acceptance',
        trigger='existing XQ_PICTURE_CAPTURE FIFO calls same picture_step as Space',
        observed_startup_NACK_failures=1,successful_attempt=2,additional_trigger_required=False,
        fresh_publications_required=2,request_matches_verified_snapshot_frame=True,
        complete_RAM_file_snapshot_and_request_CRC_equal=True,input_bytes=1843200,image_nonblank=True,
        native_model_execution_confirmed=True,native_board_model_jobs=int(stage[2]),
        native_board_stage_ms=int(stage[1]),timing_scope='single old640/v1 diagnostic stage; not clean latency or r11 model timing',
        GUI_sha256=sha(gui),GUI_active_location='/tmp/xq-gui-r11',models_and_worker='unchanged installed frozen640/v1',
        GUI_voice_during_RAM_test='off',recognition_result='still running at collection',
        full_recognition_passed=False,accuracy_accepted=False,end_to_end_5s_passed=False,
        physical_Space_accepted=False,SD_written=False,Flash_written=False,
        persistence='RAM only; reset restores old SD software and requires current volatile bitstream verification',
        production_ready=False,raw_live_material_location='build/ or board RAM only',
        source_sha256={n:sha(REPO/n) for n in source_names},transcripts_sha256={n:sha(BUILD/n) for n in logs})
    (OUT/'capture-board.json').write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
    build=dict(status='RV32_COMPILE_AND_HOST_WARMUP_TEST_PASS',hardware_acceptance=False,
        GUI_sha256=sha(gui),camera_capture_sha256=sha(BUILD/'target-r01/gui/xq-camera-capture'),
        camera_exec_sha256=sha(BUILD/'camera-exec-r01/target/xq-camera-exec'),
        ELF32_RV32IMA=True,engine_objects_unchanged=True,startup_handoff_host_tests=True,
        source_sha256=result['source_sha256'])
    (OUT/'capture-build.json').write_text(json.dumps(build,indent=2)+'\n',encoding='utf-8')
    print('R11_CAPTURE_REDACTED_EVIDENCE_PASS')


if __name__=='__main__':main()
