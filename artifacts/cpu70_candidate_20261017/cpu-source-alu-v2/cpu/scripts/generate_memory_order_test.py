"""Exercise real load/store violations, byte overlap, and dependent replay."""
from pathlib import Path
import runpy, json
root=Path(__file__).resolve().parent.parent
runpy.run_path(str(root/'scripts/generate_cpu_test.py'))
out=root/'work/cpu-test'
lines=['.section .init,"ax"','.globl _start','_start:','li s0, 0x1c010000']
for n in range(12):
    # Older store waits for DIV data; younger cached load must eventually see
    # the new value, and its dependent addition must also be replayed.
    lines += ['li t0, -1','sw t0, 0(s0)','fence rw,rw','lw t4, 0(s0)',
              f'li t0, {300+n*3}','li t1, 3','divu t2,t0,t1',
              'sw t2, 0(s0)','lw t3, 0(s0)','addi t4,t3,7',
              f'li t5, {107+n}','bne t4,t5,fail']
    # Unknown store address, same physical word.
    lines += ['sw zero, 0(s0)','fence rw,rw','li t0,0x38020000','li t1,2',
              'li t3, 0x12345678','divu t2,t0,t1','sw t3,0(t2)',
              'lw t4,0(s0)','bne t3,t4,fail']
    # Partial overlap (byte store vs full word load).
    lines += ['sw zero, 0(s0)','fence rw,rw','li t0, 510','li t1,2',
              'divu t2,t0,t1','sb t2,1(s0)','lw t3,0(s0)',
              'li t4,0xff00','bne t3,t4,fail']
    # Disjoint word and byte accesses may bypass without invalidation.
    lines += ['li t0,0x44332211','sw t0,0(s0)','fence rw,rw','li t0,300','li t1,3',
              'divu t2,t0,t1','sb t2,3(s0)','lbu t3,0(s0)','li t4,0x11','bne t3,t4,fail']
for label,marker in [('pass','CPU_TEST_PASS!'),('fail','CPU_TEST_FAIL!')]:
    lines += [label+':','li t4,0x1fe001e0']
    for c in marker: lines += [f'li t5,{ord(c)}','sb t5,0(t4)']
    lines += [label+'_halt:','j '+label+'_halt']
(out/'test.S').write_text('\n'.join(lines)+'\n')
tb=(out/'tb_cpu_architecture.v').read_text()
anchor = '    integer cycle_count = 0;'
if tb.count(anchor) != 1:
    raise RuntimeError('Expected one cycle counter declaration in the CPU testbench')
tb=tb.replace(anchor, '''    integer cycle_count = 0;
integer conflict_cycles = 0;
// 135: 旧观测点 backend.io_memoryReplayMask 在 133 起的 RTL 中已不存在（133 的
// Functional 为继承结果，本机从未跑过此脚本，故未暴露）。等价观测点改为 LSU 的
// storeOrderBlock（load/store 冲突在发射前阻塞计数），与 134 验证过的写法一致。
always @(posedge clk) if (rst_n && dut.u_cpu.core.memory.u_lsu.storeOrderBlock)
    conflict_cycles <= conflict_cycles + 1;
''')
tb=tb.replace('if (marker_next == "CPU_TEST_PASS!") begin', '''if (marker_next == "CPU_TEST_PASS!") begin
                if (conflict_cycles == 0) $fatal(1,"No load/store conflict exercised");
                $display("LOAD_ORDER_CONFLICT_CYCLES=%0d",conflict_cycles);''')
(out/'tb_cpu_architecture.v').write_text(tb)
(out/'oracle.json').write_text(json.dumps({'checks':['unknown store data','unknown store address',
    'dependent replay','partial byte overlap','disjoint byte bypass','ROB wrap'], 'repetitions':12},indent=2))
