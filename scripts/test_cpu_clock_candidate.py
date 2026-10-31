"""Bounded WSL functional checks for a frozen CPU clock candidate; no CoreMark."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess
import tempfile
import time


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--verilator', default='verilator')
    args = parser.parse_args()
    root, out = args.root.resolve(), args.output.resolve()
    out.mkdir(parents=True, exist_ok=False)
    results, sources = {}, set()
    clock = json.loads((root/'config/clocks.json').read_text())
    cpu_arg = '+cpu_hz='+str(clock['cpu_hz'])
    # The existing peripheral bench uses the build helper's PDS ROM alias.
    # A source-only staged candidate has the authoritative artifact but has
    # not yet run that helper. Never replace a different existing ROM.
    rom = root/'artifacts/bootrom.hex'
    alias = root/'pds/bootrom.hex'
    if alias.exists():
        if alias.read_bytes() != rom.read_bytes():
            raise RuntimeError('PDS ROM alias differs from authoritative artifact')
    else:
        alias.write_bytes(rom.read_bytes())
    sources.update([rom, alias])

    def receipt(status):
        record = {'status': status, 'scope': 'Functional RTL only; no RTL CoreMark or board score',
                  'root': str(root), 'clocks': clock, 'results': results,
                  'source_sha256': {str(p.relative_to(root)): hashlib.sha256(p.read_bytes()).hexdigest()
                                    for p in sorted(sources)}}
        (out/'results.json').write_text(json.dumps(record, indent=2)+'\n')
        return record

    def run(name, command, marker=None, timeout=180, cwd=None):
        start = time.monotonic()
        command = [str(x) for x in command]
        try:
            p = subprocess.run(command, cwd=cwd or root, capture_output=True, timeout=timeout)
        except subprocess.TimeoutExpired as error:
            log = (error.stdout or b'')+(error.stderr or b'')
            (out/(name+'.log')).write_bytes(log)
            results[name] = {'command': command, 'timeout_seconds': timeout,
                             'seconds': time.monotonic()-start, 'status': 'TIMEOUT'}
            receipt('CPU_CLOCK_FUNCTIONAL_FAILED')
            raise
        log = p.stdout + p.stderr
        (out/(name+'.log')).write_bytes(log)
        text = log.decode('utf-8', errors='replace')
        results[name] = {'command': command, 'exit': p.returncode, 'seconds': time.monotonic()-start,
                         'log_sha256': hashlib.sha256(log).hexdigest()}
        if p.returncode or re.search(r'(?m)^\s*(ERROR:|FATAL:|%Error)', text) or (marker and marker not in text):
            receipt('CPU_CLOCK_FUNCTIONAL_FAILED')
            raise RuntimeError(f'{name} failed; inspect {out/(name+".log")}')
        receipt('CPU_CLOCK_FUNCTIONAL_RUNNING')
        if marker:
            print(name+' PASS', flush=True)
        return text

    def leaf(top, names, variants=([],)):
        paths = [root/n for n in names]
        sources.update(paths)
        image = out/(top+'.vvp')
        run(top+'_compile', ['iverilog', '-g2012', '-s', top, '-o', image, *paths])
        for i, extra in enumerate(variants):
            run(top+f'_{i}', ['vvp', image, *extra], 'PASS')

    leaf('tb_axi_cpu_sys_cdc', ['rtl/soc/axi_cpu_sys_cdc.v','sim/tb_axi_cpu_sys_cdc.sv'], [
        ['+cpu_half=7','+sys_half=11','+sys_phase=3','+seed=439041101'],
        ['+cpu_half=13','+sys_half=5','+sys_phase=2','+seed=1515870810'],
        ['+cpu_half=10','+sys_half=10','+sys_phase=4','+seed=305419896'],
        ['+cpu_half=20','+sys_half=30','+sys_phase=7','+seed=1882533926']])
    leaf('tb_clint_sys_irq', ['rtl/clint.v','rtl/cpu_top.v','sim/tb_clint_sys_irq.sv'])
    for top, names in {
        'tb_axi_2x1_arbiter':['rtl/soc/axi_2x1_arbiter.v'],
        'tb_axi_boot_periph':['rtl/soc/uart_tx_fifo.v','rtl/soc/axi_boot_periph.v'],
        'tb_sd_native_mmio':['rtl/soc/sd_native_mmio.v'],
        'tb_sd_native_write':['rtl/soc/sd_native_mmio.v'],
        'tb_sd_native_multiblock':['rtl/soc/sd_native_mmio.v'],
        'tb_ch9350_hid':['rtl/soc/ch9350_hid_core.v'],
        'tb_ch9350_linux_no_toolbar':['rtl/soc/ch9350_hid_core.v'],
        'tb_axi_ddr_cdc':['rtl/soc/axi_ddr_cdc.v'],
        'tb_ddr_native_read_arbiter':['rtl/soc/ddr_native_read_arbiter.v'],
        'tb_ddr_native_write_arbiter':['rtl/soc/ddr_native_write_arbiter.v'],
        'tb_camera_mmio':['rtl/camera/camera_mmio.v'],
        'tb_camera_buffer_control':['rtl/camera/camera_buffer_control.v'],
        'tb_camera_frame_writer':['sim/camera_line_buffer_model.sv','rtl/camera/camera_frame_writer.v'],
        'tb_video_fb_dma':['rtl/video/video_fb_dma.v'],
        'tb_eth_mac_mmio':['rtl/eth/eth_mac_mmio.v'],
        'tb_rgmii_100m':['rtl/eth/rgmii_interface.v'],
    }.items():
        bench = next((root/'sim').glob(top+'.*'))
        leaf(top, names+[bench.relative_to(root).as_posix()])

    # Assembly integration uses the available Linux cross compiler, not a
    # substitute for the release GCC 16.2/CoreMark performance toolchain.
    gcc = '/opt/toolchain/bin/riscv32-linux-musl-gcc'
    run('functional_compiler', [gcc,'-v'])
    fixture = root/'artifacts/selftest'
    fixture.mkdir(parents=True, exist_ok=True)
    sources.update(root/n for n in ['sim/cpu_integration.S','sim/cpu_integration.ld'])
    # GCC 9 predates split Zicsr/Zifencei names; the installed assembler is
    # newer. Pass each its actual supported spelling for this assembly-only
    # functional fixture, without changing the release toolchain contract.
    run('assembly', [gcc, '-march=rv32ima','-Wa,-march=rv32ima_zicsr_zifencei','-mabi=ilp32','-mno-relax',
        '-nostdlib','-nostartfiles','-static','-Wl,--build-id=none',
        '-T',root/'sim/cpu_integration.ld',root/'sim/cpu_integration.S','-o',out/'integration.elf'])
    run('objcopy', ['/opt/toolchain/bin/riscv32-linux-musl-objcopy','-O','binary',out/'integration.elf',out/'integration.bin'])
    data = (out/'integration.bin').read_bytes()
    data += bytes((-len(data)) % 4)
    (fixture/'cpu_integration.hex').write_text(''.join(f'{int.from_bytes(data[i:i+4],"little"):08x}\n' for i in range(0,len(data),4)))
    paths = [root/n for n in ['rtl/cpu/CoreTop.sv','rtl/clint.v','rtl/cpu_top.v',
        'rtl/soc/axi_1x2.v','rtl/soc/axi_boot_periph.v','rtl/soc/axi_cpu_sys_cdc.v',
        'rtl/soc/uart_tx_fifo.v','sim/tb_cpu_integration.sv']]
    sources.update(paths)
    model_cache = out/'model-cache'
    model_cache.mkdir(parents=True, exist_ok=True)
    model = Path(tempfile.mkdtemp(prefix='model-',dir=model_cache))
    version = run('simulator_version',[args.verilator,'--version'])
    # Verilator 5.006 rejects mixed assignments to the bench's previous_mtime
    # in its two CoreMark-only monitors. Both monitors are disabled in the
    # functional modes below; no CoreMark mode is invoked by this runner.
    compatibility = ['-Wno-BLKANDNBLK'] if 'Verilator 5.006 ' in version else []
    run('cpu_compile',[args.verilator,'--binary','--timing','-j','2','-CFLAGS','-Os',
        '-CFLAGS','-fno-declone-ctor-dtor','-Wno-fatal',*compatibility,
        '--top-module','tb_cpu_integration','--Mdir',model,*paths],timeout=1800)
    run('cpu_integration',[model/'Vtb_cpu_integration',cpu_arg], 'CPU_AXI_CLINT_UART_DDR_PASS',timeout=300)
    run('production_console',[model/'Vtb_cpu_integration','+production_bootloader',cpu_arg],
        'CPU_PRODUCTION_CONSOLE_PASS',timeout=300)
    record = receipt('CPU_CLOCK_FUNCTIONAL_PASS')
    record['model_directory'] = str(model)
    record['compatibility_options'] = compatibility
    (out/'results.json').write_text(json.dumps(record,indent=2)+'\n')
    print(record['status'],flush=True)


if __name__=='__main__':
    main()
