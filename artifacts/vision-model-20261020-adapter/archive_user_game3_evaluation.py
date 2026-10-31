"""Archive fresh original-label gate results separately from historical 81-correction scores."""
from datetime import datetime,timezone
import hashlib,json
from pathlib import Path
import shutil
HERE=Path(__file__).resolve().parent;REPO=HERE.parents[1]
OUT=REPO/'docs/validation/picture-p20-original-labels-20261020-r03'
def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
metrics={};supplement={};identities={}
for backend in ('fp32','quantized-mac'):
    root=OUT/backend
    metrics[backend]=json.loads((root/'metrics_summary.json').read_text())
    supplement[backend]=json.loads((root/'retained-missing/metrics_summary.json').read_text())
    assert metrics[backend]['n_frames']==135 and metrics[backend]['requested_numeric_gate_pass']
    assert metrics[backend]['test_game_corrections']==0 and metrics[backend]['withdrawn_game3_corrections']==77
    assert len(list((root/'predictions').glob('IMG*.json')))==135
    assert supplement[backend]['whole_board_exact']['correct']==135
    policy=json.loads((root/'truth-policy/manifest.json').read_text())
    for name,digest in policy['files'].items():assert sha(root/'truth-policy'/name)==digest
    rows=json.loads((root/'end_to_end_per_frame.json').read_text())
    diffs=[row for row in rows if not row['usable_exact']]
    (root/'strict-interface-differences.json').write_text(json.dumps(diffs,indent=2)+'\n')
    identities[backend]={name:sha(root/name) for name in ('inputs.json','metrics_summary.json','per_frame.json',
        'end_to_end_per_frame.json','truth-policy/manifest.json','retained-missing/metrics_summary.json')}
assert identities['fp32']['truth-policy/manifest.json']==identities['quantized-mac']['truth-policy/manifest.json']
policy_dir=HERE/'label-policy-user-original-game3-20261020'
assert not policy_dir.exists()
shutil.copytree(OUT/'fp32/truth-policy',policy_dir)
record=dict(schema_version=1,recorded_utc=datetime.now(timezone.utc).isoformat(),
    status='REQUESTED_NUMERIC_GATES_PASS_WITH_BOUNDARIES',requested_numeric_gates_pass=True,m0_accepted=False,
    user_ruling='(8,3) is a pawn; withdraw the 77 game-3 class corrections; rerun 135 frames against original labels',
    primary_policy='Original game-3 circle labels without any correction overlays',
    supplemental_policy='Only 77 class corrections withdrawn; retain existing IMG00920 missing-pawn correction',
    historical_record_preserved='../picture-p20-combined-20261020/M0.json',
    withdrawn_class_corrections=77,primary_test_corrections_applied=0,supplemental_test_corrections_applied=1,
    frames='IMG00908..IMG01042',n_frames=135,fresh_model_inference_per_backend=True,
    thresholds=dict(conf=.05,ap_match_iou=.5,class_aware_nms_iou=.6,whole_board_min=.85,weak_ap50_min=.5),
    metrics=metrics,supplemental_metrics=supplement,evidence_sha256=identities,
    independent_test=False,independence_reason='R2 manifest discloses prior game-3 failure-analysis use',
    production_ready=False,full_integer_pipeline=False,
    original_cpu_integer_backend_exactness_unresolved=True,training_payloads_and_original_labels_modified=False,
    remaining=['Fresh independent acceptance','Original torch._int_mm exactness and strict cell conflicts',
               'Live camera positive recognition','Native latency and P22-P24 acceptance'])
with (OUT/'M0.json').open('x') as f:json.dump(record,f,indent=2);f.write('\n')
table=[]
for b in metrics:
    m=metrics[b];s=supplement[b]
    table.append(f"| {b} | {m['whole_board_exact']['correct']}/135 (99.26%) | {s['whole_board_exact']['correct']}/135 (100%) | {m['end_to_end']['strict_usable_exact']}/135 | {s['end_to_end']['strict_usable_exact']}/135 |")
text='''# 用户裁定后的135帧复测（2026-10-20）

用户确认 (8,3) 是兵，明确撤回第3局77条分类修正。原训练包、原标注、原81条修正表、
旧42.96%报告均保留；新口径独立版本化。两个后端均重新执行完整135帧推理，不是仅换分母或重算旧预测。
图像/棋子标注/棋盘标注405项 SHA 与旧评估逐项相同，阈值、权重与原后端未更改。

## 新门槛数字

| 后端 | 原始标注整盘 | 仅撤回77条并保留漏标补子 | 原始标注严格FEN正确 | 保留漏标补子严格FEN正确 |
|---|---:|---:|---:|---:|
'''+ '\n'.join(table)+'''

两后端 black_pao、black_ma、red_ma AP50 均为0.995，指定整盘≥85%、弱类各≥0.5的数字门槛通过。
原始标注主评分不叠加任何修正，唯一整盘差异为 IMG00920 原标注漏兵；该条漏标补子不在撤回的77条分类修正中，
因此另附保留它的对照评分。对照评分复用本次新生成的预测文件，没有额外推理，来源 SHA 独立归档。

FP32 严格接口仍有1帧冲突，原版 quantized-mac 有54帧冲突。
参考几何的90格评分与自动几何的严格FEN为不同口径；GT离格丢弃及严格拒绝不能由整盘评分替代。
逐帧严格差异在各后端 strict-interface-differences.json，全部预测位于 predictions/。
原CPU整数点积问题仍未解决，未静默替换精确INT32后端。

**本次指定数字门槛通过，整体M0仍未确认通过。** 第3局已被R2用于失败分析，不是新独立验收；
production_ready=false、full_integer_pipeline=false、真实相机正向识别、原生延迟与整局验收均未由本记录通过。

[M0机器记录](M0.json)、[FP32](fp32/metrics_summary.json)、[quantized-mac](quantized-mac/metrics_summary.json)。
各后端 truth-policy/ 包含版本化1042帧FEN、撤回清单、逐帧再生成审计及来源SHA。
adapter/label-policy-user-original-game3-20261020/ 为同内容的后续回归输入。
同名r01/r02目录仅为真值生成守卫的失败尝试，没有完成推理或门槛结果；本轮有效结果是r03。
'''
(OUT/'README.md').write_text(text,encoding='utf-8')
print('USER_ORIGINAL_LABEL_GATE_ARCHIVED numeric_pass=true m0_accepted=false')
