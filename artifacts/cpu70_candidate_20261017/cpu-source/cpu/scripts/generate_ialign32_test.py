"""Whole-core IALIGN32 and illegal-C oracle, independent of the seven older tests."""
from pathlib import Path
import argparse
import json

root = Path(__file__).resolve().parent.parent
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--output', type=Path, default=root / 'work/cpu-test')
out = parser.parse_args().output.resolve()
out.mkdir(parents=True, exist_ok=True)

lines = [
    '.option norvc', '.option norelax', '.section .init,"ax"',
    '.globl _start', '_start:', 'la t0, trap', 'csrw mtvec, t0',
    'li s4, 0', 'li s5, 0x13579bdf', 'mv a0, s5',
    # A not-taken branch must not raise an alignment fault for its +2 target.
    'li s0, 31', 'not_taken:', '.word 0x00001163',  # bne zero,zero,+2
    'bnez s4, fail',
]
cases = [
    ('taken_branch', ['.word 0x00000963'], 0),  # beq zero,zero,+18
    ('jal', ['.word 0x0120056f'], 0),          # jal a0,+18
    ('jalr', ['jalr a0, 0(t0)'], 0),
    ('jalr_odd', ['jalr a0, 0(t0)'], 0),      # bit 0 is cleared before checking bit 1
    ('c_nop', ['.word 0x00010001'], 2),
    ('c_ebreak', ['.word 0x00009002'], 2),
]
for name, instruction, cause in cases:
    lines += [f'li s0, {cause}', f'la s1, fault_{name}',
              f'la s3, resume_{name}', 'mv a0, s5']
    # Target a different aligned word +2. A faulty implementation that retires
    # the branch and traps on target fetch would then save a different mepc;
    # source+2 alone would hide that mistake when mepc bit 1 is masked.
    lines += ['addi s2, s1, 18'] if cause == 0 else ['li s2, 0']
    if name.startswith('jalr'):
        lines += [f'addi t0, s1, {19 if name == "jalr_odd" else 18}']
    lines += ['.balign 4', f'fault_{name}:'] + instruction
    # Trap handler chooses this exact word-aligned continuation. A missing trap
    # also arrives here, but the final exact count and unchanged link reject it.
    lines += [f'resume_{name}:', 'bne a0, s5, fail']

lines += [
    f'li t0, {len(cases)}', 'bne s4, t0, fail', 'j pass',
    '.balign 4', 'trap:',
    'csrr t3, mcause', 'bne t3, s0, fail',
    'csrr t4, mepc', 'bne t4, s1, fail',
    # This CPU reports zero mtval for illegal instructions; alignment faults
    # must report the bad target, not the PC of the instruction raising them.
    'csrr t5, mtval', 'bne t5, s2, fail', 'addi s4, s4, 1',
    # IALIGN32 masks both low mepc bits on a software write and on MRET.
    'addi t4, s3, 3', 'csrw mepc, t4', 'csrr t5, mepc',
    'bne t5, s3, fail', 'mret',
]
for label, marker in [('pass', 'CPU_TEST_PASS!'), ('fail', 'CPU_TEST_FAIL!')]:
    lines += [label + ':', 'li x29, 0x1fe001e0']
    for char in marker:
        lines += [f'li x30, {ord(char)}', 'sb x30, 0(x29)']
    lines += [f'{label}_halt:', f'j {label}_halt']
(out / 'test.S').write_text('\n'.join(lines) + '\n', encoding='utf-8')
(out / 'oracle.json').write_text(json.dumps({
    'name': 'ialign32', 'expected_traps': len(cases),
    'cases': [name for name, _, _ in cases],
    'checks': ['taken branch/JAL/JALR word+2: mcause=0, mepc=source, mtval=target',
               'JALR clears target bit 0 before alignment check',
               'not-taken word+2 branch does not trap',
               'faulting JAL/JALR do not write the link register',
               'C.NOP/C.EBREAK encodings are illegal (mcause=2), not executable/breakpoints',
               'mepc write clears both low bits and MRET resumes at the correct word'],
    'illegal_mtval_policy': 'Current CPU returns zero, permitted by the architecture',
}, indent=2) + '\n', encoding='utf-8')

tb = (root / 'coremark_test_soc/sim/tb_coremark_soc.v').read_text(encoding='utf-8')
tb = tb.replace('tb_coremark_soc', 'tb_cpu_architecture').replace('TB_COREMARK_SOC', 'TB_CPU_ARCHITECTURE')
tb = tb.replace('8*13', '8*14').replace('8*12', '8*13')

def replace_once(old, new):
    global tb
    assert tb.count(old) == 1, f'testbench anchor must occur once: {old}'
    tb = tb.replace(old, new)

replace_once('integer cycle_count = 0;', 'integer cycle_count = 0;\n    integer ialign_trap_count = 0;')
replace_once('$fatal(1,"Unexpected architectural trap in CoreMark pc=%h",dut.u_cpu.core.backend.cmt_csr_pc);',
             'ialign_trap_count <= ialign_trap_count + 1;')
replace_once('if (marker_next == "COREMARK_DONE")',
             'if (marker_next == "CPU_TEST_FAIL!") $fatal(1,"IALIGN32 instruction oracle mismatch");\n'
             '            if (marker_next == "CPU_TEST_PASS!")')
replace_once('$fclose(uart_log);',
             'if (ialign_trap_count != 6) $fatal(1,"IALIGN32 trap count %0d != 6",ialign_trap_count);\n'
             '                $display("IALIGN32_CHECKS_PASS traps=%0d",ialign_trap_count);\n'
             '                $fclose(uart_log);')
tb_path = out / 'tb_cpu_architecture.v'
if not tb_path.exists() or tb_path.read_text(encoding='utf-8') != tb:
    tb_path.write_text(tb, encoding='utf-8')
print(out)
