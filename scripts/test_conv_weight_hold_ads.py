"""Positive mapped pad fixture and actual identity/bypass faults using frozen RAMs."""
from pathlib import Path
import argparse, hashlib, json, re
from audit_icache_pad_ads import module
from audit_conv_weight_hold_ads import audit
p=argparse.ArgumentParser();p.add_argument('--baseline-vm',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
source=a.baseline_vm.read_text();body=module(source,'mac_conv_weight_dma')
m=re.search(r'(\.load_data\s*\()([^()]+)(\))',body);assert m
arg=m[2];newarg=arg.replace('line_shift[120]','conv_hold_lo').replace('line_shift[121]','conv_hold_hi');assert arg!=newarg
body=body[:m.start(2)]+newarg+body[m.end(2):]
pad="""
wire conv_hold_lo,conv_hold_hi;
(* PAP_DONT_TOUCH *) GTP_LUT6D #(.INIT(64'hCCCCCCCC_AAAAAAAA))
\\g_folded.g_stream.u_line_write_hold_lut (
 .I0(line_shift[120]), .I1(line_shift[121]), .I2(1'b0), .I3(1'b0), .I4(1'b0), .I5(1'b1),
 .Z5(conv_hold_lo), .Z(conv_hold_hi));
"""
body=body.replace('endmodule',pad+'\nendmodule')
fixture='module soc_top(input clk);\nmac_conv_weight_dma u_weight (.clk(clk));\nendmodule\n'+body+'\n'+module(source,'mac_weight_double_buffer')
proof=audit(fixture);assert proof['padded_di_pins']==4
faults={
 'identity_bit':fixture.replace("64'hCCCCCCCC_AAAAAAAA","64'hCCCCCCCC_AAAAAAAB"),
 'swapped_source':fixture.replace('.I0(line_shift[120])','.I0(line_shift[121])'),
 'child_bypass':fixture.replace('conv_hold_lo,','line_shift[120],',1),
}
rejected=[]
for name,mutant in faults.items():
 assert mutant!=fixture
 try:audit(mutant)
 except (AssertionError,ValueError,KeyError):rejected.append(name)
 else:raise RuntimeError('Accepted native pad fault '+name)
assert not a.output.exists()
a.output.write_text(json.dumps(dict(status='CONV_HOLD_NATIVE_FIXTURE_AND_THREE_FAULTS_PASS',truth_cases=4,padded_di_pins=4,faults=rejected,baseline_vm_sha256=hashlib.sha256(a.baseline_vm.read_bytes()).hexdigest()),indent=2)+'\n')
print('CONV_HOLD_NATIVE_FIXTURE_AND_THREE_FAULTS_PASS')
