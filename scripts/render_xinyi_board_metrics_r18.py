"""Render a source-backed, bounded real-board comparison table for video use."""
from pathlib import Path
import argparse
import hashlib
import json
import re
import sys

from picture_workspace import ROOT, workspace_path


def fields(line):
    return dict(item.split('=', 1) for item in line.split()[1:] if '=' in item)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--evidence', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    a = p.parse_args()
    source, out = workspace_path(a.evidence), workspace_path(a.output)
    out.mkdir(parents=True, exist_ok=False)
    sha = lambda b: hashlib.sha256(b).hexdigest()
    inputs = {}

    def read(name):
        data = (source/name).read_bytes()
        inputs[name] = {'bytes': len(data), 'sha256': sha(data)}
        return data.decode('utf8')

    receipt = json.loads(read('cram-r18-r01.json'))
    assert receipt['status'] == 'PASS' and receipt['operation'] == 'CRAM'
    assert receipt['device_count'] == 1 and receipt['native_input_hashes'] == 498
    assert receipt['bitstream_sha256'] == 'e42f5f1be3bc2a1a2e8f99ce428c3f9ed9762bcc685c722b03342ac746b5470b'
    audit = read('fresh-linux-audit-r01.txt')
    assert 'CPU_HZ 0x03938700' in audit and 'SYS_HZ 0x02F34F60' in audit
    assert 'MAC_VERSION 0x00010001' in audit
    rows = []
    for name, count, title, scope, lut in [
        ('vision', 3, '图像卷积算子', '16×16 · Cin32/Cout32 · 3×3 · RAW-I32', 5762),
        ('voice', 4, '语音 CNN', '冻结 balanced24 · 64 帧 · 五层网络', 2458),
        ('nnue', 3, '棋盘推理 MLP', '四组双视图 · 特征变换＋专用 MLP', 2891),
    ]:
        text = read('run-'+name+'-r01.txt')
        assert re.search(r'XYHOST_\w+_STATUS=0', text)
        post = text.split('R18_EXTERNAL_POST_'+name.upper()+' rc=0', 1)[1]
        busy = re.findall(r'BUSY (0x[0-9a-f]+) (0x[0-9a-fA-F]+)', post)
        assert len(busy) == 5 and all(int(v, 16) & 1 == 0 for _, v in busy)
        prefix = 'VOICE_PROBE_PAIR ' if name == 'voice' else 'R18_PAIR '
        pairs = [fields(line) for line in text.splitlines() if line.startswith(prefix)]
        assert len(pairs) == count
        if name == 'voice':
            assert 'clock=CLOCK_MONOTONIC mock=0' in text
            assert 'hardware_used=1' in text and 'output_crc=843efe51' in text
            assert all(v['full5_equal'] == '1' and v['jobs'] == '12' for v in pairs)
        else:
            assert 'backend=published_E42_driver' in text
            assert 'R18_PROBE_PASS outputs_complete_i32_equal=1 final_idle_proven=1' in text
            assert all(v['exact'] == '1' for v in pairs)
        cpu = sum(int(v['cpu_ns']) for v in pairs)
        hw = sum(int(v['mac_ns' if name == 'voice' else 'accelerator_ns']) for v in pairs)
        rows.append(dict(name=name, title=title, scope=scope, pairs=pairs,
            cpu_mean_ms=cpu/count/1e6, accelerator_mean_ms=hw/count/1e6,
            cpu_total_ns=cpu, accelerator_total_ns=hw, speedup=cpu/hw,
            scope_luts=lut, full_outputs_equal=True))
    result = dict(status='REAL_CPU60_BOARD_MATCHED_INPUT_ALL_OUTPUTS_PASS',
        cpu_hz=60000000, system_hz=49500000, mac_version='00010001',
        statistic='sum CPU wall time / sum accelerator wall time, warmed alternating pairs',
        timing_includes='per-call layout/packing, driver transfers, materialization/readback; voice includes CPU requant',
        timing_excludes='one-time process/model/setup, capture, FFT/VAD/CTC, image geometry, engine search',
        synthetic_input=True, rows=rows, evidence=inputs,
        generator_sha256=sha(Path(__file__).read_bytes()),
        limitations=['Operator/CNN-subgraph comparisons, not whole recognition or game speedup.',
            'LUT counts are fixed synthesis subtree references; do not include shared infrastructure.',
            'Three convolution/MLP measured pairs after three warm pairs; four CNN pairs after one warm pair.'])
    (out/'metrics.json').write_text(json.dumps(result, ensure_ascii=False, indent=2)+'\n', encoding='utf8')
    sys.path.insert(0, str(ROOT/'build/xinyi-host-20261024/tools'))
    from PIL import Image, ImageDraw, ImageFont
    font_path = 'C:/Windows/Fonts/msyh.ttc'
    font = lambda n: ImageFont.truetype(font_path, n)
    im = Image.new('RGB', (1920, 1080), '#f4f0e7')
    d = ImageDraw.Draw(im)
    d.rounded_rectangle((48, 38, 1872, 1042), 30, fill='#fffdf7')
    d.text((96, 76), '中国象棋 RISC-V 平台 · 实板加速测量', font=font(54), fill='#23382f')
    d.text((99, 156), '盘古676 100Pro+   |   CPU 60 MHz   |   系统 49.5 MHz   |   2026-10-29', font=font(28), fill='#5d675e')
    y, h = 231, 151
    xs = [96, 800, 1100, 1385, 1610, 1824]
    d.rounded_rectangle((96, y, 1824, y+70), 12, fill='#23382f')
    for x, label in zip(xs, ['测试范围', 'CPU / ms', '加速后 / ms', '加速比', '完整输出']):
        d.text((x+22, y+16), label, font=font(28), fill='white')
    y += 70
    for i, row in enumerate(rows):
        d.rectangle((96, y, 1824, y+h), fill='#f0f2eb' if i%2 == 0 else '#faf8f1')
        d.text((118, y+27), row['title'], font=font(34), fill='#23382f')
        d.text((118, y+87), row['scope'], font=font(22), fill='#56665c')
        for x, value in [(822, f"{row['cpu_mean_ms']:.3f}"),
                         (1122, f"{row['accelerator_mean_ms']:.3f}"),
                         (1407, f"{row['speedup']:.2f}×")]:
            d.text((x, y+43), value, font=font(38), fill='#9e3e28' if x == 1407 else '#23382f')
        d.text((1632, y+50), '一致', font=font(31), fill='#267047')
        y += h
    notes = [
        '计时：同一板卡、同一输入，预热后交替配对；表中为平均墙钟耗时，倍率取总耗时之比。',
        '包含：每次布局/打包、驱动传输、完整输出读回；语音另包含 CPU 重量化。',
        '范围：卷积算子、语音 CNN 子图和 NNUE MLP 路径；不代表整盘识别、完整语音或棋局加速比。',
        '验证：卷积 8192 个 I32；语音五层累加及量化输出；MLP 四个 I32 评分，全部逐项一致。',
    ]
    for i, note in enumerate(notes):
        d.text((100, 784+i*47), note, font=font(25), fill='#4e5d54')
    d.text((100, 994), '数据来源：新运行实板记录 / 有限测量 / 合成固定输入 / 原始日志与程序 SHA 可追溯', font=font(21), fill='#798178')
    im.save(out/'xinyi-board-speedups-r18-1920x1080.png')
    (out/'SHA256SUMS.txt').write_text(''.join(sha(f.read_bytes())+'  '+f.name+'\n'
        for f in sorted(out.iterdir()) if f.is_file()), encoding='utf8')
    print(json.dumps([(r['name'], round(r['speedup'], 6)) for r in rows]))


if __name__ == '__main__':
    main()
