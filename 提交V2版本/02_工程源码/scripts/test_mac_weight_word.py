"""DMA word-store and AXI read-launch regression with optional RTL baseline."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--output', type=Path, required=True)
    ap.add_argument('--baseline', type=Path, help='Directory containing the three original RTL files')
    ap.add_argument('--iverilog', default='iverilog')
    ap.add_argument('--vvp', default='vvp')
    args = ap.parse_args()
    root = Path(__file__).resolve().parents[1]
    out = args.output.resolve()
    out.mkdir(parents=True, exist_ok=True)
    results = {}
    used_sources = set()

    def run(name, top, sources, defines=()):
        used_sources.update(sources)
        image = out / (name + '.vvp')
        commands = [[args.iverilog, '-g2012', '-s', top, '-o', str(image),
                     *['-D' + d for d in defines], *map(str, sources)], [args.vvp, str(image)]]
        logs = []
        for cmd in commands:
            p = subprocess.run(cmd, cwd=root, capture_output=True, text=True, timeout=180)
            logs.append(p.stdout + p.stderr)
            (out / (name + '.log')).write_text('\n'.join(logs), encoding='utf8')
            if p.returncode or re.search(r'(?m)^\s*(ERROR:|FATAL:|FAIL\b)', logs[-1]):
                raise RuntimeError(f'{name} failed: {out / (name + ".log")}')
        if 'PASS' not in logs[-1]:
            raise RuntimeError(f'{name}: missing PASS marker')
        results[name] = logs[-1].strip().splitlines()
        print(name, 'PASS', flush=True)
        return logs[-1]

    mac = root / 'rtl/mac_accel'
    core = mac / 'MacAccelCore.v'
    run('word_bank', 'tb_mac_weight_word_bank', [core, root / 'sim/tb_mac_weight_word_bank.sv'])
    run('axi_read_launch', 'tb_mac_axi_read_launch',
        [mac / 'mac_accel_axi_master32.v', root / 'sim/tb_mac_axi_read_launch.sv'])
    extras = [root / p for p in ['rtl/soc/axi_2x1_arbiter.v', 'sim/gtp_apm_e2_perf_sim.v',
                                 'sim/axi_shared_ram.sv', 'sim/tb_soc_mac_accel.sv']]
    sources = sorted(mac.glob('*.v')) + extras
    for compact in (False, True):
        profile = 'compact' if compact else 'full'
        defines = ['PIKAFISH_BOOT_MIN_DRM'] if compact else []
        candidate = run(profile, 'tb_soc_mac_accel', sources, defines)
        if args.baseline:
            baseline = args.baseline.resolve()
            original = [baseline / p.name if p.name in ('MacAccelCore.v', 'mac_accel_dma_kernel.v', 'mac_accel_axi_master32.v') else p
                        for p in sources]
            before = run(profile + '_baseline', 'tb_soc_mac_accel', original, defines)
            # The existing bench's "sparse=" field prints MMIO +0xac,
            # the sparse cycle counter; its arithmetic result is checked as 5.
            normalize = lambda s: re.sub(r'(cycles|sparse)=\d+', r'\1=<measured>', s)
            if normalize(candidate) != normalize(before):
                raise RuntimeError(f'{profile}: baseline outputs or traffic changed')
            old_cycles = list(map(int, re.findall(r'(?:cycles|sparse)=(\d+)', before)))
            new_cycles = list(map(int, re.findall(r'(?:cycles|sparse)=(\d+)', candidate)))
            if len(old_cycles) != len(new_cycles) or any(a > b for a, b in zip(new_cycles, old_cycles)):
                raise RuntimeError(f'{profile}: cycle count increased')
            results[profile + '_cycles'] = {'before': old_cycles, 'after': new_cycles}
    run('dma_stream', 'tb_mac_dma_output_stream',
        [mac / 'mac_accel_dma_kernel.v', root / 'sim/tb_mac_dma_output_stream.sv'])
    for top in ['tb_mac_bias_word_bank', 'tb_mac_lane_select', 'tb_mac_output_layout',
                'tb_fp8_e4m3_q8_exhaustive']:
        bench = next((root / 'sim').glob(top + '.*'))
        run(top, top, [core, root / 'sim/gtp_apm_e2_perf_sim.v', bench])
    for top in ['tb_audio_mmio', 'tb_i2s_audio', 'tb_audio_fifo_order', 'tb_audio_capture_chain']:
        bench = next((root / 'sim').glob(top + '.*'))
        run(top, top, [root / 'rtl/audio/audio_mmio.v', root / 'rtl/audio/i2s_audio_duplex.v', bench])
    hashes = {str(p.relative_to(root)): hashlib.sha256(p.read_bytes()).hexdigest()
              for p in sorted(used_sources) if p.is_relative_to(root) and '/synth/original/' not in p.as_posix()}
    summary = {'status': 'MAC_WEIGHT_WORD_REGRESSION_PASS', 'baseline_compared': bool(args.baseline),
               'scope': 'RTL simulation; not physical timing or board acceptance',
               'results': results, 'source_sha256': hashes,
               'runner_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest()}
    (out / 'results.json').write_text(json.dumps(summary, indent=2) + '\n', encoding='utf8')
    print(summary['status'], flush=True)


if __name__ == '__main__':
    main()
