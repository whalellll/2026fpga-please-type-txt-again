"""Check native folded RAS controls and reject LUT mutations; no STA evidence."""
import argparse,json,re,sys
from pathlib import Path
from audit_cpu_ads import Cone,bind_registered_frontend_controls
p=argparse.ArgumentParser();p.add_argument('--netlist',type=Path);p.add_argument('--output',type=Path);a=p.parse_args()
source=a.netlist.read_text() if a.netlist else '''module CoreFrontend ();
GTP_LUT4 #(.INIT(16'hfffe)) r (.I0(pdReturns_0), .I1(pdReturns_1), .I2(pdReturns_2), .I3(pdReturns_3), .Z(selected_return));
GTP_LUT4 #(.INIT(16'hfffe)) c (.I0(pdCalls_0), .I1(pdCalls_1), .I2(pdCalls_2), .I3(pdCalls_3), .Z(selected_call));
GTP_LUT4 #(.INIT(16'h4000)) p (.I0(selected_return), .I1(selected_call), .I2(found), .I3(pdAccept), .Z(actual_push));
Ras ras (.io_specPush(actual_push));
endmodule
'''
c=Cone(source,'CoreFrontend');binding=bind_registered_frontend_controls(c,source)
assert binding['mode']=='folded_ras_push' and binding['truth_cases']>=16,binding
results=[]
for name,target in [('return_selector',binding['return_selector']),('call_selector',binding['call_target']),('actual_push',binding['push_target'])]:
    cc=Cone(source,'CoreFrontend');node,port=cc.drivers[target]
    # Mutate just the observed LUT output cofactor; preserve the other half.
    if port=='Z5':node['init']&=~0xffffffff
    elif node['kind']=='GTP_LUT6D' and node['ports'].get('I5')=="1'b1":node['init']&=0xffffffff
    else:node['init']=0
    try:bind_registered_frontend_controls(cc,source)
    except (ValueError,AssertionError):results.append(name)
    else:raise AssertionError('Accepted mutation '+name)
for name,changed in [('ras_disconnected',source.replace('io_specPush','io_wrongPush')),
                     ('ras_wrong_target',re.sub(r'\.io_specPush\s*\([^)]*\)','.io_specPush(found)',source))]:
    assert changed!=source
    try:bind_registered_frontend_controls(Cone(changed,'CoreFrontend'),changed)
    except (ValueError,AssertionError):results.append(name)
    else:raise AssertionError('Accepted mutation '+name)
if a.output:a.output.write_text(json.dumps({'status':'FOLDED_RAS_CONTROLS_MUTATIONS_PASS_NOT_STA','native_netlist':bool(a.netlist),'binding':binding,'rejected':results},indent=2)+'\n')
print('FOLDED_RAS_CONTROLS_MUTATIONS_PASS')
