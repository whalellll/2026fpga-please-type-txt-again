"""Replay real StageA/official-C-score checks with simultaneous vision DMA."""
from pathlib import Path
import argparse
import hashlib
import json
import subprocess

ROOT = Path(__file__).resolve().parents[1]


def linux(p):
    s = Path(p).resolve().as_posix()
    return '/mnt/' + s[0].lower() + s[2:]


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--output', required=True, type=Path)
    ap.add_argument('--vectors', required=True, type=Path)
    ap.add_argument('--batch', action='store_true', help='Also enable and replay integrated batch transactions.')
    a = ap.parse_args()
    out = a.output.resolve()
    out.mkdir(parents=True, exist_ok=False)
    ref = a.vectors.resolve()
    assert json.loads((ref/'result.json').read_text())['status'] == 'NNUE_MLP_CHAIN_C_REFERENCE_REAL_PE_PASS_NOT_BOARD'
    (out/'nnue-model.hex').write_text(''.join((ref/'model.hex').read_text().splitlines(keepends=True)[16384:32768]))
    (out/'nnue-golden.hex').write_text((ref/'golden.hex').read_text().splitlines()[131]+'\n')
    src = ROOT/'sim/tb_soc_mac_accel.sv'
    tb = src.read_text()
    tb = tb.replace('.ENABLE_CONV(CONV_ENABLED)', '.ENABLE_CONV(CONV_ENABLED),.ENABLE_VISION32(1)')
    tb = tb.replace('if(measure_nnue && s1_awvalid && s1_awready)',
                    "if(measure_nnue && s1_awvalid && s1_awready && !(s1_awaddr>=32'h1b00d400 && s1_awaddr<32'h1b00d480))")
    preparation = '''
            // Separate vision input/weights/parameters/output from the35,204B MLP model.
            cpu_write_repeat(32'h1b00d000,4,32'h01010101);
            cpu_write_repeat(32'h1b00d100,8,32'h01010101);
            cpu_write_repeat(32'h1b00d300,8,0);cpu_write_repeat(32'h1b00d320,8,0);cpu_write_repeat(32'h1b00d340,8,0);
            reg_write(9'h04c,0);reg_write(9'h050,32'h1b00d000);
            reg_write(9'h04c,1);reg_write(9'h050,32'h1b00d100);
            reg_write(9'h04c,2);reg_write(9'h050,32'h1b00d400);
            reg_write(9'h04c,3);reg_write(9'h050,32'h1b00d300);
            reg_write(9'h04c,4);reg_write(9'h050,32'h1b00d380);
            reg_write(9'h04c,5);reg_write(9'h050,4);
            reg_write(9'h04c,6);reg_write(9'h050,1);
            reg_write(9'h04c,7);reg_write(9'h050,4);
            reg_write(9'h04c,8);reg_write(9'h050,8);
            reg_write(9'h04c,9);reg_write(9'h050,1);
            reg_write(9'h04c,10);reg_write(9'h050,1);
            reg_write(9'h04c,11);reg_write(9'h050,0);
            reg_write(9'h04c,12);reg_write(9'h050,2);
            reg_write(9'h04c,13);reg_write(9'h050,100000);
'''
    needle = '            for(nr=0;nr<2;nr=nr+1)begin'
    assert tb.count(needle) == 1
    tb = tb.replace(needle, preparation+'\n'+needle)
    tb = tb.replace('                measure_nnue=1;nnue_write_bursts=0;',
                    "                if(nr==0)reg_write(9'h048,1);\n                measure_nnue=1;nnue_write_bursts=0;")
    needle = '                measure_nnue=0;'
    assert tb.count(needle) == 1
    tb = tb.replace(needle, needle+'''
                if(nr==0)begin
                    reg_rd_addr=9'h044;#1;timeout=0;
                    while(reg_rd_data[0] && timeout<10000)begin @(posedge clk);#1;timeout=timeout+1;end
                    if(timeout==10000 || reg_rd_data[2] || !reg_rd_data[1])fail("vision simultaneous completion");
                    for(i=0;i<32;i=i+1)begin
                        cpu_read_word(32'h1b00d400+i*4,value);if(value!==4)fail("vision simultaneous exact dot");
                    end
                    $display("VISION32_NNUE_SHARED_PASS vision_words=32 exact_dot=4 official_score=exact intermediate_NNUE_writes=0");
                end
''')
    generated = out/'tb_shared.sv'
    generated.write_text(tb)
    sources = [ROOT/'rtl/soc/axi_2x1_arbiter.v', *sorted((ROOT/'rtl/mac_accel').glob('*.v')),
               ROOT/'sim/gtp_apm_e2_perf_sim.v', ROOT/'sim/axi_shared_ram.sv']
    before = {p.relative_to(ROOT).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest() for p in sources+[src]}
    cmd = f"set -eu; cd '{linux(out)}'; iverilog -g2012 -DPIKAFISH_BOOT_MIN_DRM -s tb_soc_mac_accel -Ptb_soc_mac_accel.H128_ENABLED=0 -Ptb_soc_mac_accel.CONV_ENABLED=1 -Ptb_soc_mac_accel.PIKAFISH_ONLY=1 -Ptb_soc_mac_accel.NNUE_ENABLED=1 -o shared.vvp "
    if a.batch:cmd=cmd.replace('-o shared.vvp','-Ptb_soc_mac_accel.BATCH_ENABLED=1 -o shared.vvp')
    cmd += ' '.join("'"+linux(p)+"'" for p in sources+[generated])+'; vvp shared.vvp'
    r = subprocess.run(['wsl', '-d', 'pikafish-verify', '--', 'sh', '-c', cmd], capture_output=True, timeout=300)
    (out/'simulation.log').write_bytes(r.stdout+r.stderr)
    assert r.returncode == 0, (out/'simulation.log').read_text(errors='replace')[-2500:]
    for marker in (b'VISION32_NNUE_SHARED_PASS', b'NNUE_SOC_DIRECT_PIPELINE_PASS', b'PIKAFISH_SOC_CACHE_PASS'):
        assert marker in r.stdout, marker
    if a.batch:
        for marker in (b'PIKAFISH_BATCH_DEPENDENT_PASS',b'PIKAFISH_BATCH_REJECT_DRAIN_RECOVERY_PASS'):assert marker in r.stdout,marker
    assert before == {p.relative_to(ROOT).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest() for p in sources+[src]}
    result = dict(status='VISION32_AND_PIKAFISH_SIMULTANEOUS_AXI_PASS_NOT_BOARD', source_sha256=before,
                  batch_enabled=a.batch,
                  generated_tb_sha256=hashlib.sha256(generated.read_bytes()).hexdigest(),
                  log_sha256=hashlib.sha256((out/'simulation.log').read_bytes()).hexdigest())
    (out/'result.json').write_text(json.dumps(result, indent=2)+'\n')
    print(json.dumps({'status': result['status']}), flush=True)


if __name__ == '__main__':
    main()
