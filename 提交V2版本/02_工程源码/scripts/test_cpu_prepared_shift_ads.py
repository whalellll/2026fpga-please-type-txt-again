"""Synthetic structural fixtures only; no FPGA or performance acceptance."""
import hashlib,json
from pathlib import Path
import tempfile
from audit_cpu_prepared_shift_ads import audit

checker=Path(__file__).with_name('audit_cpu_prepared_shift_ads.py')
with tempfile.TemporaryDirectory(prefix='cpu75-shift-ads-') as d:
    root=Path(d);rtl=root/'rtl.sv';net=root/'mapped.vm';snapshot=root/'snapshot.json'
    rtl.write_text('// SYNTHETIC ONLY io_shiftSrcPrepared exShiftSrc\n')
    snapshot.write_text(json.dumps({'run_id':'SYNTHETIC_NOT_HARDWARE','inputs':{'rtl/cpu/CoreTop.sv':hashlib.sha256(rtl.read_bytes()).hexdigest(),'scripts/audit_cpu_prepared_shift_ads.py':hashlib.sha256(checker.read_bytes()).hexdigest()}}))
    targets=[f'exShiftSrc[{i}]' for i in range(32)]+['exShiftSign']+[f'exShiftAmount[{i}]' for i in range(5)]
    cells='\n'.join(f'GTP_DFF_E r{i} (.Q({target}),.CLK(clock),.CE(enable),.D(data));' for i,target in enumerate(targets))
    text='module FuAlu\n(input clock);\n'+cells+'\nAlu uAlu (.io_shiftSrcPrepared(exShiftSrc),.io_shiftSignPrepared(exShiftSign),.io_shiftAmountPrepared(exShiftAmount));\nendmodule\nmodule CoreBackend\n();\nFuAlu u_fu_alu0 ();\nFuAlu u_fu_alu1 ();\nendmodule\n'
    net.write_text(text);record=audit(net,rtl,snapshot,checker);assert record['total_register_bits']==76
    cases={'missing_source_bit':text.replace('.Q(exShiftSrc[31])','.Q(missing)'),
      'missing_amount_bit':text.replace('.Q(exShiftAmount[4])','.Q(missing)'),
      'wrong_clock':text.replace('.CLK(clock)','.CLK(sys_clk)',1),
      'combinational_source':text.replace('GTP_DFF_E r0','GTP_LUT1 r0',1),
      'wrong_child_binding':text.replace('.io_shiftSrcPrepared(exShiftSrc)','.io_shiftSrcPrepared(exSrc0)'),
      'only_one_fu':text.replace('FuAlu u_fu_alu1 ();',''),
      'duplicated_fu':text.replace('FuAlu u_fu_alu1 ();','FuAlu u_fu_alu1 ();\nFuAlu u_fu_alu2 ();')}
    for name,value in cases.items():
        net.write_text(value)
        try:audit(net,rtl,snapshot,checker)
        except (AssertionError,KeyError):pass
        else:raise AssertionError('Accepted mutation '+name)
    body='module FuAlu_unq4\n(input clock);\n'+cells+'\nAlu_unq4 uAlu (.io_shiftSrcPrepared(exShiftSrc),.io_shiftSignPrepared(exShiftSign),.io_shiftAmountPrepared(exShiftAmount));\nendmodule\n'
    renamed=text.replace('FuAlu u_fu_alu1 ();','FuAlu_unq4 u_fu_alu1 ();')+body
    net.write_text(renamed);record=audit(net,rtl,snapshot,checker)
    assert len(record['registers'])==76 and {r['fu_module'] for r in record['registers']}=={'FuAlu','FuAlu_unq4'}
    for name,value in {'second_fu_bit_missing':renamed.replace(body,body.replace('.Q(exShiftSrc[31])','.Q(missing)')),
                       'second_fu_binding_wrong':renamed.replace(body,body.replace('.io_shiftSignPrepared(exShiftSign)','.io_shiftSignPrepared(exSrc0)')),
                       'second_fu_clock_wrong':renamed.replace(body,body.replace('.CLK(clock)','.CLK(sys_clk)',1))}.items():
        net.write_text(value)
        try:audit(net,rtl,snapshot,checker)
        except (AssertionError,KeyError):pass
        else:raise AssertionError('Accepted mutation '+name)
    print('PREPARED_SHIFT_ADS_FIXTURES_PASS cases=12 SYNTHETIC_NOT_HARDWARE')
