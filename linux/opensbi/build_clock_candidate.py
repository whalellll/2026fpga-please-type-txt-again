"""Build isolated clock-matched OpenSBI/DTB and a RAM-only read-only-SD loader.

Run under WSL. This does not invoke FPGA tools, open a serial port or write SD.
The release boot ROM/CoreMark firmware is never rebuilt by this helper.
"""
import argparse
import hashlib
import json
import math
from pathlib import Path
import shutil
import struct
import subprocess
import zlib


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def clock_candidate_ratio(clock):
    assert clock['pll_vco_hz'] == 891000000 and clock['sys_hz'] == clock['timebase_hz'] == 49500000
    divisor = clock['cpu_divisor']
    mode = clock.get('cpu_clock_source', 'video891')
    profiles={'dedicated850p5':(850500000,{12}), 'dedicated675':(675000000,{9}),
              'dedicated800':(800000000,{10}), 'dedicated1080frac':(1080000000,{27,36}), 'dedicated1147p5frac':(1147500000,{27}), 'dedicated945frac':(945000000,{27}), 'video891':(891000000,set(range(12,19)))}
    assert mode in profiles
    cpu_vco,divisors=profiles[mode]
    assert divisor in divisors and clock.get('cpu_pll_vco_hz',cpu_vco)==cpu_vco
    if mode=='dedicated800':assert clock['cpu_reference_hz']==125000000
    factor=2 if mode in ('dedicated1080frac','dedicated1147p5frac','dedicated945frac') else 1
    if mode in ('dedicated1080frac','dedicated1147p5frac','dedicated945frac'):assert clock['cpu_reference_hz']==27000000 and clock['cpu_output_divisor_eighths']==divisor*4
    assert clock['cpu_hz']==(2*cpu_vco*factor+divisor)//(2*divisor)
    ticks=clock['timebase_hz']*divisor
    common=math.gcd(ticks,cpu_vco*factor)
    return ticks//common,cpu_vco*factor//common


def enable_stagea_gather_dts(source):
    replacements = (
        ('        pikafish-pff1@10000000 {',
         '        pikafish_pff1: pikafish-pff1@10000000 {'),
        ('reg = <0x1fe10000 0x00000100>;', 'reg = <0x1fe10000 0x00000200>;'),
        ('memory-region = <&mac_accel_mem>;',
         'memory-region = <&mac_accel_mem &pikafish_pff1>;'),
    )
    for before, after in replacements:
        if source.count(before) != 1:
            raise ValueError('Unexpected PFF1 gather device-tree contract: '+before)
        source = source.replace(before, after)
    return source


def reserve_clint_mmio_dts(source):
    # The CPU wrapper decodes 0x0200xxxx as CLINT rather than DDR.
    # This range lies inside memory@0 and must not reach alloc_pages().
    if 'clint-mmio@2000000' in source:
        import re
        nodes = re.findall(r'clint-mmio@2000000\s*\{([^}]+)\}', source)
        if len(nodes) != 1 or not re.search(r'reg\s*=\s*<0x02000000\s+0x00010000>', nodes[0]) or 'no-map;' not in nodes[0]:
            raise ValueError('Invalid CLINT reserved-memory contract')
        return source
    before = '        // Used by the flash FW_PAYLOAD recipe in the guide.'
    if source.count(before) != 1:
        raise ValueError('Missing reserved-memory insertion anchor')
    node = ('        // CLINT MMIO is decoded inside the low DDR address range.\n'
            '        // Never let the Linux buddy allocator hand these pages out.\n'
            '        clint-mmio@2000000 {\n'
            '            reg = <0x02000000 0x00010000>;\n'
            '            no-map;\n'
            '        };\n\n')
    return source.replace(before, node+before)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--archive', type=Path, required=True)
    parser.add_argument('--clock-config', type=Path, required=True)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[2]
    out = args.output.resolve()
    out.mkdir(parents=True, exist_ok=False)
    clock = json.loads(args.clock_config.read_text())
    numerator, denominator = clock_candidate_ratio(clock)
    assert sha(args.archive) == 'ee5be2c582f9a837e9db88368220758e014dd694b566bb6c8efe1e50cfad0004'
    source = root/'sw/bootloader'
    loader_source = root/'artifacts/voice_hw_candidate_20261016/loader'
    dts = root/'artifacts/voice_hw_candidate_20261016/boot/voice.soc.dts'
    inputs = [args.archive.resolve(), args.clock_config.resolve(), Path(__file__).resolve(),
              dts, loader_source/'loader.c', loader_source/'start.S', loader_source/'link.ld',
              root/'linux/opensbi/pg2l_timer_bridge.h',
              root/'linux/opensbi/0001-pg2l-clock-config-timer-bridge.patch']
    inputs += sorted(source.glob('*.h'))
    inputs += [source/name for name in ('runtime.c', 'sd_native.c', 'fat_ro.c', 'crc32_fast.c')]
    hashes = {str(p): sha(p) for p in inputs}
    record = {'schema': 1, 'status': 'BUILDING_NOT_BOARD_TESTED', 'clocks': clock,
              'ratio': [numerator, denominator], 'inputs_sha256': hashes, 'commands': [],
              'scope': 'RAM loader and candidate Linux boot only; no CoreMark firmware, FPGA, SD or Flash writes'}

    def save():
        (out/'boot-manifest.json').write_text(json.dumps(record, indent=2)+'\n')

    def run(name, command, cwd=None, timeout=300):
        command = [str(v) for v in command]
        record['commands'].append({'name': name, 'argv': command})
        save()
        process = subprocess.run(command, cwd=cwd or out, capture_output=True, timeout=timeout)
        log = process.stdout+process.stderr
        (out/(name+'.txt')).write_bytes(log)
        record['commands'][-1].update(exit=process.returncode, log_sha256=hashlib.sha256(log).hexdigest())
        if process.returncode:
            record['status'] = 'BUILD_FAILED_NOT_BOARD_TESTED'
            save()
            raise RuntimeError(f'{name}: {log.decode(errors="replace")[-2500:]}')
        save()
        return log.decode(errors='replace')

    tree = out/'source'
    tree.mkdir()
    run('extract', ['tar', '-xzf', args.archive.resolve(), '-C', tree])
    tree /= 'opensbi-1.3.1'
    run('patch', ['patch', '--batch', '--fuzz=0', '-p1', '-i', inputs[8]], cwd=tree)
    shutil.copyfile(root/'linux/opensbi/pg2l_timer_bridge.h', tree/'lib/sbi/pg2l_timer_bridge_impl.h')
    wrapper = f'#define PG2L_TIME_NUMERATOR {numerator}\n#define PG2L_TIME_DENOMINATOR {denominator}\n#include "pg2l_timer_bridge_impl.h"\n'
    (tree/'lib/sbi/pg2l_timer_bridge.h').write_text(wrapper)
    (out/'pg2l_clock_ratio.h').write_text(wrapper)
    run('opensbi_compiler', ['riscv64-linux-gnu-gcc', '-v'])
    run('opensbi_build', ['make', '-j4', 'PLATFORM=generic', 'FW_TEXT_START=0x18000000',
        'FW_JUMP_ADDR=0x00400000', 'FW_JUMP_FDT_ADDR=0x1a000000',
        'CROSS_COMPILE=riscv64-linux-gnu-', 'PLATFORM_RISCV_XLEN=32',
        'PLATFORM_RISCV_ISA=rv32ima_zicsr_zifencei', 'PLATFORM_RISCV_ABI=ilp32'], cwd=tree, timeout=900)
    firmware = tree/'build/platform/generic/firmware'
    for name in ('fw_jump.bin', 'fw_jump.elf'):
        shutil.copyfile(firmware/name, out/name)
    assert 200000 < (out/'fw_jump.bin').stat().st_size < 327680

    driver_dts = out/'driver-gather.dts'
    driver_dts.write_text(reserve_clint_mmio_dts(enable_stagea_gather_dts(dts.read_text())))
    run('dtc', ['dtc', '-I', 'dts', '-O', 'dtb', '-o', out/'soc.dtb', driver_dts])
    clint_reg = run('fdtget_clint_reserved', ['fdtget', '-t', 'x', out/'soc.dtb',
                    '/reserved-memory/clint-mmio@2000000', 'reg'])
    assert clint_reg.split() == ['2000000', '10000']
    run('fdtget_clint_no_map', ['fdtget', out/'soc.dtb',
                              '/reserved-memory/clint-mmio@2000000', 'no-map'])
    for node, prop in (('/cpus', 'timebase-frequency'), ('/cpus/cpu@0', 'clock-frequency')):
        run('fdtput_'+prop, ['fdtput', '-t', 'u', out/'soc.dtb', node, prop, clock['cpu_hz']])
        value = run('fdtget_'+prop, ['fdtget', '-t', 'u', out/'soc.dtb', node, prop])
        assert int(value.strip()) == clock['cpu_hz']
    run('candidate_dts', ['dtc', '-I', 'dtb', '-O', 'dts', '-o', out/'soc.dts', out/'soc.dtb'])

    loader = out/'loader'
    loader.mkdir()
    for name in ('start.S', 'link.ld'):
        shutil.copyfile(loader_source/name, loader/name)
    fw, dtb = (out/'fw_jump.bin').read_bytes(), (out/'soc.dtb').read_bytes()
    def array(symbol, data):
        return 'static const unsigned char '+symbol+'[] = {\n'+''.join(
            ','.join(f'0x{v:02x}' for v in data[i:i+16])+',\n' for i in range(0,len(data),16))+'};\n'
    (loader/'opensbi_timer_bridge.inc').write_text(array('fw_jump_bin', fw)+array('clock_dtb_bin', dtb))
    replacement = f'''static void publish_clock_payload(uint32_t address, const uint8_t *data, uint32_t bytes)
{{
    volatile uint32_t *cached=(volatile uint32_t *)(uintptr_t)address;
    volatile uint32_t *alias=(volatile uint32_t *)(uintptr_t)(address|0x80000000u);
    uint32_t i;
    for(i=0;i<(bytes+3u)/4u;i++) {{
        uint32_t j,value=0;
        for(j=0;j<4;j++) if(i*4u+j<bytes) value|=(uint32_t)data[i*4u+j]<<(j*8u);
        cached[i]=value; alias[i]=value;
    }}
    __asm__ volatile("fence iorw, iorw" ::: "memory");
}}
static int patch_sbi_timer_bridge(void)
{{
    if(REG32(CPU_HZ_REG)!={clock['cpu_hz']}u || REG32(TIMEBASE_HZ_REG)!=49500000u) return 0;
    publish_clock_payload(0x18000000u,fw_jump_bin,sizeof(fw_jump_bin));
    publish_clock_payload(0x1a000000u,clock_dtb_bin,sizeof(clock_dtb_bin));
    /* The uncached DDR alias requires word accesses, including CRC tails. */
    if(copy_to_uncached(0x18000000u,sizeof(fw_jump_bin))!=0x{zlib.crc32(fw):08x}u) return 0;
    if(copy_to_uncached(0x1a000000u,sizeof(clock_dtb_bin))!=0x{zlib.crc32(dtb):08x}u) return 0;
    __asm__ volatile("fence iorw, iorw\\n\\t.word 0x0000100f" ::: "memory");
    console_puts("CPU_CLOCK_RAM_BOOT_PATCH cpu_hz={clock['cpu_hz']} sys_hz=49500000 ratio={numerator}/{denominator}\\n");
    return 1;
}}'''
    text = (loader_source/'loader.c').read_text()
    start = text.index('static int patch_sbi_timer_bridge(void)')
    end = text.index('\n}\n#endif', start)+2
    (loader/'loader.c').write_text(text[:start]+replacement+text[end:])
    cc = '/opt/toolchain/bin/riscv32-linux-musl-gcc'
    flags = ['-march=rv32ima', '-Wa,-march=rv32ima_zicsr_zifencei', '-mabi=ilp32',
             '-mcmodel=medany', '-mno-relax', '-msmall-data-limit=0', '-mstrict-align',
             '-ffreestanding', '-fno-builtin', '-fno-common', '-ffunction-sections',
             '-fdata-sections', '-Os', '-Wall', '-Wextra', '-Werror',
             '-DSD_LOADER_BRIDGE_NONBLOCK_BOOT=1', '-DSD_LOADER_SBI_TIMER_BRIDGE=1', '-I', source]
    run('loader_compiler', [cc, '-v'])
    objects = []
    for name, path in [('start', loader/'start.S'), ('loader', loader/'loader.c')]+[
            (name, source/(name+'.c')) for name in ('runtime','sd_native','fat_ro','crc32_fast')]:
        obj = loader/(name+'.o')
        run('compile_'+name, [cc, *flags, '-c', path, '-o', obj])
        objects.append(obj)
    run('loader_link', [cc, '-march=rv32ima', '-mabi=ilp32', '-nostdlib', '-static',
        '-Wl,--gc-sections,--no-relax', '-Wl,-T,'+str(loader/'link.ld'),
        '-Wl,-Map,'+str(loader/'loader.map'), *objects, '-lgcc', '-o', out/'loader-cpu-clock.elf'])
    run('loader_binary', ['/opt/toolchain/bin/riscv32-linux-musl-objcopy', '-O', 'binary',
                         out/'loader-cpu-clock.elf', out/'loader-cpu-clock.bin'])
    assert (out/'loader-cpu-clock.bin').stat().st_size < 0x100000
    for name in ('fw_jump.elf', 'loader-cpu-clock.elf'):
        elf = (out/name).read_bytes()
        assert elf[:6] == b'\x7fELF\x01\x01' and struct.unpack_from('<H',elf,18)[0] == 243
        assert struct.unpack_from('<I',elf,36)[0] & 7 == 0, 'C or hardware float ABI enabled'
        run(name+'_attributes', ['riscv64-linux-gnu-readelf', '-h', '-A', out/name])
    assert hashes == {str(p): sha(p) for p in inputs}, 'Build inputs changed'
    record['outputs_sha256'] = {name: sha(out/name) for name in
        ('fw_jump.bin','fw_jump.elf','soc.dtb','soc.dts','loader-cpu-clock.bin','loader-cpu-clock.elf','pg2l_clock_ratio.h')}
    record['status'] = 'BOOT_CANDIDATE_BUILT_NOT_BOARD_TESTED'
    save()
    print(record['status']+' cpu_hz='+str(clock['cpu_hz'])+' ratio='+str(record['ratio']))


if __name__ == '__main__':
    main()
