"""Seal an offline model-side INT8 handoff; no inference, training or install."""
from pathlib import Path
import argparse
import hashlib
import json
import re
import subprocess
import sys
import zipfile

from picture_workspace import ROOT, workspace_path

sys.dont_write_bytecode = True
sys.path.insert(0, str(ROOT/'scripts/model_int8_handoff'))
from handoff_inventory import MODELS, inventory


DATE = '20261027'
DOCS = ROOT/'docs/validation/picture-e42-integration-20261026'
DOC_FILES = {
    'PROMPT_zh.md':'model-int8-ai-prompt-20261027.md',
    'handoff-contract.md':'model-int8-handoff-contract-20261027.md',
    'model-direction.md':'model-direction-20261027.md',
    'model-int8-primary-notes.md':'model-int8-primary-notes-20261027.md',
    'software-next-plan.md':'software-next-plan-20261027.md',
}

README = '''# 模型侧INT8交接 r01 · 2026-10-27

先读PROMPT_zh.md、model-direction.md、handoff-contract.md，再运行只读核验。
模型路线已经由工程侧选定：混合精度W8/A8主干、I32累加、必要S16分支/头；
主候选512保持结构，质量不合格时备选640结构化裁剪/蒸馏。
当前85节点实际69个S8、16个S16，没有S32激活节点；累加仍是I32。
全A8不是交付目标。冻结部署模型、阈值和估计盘面/荐着策略保持。

本包包含冻结部署模型，不含原始FP32训练checkpoint、训练工程和数据集。
本轮工程未训练/校准，也未安装新模型；模型侧实验遵循实际训练/数据授权。
game2/CAMERA_v2封存，不由此包开放。无真实照片、局面/FEN、请求/结果或实景张量。
PN08此前已实际上板；r05新候选尚未安装。正确物理Space到HDMI整盘<300秒仍待验收。

目录：
- baseline-models/：board/classifier冻结pack、原参数、refinement RNG。
- baseline-oracle/：逐字节保留的历史HWC CPU合成验收kit，包含detector XQM/XQI。
- current-source/：当前r05绑定的工程源码加本交接所需的格式/量化/测试源码。
- baseline-inventory.json：读取模型真实字节得到的逐节点图、尺度、位宽与参数约束。
- templates/：候选合同和回传清单；未知/未测保持null或NOT_RUN，不填虚假PASS。
- evidence/current-facts.json：当前状态与历史证据边界。

根提示词优先于baseline-oracle/README.md及源码内的历史说明：不要重新启动旧r25
178帧任务，不访问其历史说明提到的封存图像。历史kit和current-source是不同源码
快照，分别保留身份；不得把历史二进制绑定到当前源码。

在Linux x86_64/WSL及Python>=3.9执行：

```sh
python3 verify_handoff.py
python3 numeric_smoke.py --output /absolute/fresh-directory-outside-this-handoff
```

第一条只核对清单/模型SHA/CRC/逐节点元数据。第二条从导出源码编译有限的合成
量化和整数算子测试，不运行完整网络、设备或训练；每子命令60秒上限。
如有相关改动或首次需要重建完整基线，才运行历史完整CPU合成自检：

```sh
chmod +x baseline-oracle/integer-host baseline-oracle/hwc-convert
python3 baseline-oracle/selftest.py
```

该完整selftest未在本交接重复运行，原kit身份/合成证据已保留。它只接受冻结SHA，
不能用于新候选而只改expected或SHA常量。新模型需交付自己的参考/格式/loader差异。
工程硬件接口不变；原生S8写回不是模型导出即可提供的能力。
本包没有自动安装/启动操作，设备bench和worker源码仅供合同阅读，不授权上板。
'''


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', required=True, type=Path)
    parser.add_argument('--kit', type=Path, default=ROOT/'build/picture-e42-20261025/hwc-acceptance-kit')
    parser.add_argument('--models', type=Path, default=ROOT/'build/picture-e42-20261025/hwc-product-host-r01/models')
    parser.add_argument('--desktop-directory', type=Path)
    args = parser.parse_args()
    if not args.output.absolute().is_relative_to(ROOT/'build'):
        parser.error('Use a new private build output directory')
    out = workspace_path(args.output)
    if not out.is_relative_to((ROOT/'build/picture-e42-20261025').resolve()):
        parser.error('Model payloads must remain outside Git in the private E build area')
    kit, models = workspace_path(args.kit), workspace_path(args.models)
    out.mkdir(parents=True, exist_ok=False)
    stage = out/'handoff';stage.mkdir()
    sha = lambda data: hashlib.sha256(data).hexdigest()
    payload = {}
    sources = {}
    report = dict(status='FAILED_PRESERVED', hardware_used=False, training_or_calibration_run=False)

    def add(name, data):
        assert name not in payload
        assert not name.startswith('/') and '..' not in Path(name).parts and '\\' not in name
        payload[name] = data
        path = stage/name;path.parent.mkdir(parents=True, exist_ok=True);path.write_bytes(data)

    def json_bytes(value):
        return (json.dumps(value, indent=2, ensure_ascii=False)+'\n').encode('utf-8')

    try:
        r05 = json.loads((DOCS/'software-speed-offline-r05.json').read_text(encoding='utf-8'))
        bindings = r05['package']['source_sha256']
        assert len(bindings) == 217
        for rel, digest in bindings.items():
            data = (ROOT/rel).read_bytes();assert sha(data) == digest, ('r05 source drift', rel)
            sources[rel] = digest
        extra = ['scripts/prepare_picture_hwc_model.py','scripts/analyze_picture_costs.py',
            'scripts/prepare_picture_model_int8_handoff.py',
            'artifacts/picture-e42-integration-20261026/software/prepare_integer_detector.py',
            'linux/picture_new/hwc_fast/tests/test_integer_quant.c',
            'linux/picture_new/hwc_fast/tests/test_integer_ops.c',
            'linux/picture_new/upstream/adapter/runtime/xq_int8_layer.c',
            'linux/picture_new/upstream/adapter/runtime/xq_int8_layer.h']
        for rel in re.findall(r'\]\(\.\./\.\./\.\./([^\)]+)\)', (DOCS/DOC_FILES['model-int8-primary-notes.md']).read_text(encoding='utf-8')):
            extra.append(rel.split('#')[0])
        for rel in extra:
            data = (ROOT/rel).read_bytes();sources[rel] = sha(data)
        for rel in sorted(sources):
            add('current-source/'+rel, (ROOT/rel).read_bytes())
        for target, source in DOC_FILES.items():
            text = (DOCS/source).read_text(encoding='utf-8')
            if target == 'model-int8-primary-notes.md':
                text = text.replace('](../../../', '](current-source/')
            add(target, text.encode('utf-8'))
        add('README.md', README.encode('utf-8'))
        for name in ['handoff_inventory.py','verify_handoff.py','numeric_smoke.py']:
            add(name, (ROOT/'scripts/model_int8_handoff'/name).read_bytes())

        # Preserve every original kit entry; validate its complete 97-file list.
        kit_entries = {}
        for line in (kit/'SHA256SUMS.txt').read_text().splitlines():
            digest, rel = line.split(maxsplit=1)
            assert rel not in kit_entries and '..' not in Path(rel).parts
            data = (kit/rel).read_bytes();assert sha(data) == digest, rel
            kit_entries[rel] = digest
        assert len(kit_entries) == 97
        assert {p.relative_to(kit).as_posix() for p in kit.rglob('*') if p.is_file()} == set(kit_entries)|{'SHA256SUMS.txt'}
        for rel in sorted(set(kit_entries)|{'SHA256SUMS.txt'}):
            add('baseline-oracle/'+rel, (kit/rel).read_bytes())
        for name in ['board.xqm','classifier.xqm','native_parameters.h','refinement_rng.bin']:
            data = (models/name).read_bytes()
            expected = r05['package']['frozen_models_not_included_sha256'][name]
            assert sha(data) == expected, name
            add('baseline-models/'+name, data)
        for name in ['detector.xqm','detector.xqi']:
            assert (models/name).read_bytes() == payload['baseline-oracle/models/'+name]
        inv = inventory(stage)
        add('baseline-inventory.json', json_bytes(inv))
        add('templates/candidate-contract.template.json', json_bytes(dict(
            schema='picture-model-candidate-contract-v1',status='DESIGN_ONLY_NOT_TRAINED',candidate_id=None,
            selected_route='mixed_W8_A8_I32_accum_required_S16_C1_512_then_C2_640_pruning_if_needed',
            baseline_model_sha256={name:digest for name,(path,digest) in MODELS.items()},
            original_checkpoint_sha256=None,original_training_source_identity=None,exporter_sha256=None,
            input=dict(channels=3,side=None,layout=None,dtype=None,scale=None,exponent=None,zero_point=None,
                       resize=None,letterbox=None,normalization=None),
            tensors=[],tensor_required_fields=['id','shape','dtype','layout','scale_or_exponent','zero_point',
                'rounding','clamp','producer','consumers','intermediate_storage_conversion'],
            layers=[],layer_required_fields=['id','op','kernel','stride','dilation','k','input_tensor_ids',
                'output_tensor_id','weight_dtype','bias_dtype','accumulator_dtype','multiplier','right_shift',
                'lut_sha256','supported_by_current_backend'],
            outputs=[],decoder_thresholds_unchanged=True,geometry_thresholds_unchanged=True,
            estimated_recommendations_preserved=True,requires_independent_loader_contract=True,
            runtime_compatibility='NOT_VERIFIED',numeric_test_status='NOT_RUN',quality_test_status='NOT_RUN',
            device_test_status='NOT_RUN',training_or_calibration_authorization=None,
            authorized_data_identity=None,unsupported_items=[],limitations=[])))
        add('templates/return-manifest.template.json', json_bytes(dict(
            schema='picture-model-side-return-v1',status='AUDIT_ONLY_OR_INCOMPLETE',received_archive_sha256=None,
            receiver_source_commit=None,receiver_dirty_source_sha256=None,environment=None,commands=[],
            original_checkpoint_identity=None,authorized_dataset_scope=None,training_authorization=None,
            candidates=[],numerical_reference_checks=[],label_quality_checks=[],fp32_chain_agreement_checks=[],
            static_costs=[],cpu_timings_not_board=[],real_device_checks=[],
            old_r25_rerun_required=False,physical_display_under300s_accepted=False,
            files=[],failures=[],not_run=[],limitations=[])))
        facts = dict(date='2026-10-27',branch='Picture_new',head=subprocess.check_output(
            ['git','-C',str(ROOT),'rev-parse','HEAD'],text=True).strip(),implementation_checkpoint='aba5f938',
            baseline_frozen=True,pn08_has_been_run_on_board=True,r05_candidate_installed=False,
            r05_package_sha256=r05['package']['sha256'],r05_source_bindings_verified=217,
            correct_same_frame_worker_seconds=242.163,gui_capture_engine_included=False,
            worker_stages_seconds=dict(board=33.650,detector=91.633,classifier=36.294,geometry=80.530,assign=.056),
            correct_physical_space_to_independent_hdmi_under300s=False,
            actual_board_runtime_unknown=True,board_operations_suspended=True,
            r25_agreement=dict(hwc_vs_fp32=[161,178],dev37_spot=[10,10],not_label_accuracy=True,
                               no_retraining_or_old178_rerun_requested=True),
            older_complete_frame_still_incorrect=True,estimated_board_recommendations_preserved=True,
            same_graph_jobs=dict(historical_oracle=166,r05_tail_candidate=152),
            cpu_or_qemu_is_not_board_latency=True)
        add('evidence/current-facts.json', json_bytes(facts))
        for name in ['software-speed-offline-r05.md','software-investigation-r06.md']:
            add('evidence/'+name, (DOCS/name).read_bytes())
        manifest = dict(schema='picture-model-int8-handoff-v1',date='2026-10-27',
            status='PREPARED_FOR_OFFLINE_AUDIT_AND_MODEL_DIRECTION_NO_TRAINING',
            head=facts['head'],hardware_used=False,training_or_calibration_run=False,
            frozen_models_unchanged=True,model_packs_included=True,training_checkpoints_included=False,
            training_datasets_or_private_scene_inputs_included=False,old_r25_rerun_required=False,
            selected_route='mixed_precision_512_detector_primary_640_structured_pruning_backup',
            current_xqi_activation_nodes={'S8':69,'S16':16,'S32':0},
            current_source_sha256=sources,original_r05_bindings_verified=217,
            historical_kit_payloads_verified=97,
            payloads={name:dict(bytes=len(data),sha256=sha(data)) for name,data in sorted(payload.items())})
        add('manifest.json', json_bytes(manifest))
        sums = ''.join(sha(data)+'  '+name+'\n' for name,data in sorted(payload.items()))
        add('SHA256SUMS.txt', sums.encode('utf-8'))
        assert all(Path(name).suffix.lower() not in {'.png','.jpg','.jpeg','.rgb565','.ppm','.pgm'} for name in payload)
        assert not any(Path(name).name.lower() in {'request.txt','result.txt','release9.txt','frame.bin'} for name in payload)
        assert all(sha((ROOT/name).read_bytes()) == digest for name,digest in sources.items())
        proc = subprocess.run([sys.executable,'-B',str(stage/'verify_handoff.py')],capture_output=True,timeout=30)
        (out/'verify-stage.log').write_bytes(proc.stdout+proc.stderr)
        assert proc.returncode == 0, proc.stderr.decode(errors='replace')[-2000:]
        archive = out/('xinyi-model-int8-handoff-r01-'+DATE+'.zip')
        with zipfile.ZipFile(archive,'x',compression=zipfile.ZIP_DEFLATED,compresslevel=9) as z:
            for name,data in sorted(payload.items()):
                item = zipfile.ZipInfo(name,date_time=(2026,10,27,0,0,0))
                item.compress_type = zipfile.ZIP_DEFLATED
                executable = name in {'baseline-oracle/integer-host','baseline-oracle/hwc-convert'}
                item.external_attr = (0o100755 if executable else 0o100644)<<16
                z.writestr(item,data)
        with zipfile.ZipFile(archive) as z:
            assert z.testzip() is None and set(z.namelist()) == set(payload)
            assert all(z.read(name) == data for name,data in payload.items())
        report.update(status='MODEL_INT8_HANDOFF_SEALED_HASHES_INVENTORY_PASS_NO_TRAINING',
            archive=archive.name,archive_bytes=archive.stat().st_size,archive_sha256=sha(archive.read_bytes()),
            members=len(payload),current_source_entries=len(sources),model_sha256={name:digest for name,(path,digest) in MODELS.items()},
            checkpoints_included=False,original_r05_217_source_bindings_unchanged=True,
            full_network_rebenchmark_run=False,exported_numeric_smoke_run=False)
        if args.desktop_directory:
            desktop = args.desktop_directory.resolve();assert desktop.is_dir()
            target = desktop/archive.name
            with target.open('xb') as f:f.write(archive.read_bytes())
            assert sha(target.read_bytes()) == report['archive_sha256']
            prompt = desktop/('xinyi-model-int8-prompt-r01-'+DATE+'.md')
            with prompt.open('xb') as f:f.write(payload['PROMPT_zh.md'])
            report.update(desktop_archive=str(target),desktop_prompt=str(prompt))
    finally:
        (out/'result.json').write_text(json.dumps(report,indent=2,ensure_ascii=False)+'\n',encoding='utf-8')
    print(json.dumps({key:report[key] for key in ['status','archive_bytes','archive_sha256','members','current_source_entries']},indent=2))


if __name__ == '__main__':
    main()
