"""Architectural RV32A checks, including old/new value separation and LR/SC."""
from pathlib import Path
import runpy
import json
root=Path(__file__).resolve().parent.parent
runpy.run_path(str(root/'scripts/generate_cpu_test.py'))
out=root/'work/cpu-test'
lines=['.section .init,"ax"','.globl _start','_start:', 'li s0, 0x1c010000']
old=0x80000003
cases=[('amoadd',0x80000008),('amoswap',5),('amoxor',0x80000006),
       ('amoor',0x80000007),('amoand',1),('amomin',old),('amomax',5),
       ('amominu',5),('amomaxu',old)]
for index,(op,new) in enumerate(cases):
    lines += [f'li t0, 0x{old:08x}','sw t0, 0(s0)','li t1, 5',
              f'{op}.w.aqrl t2, t1, (s0)','bne t2, t0, fail',
              'addi t3, t2, 1',f'li t4, 0x{old+1:08x}','bne t3, t4, fail',
              'lw t3, 0(s0)',f'li t4, 0x{new:08x}','bne t3, t4, fail']
lines += [
    'li t0, 21','sw t0, 0(s0)',
    'lr.w.aq t1, (s0)','addi t1, t1, 1','sc.w.rl t2, t1, (s0)',
    'bnez t2, fail','lw t3, 0(s0)','li t4, 22','bne t3, t4, fail',
    'sc.w t2, zero, (s0)','beqz t2, fail','lw t3, 0(s0)','bne t3, t4, fail',
    'addi s1, s0, 4','lr.w t1, (s0)','sc.w t2, t1, (s1)','beqz t2, fail',
    'lr.w t1, (s0)','sw zero, 0(s1)','sc.w t2, t1, (s0)','beqz t2, fail',
    'li t1, 7','amoswap.w zero, t1, (s0)','lw t3, 0(s0)','bne t3, t1, fail',
    # Reservation creation must also work with rd=x0.
    'lr.w zero, (s0)','sc.w t2, t4, (s0)','bnez t2, fail',
    'lw t3, 0(s0)','bne t3, t4, fail',
    # Force an uncached-in-L1 line to exercise refill ownership.
    'li s0, 0x1c012000','lr.w t1, (s0)','bnez t1, fail',
    'li t1, 91','sc.w t2, t1, (s0)','bnez t2, fail',
    'lw t3, 0(s0)','bne t3, t1, fail',
    'li t0, 9','li t1, 3','div t2, t0, t1','li t3, 3',
    'beq t2, t3, skipped_atomic','amoswap.w t4, zero, (s0)',
    'skipped_atomic:','lw t3, 0(s0)','li t4, 91','bne t3, t4, fail',
]
for label,marker in [('pass','CPU_TEST_PASS!'),('fail','CPU_TEST_FAIL!')]:
    lines += [label+':','li t4, 0x1fe001e0']
    for char in marker: lines += [f'li t5, {ord(char)}','sb t5, 0(t4)']
    lines += [label+'_halt:','j '+label+'_halt']
(out/'test.S').write_text('\n'.join(lines)+'\n')
(out/'oracle.json').write_text(json.dumps({'checks':['nine AMOs','old/new data separation',
    'dependent consumer','aq/rl','SC success/failure','address mismatch','store invalidation',
    'rd zero','cache miss','wrong-path atomic suppression']},indent=2))
