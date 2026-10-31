"""Deterministic RV32IM instruction oracle; no CoreMark workload or score."""
from pathlib import Path
import random
import json

root = Path(__file__).resolve().parent.parent
out = root/'work/cpu-test'
out.mkdir(parents=True,exist_ok=True)
rng = random.Random(91001)
mask = (1<<32)-1
def signed(x): return x if x < (1<<31) else x-(1<<32)
regs = [0]+[rng.getrandbits(32) for _ in range(26)]
lines = ['.section .init,"ax"','.globl _start','_start:']
for i in range(1,27): lines.append(f'li x{i}, 0x{regs[i]:08x}')
operations = ['add','sub','xor','and','or','sll','srl','sra','slt','sltu',
              'mul','mulh','mulhu','mulhsu','div','divu','rem','remu']
def checkpoint():
    for i in range(1,27):
        lines.extend([f'li x27, 0x{regs[i]:08x}',f'bne x{i}, x27, fail'])
for n in range(512):
    rd,rs1,rs2 = (rng.randrange(1,27),rng.randrange(27),rng.randrange(27))
    op = rng.choice(operations)
    a,b=regs[rs1],regs[rs2]; sa,sb=signed(a),signed(b)
    if op=='add': value=a+b
    elif op=='sub': value=a-b
    elif op=='xor': value=a^b
    elif op=='and': value=a&b
    elif op=='or': value=a|b
    elif op=='sll': value=a<<(b&31)
    elif op=='srl': value=a>>(b&31)
    elif op=='sra': value=sa>>(b&31)
    elif op=='slt': value=int(sa<sb)
    elif op=='sltu': value=int(a<b)
    elif op=='mul': value=a*b
    elif op=='mulh': value=(sa*sb)>>32
    elif op=='mulhu': value=(a*b)>>32
    elif op=='mulhsu': value=(sa*b)>>32
    elif op in ('div','rem'):
        q = -1 if b==0 else (abs(sa)//abs(sb)) * (-1 if (sa<0)!=(sb<0) else 1)
        value=q if op=='div' else (sa if b==0 else sa-q*sb)
    elif op=='divu': value=mask if b==0 else a//b
    elif op=='remu': value=a if b==0 else a%b
    regs[rd]=value&mask
    lines.append(f'{op} x{rd}, x{rs1}, x{rs2}')
    if n%32==31: checkpoint()
lines += [
    'li x28, 0x1c010000','li x1, 0x80ff7f01','sw x1, 0(x28)',
    'lw x2, 0(x28)','bne x1, x2, fail',
    'lb x3, 3(x28)','li x27, -128','bne x3, x27, fail',
    'lbu x3, 3(x28)','li x27, 128','bne x3, x27, fail',
    'lh x3, 2(x28)','li x27, -32513','bne x3, x27, fail',
    'lhu x3, 2(x28)','li x27, 33023','bne x3, x27, fail',
    'li x1, 8','li x2, 0','loop:', 'addi x2, x2, 1','addi x1, x1, -1','bne x1, x0, loop',
    'li x27, 8','bne x2, x27, fail',
    'jal x5, link_target','link_return:','j link_done','link_target:',
    'la x27, link_return','bne x5, x27, fail','jalr x0, 0(x5)','link_done:',
    'li x10, 0x12345678','csrrw x11, mscratch, x10','csrrs x12, mscratch, x0',
    'bne x10, x12, fail',
]
for label,marker in [('pass','CPU_TEST_PASS!'),('fail','CPU_TEST_FAIL!')]:
    lines += [label+':','li x29, 0x1fe001e0']
    for char in marker: lines += [f'li x30, {ord(char)}','sb x30, 0(x29)']
    lines += [f'{label}_halt:',f'j {label}_halt']
(out/'test.S').write_text('\n'.join(lines)+'\n')
(out/'oracle.json').write_text(json.dumps({'seed':91001,'random_operations':512,
    'checks':'register checkpoints, load widths, branch recovery, JAL/JALR, CSR'},indent=2))
tb=(root/'coremark_test_soc/sim/tb_coremark_soc.v').read_text()
tb=tb.replace('tb_coremark_soc','tb_cpu_architecture').replace('TB_COREMARK_SOC','TB_CPU_ARCHITECTURE')
tb=tb.replace('"COREMARK_DONE"','"CPU_TEST_PASS!"')
# Both architecture markers use fourteen bytes; resize the generated UART shift register.
tb=tb.replace('8*13','8*14').replace('8*12','8*13')
tb=tb.replace('if (marker_next == "CPU_TEST_PASS!")',
    'if (marker_next == "CPU_TEST_FAIL!") $fatal(1,"CPU instruction oracle mismatch");\n            if (marker_next == "CPU_TEST_PASS!")')
tb_path = out/'tb_cpu_architecture.v'
if not tb_path.exists() or tb_path.read_text() != tb:
    tb_path.write_text(tb)
print(out)
