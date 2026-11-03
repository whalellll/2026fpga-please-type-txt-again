"""Positive native-shape fixture and adversarial hold-pad retention mutations."""
from audit_pikafish_linear_hold_ads import audit

def fixture():
    rows=['module pikafish_mlp_dedicated();']
    for pair in range(16):
        inputs=[f'lin_pack[{pair*2+i}]' if pair*2+i<24 else f'linear_q[{pair*2+i-24}]' for i in range(2)]
        inputs=["1'b0" if (pair*2+i)%8==7 else item for i,item in enumerate(inputs)]
        rows.append(f"(* PAP_DONT_TOUCH *) GTP_LUT6D #(.INIT(64'hCCCCCCCCAAAAAAAA)) \\g_linear_hold[{pair}].u_linear_hold_lut "
                    f"(.I0({inputs[0]}),.I1({inputs[1]}),.I2(1'b0),.I3(1'b0),.I4(1'b0),.I5(1'b1),.Z5(pad[{pair*2}]),.Z(pad[{pair*2+1}]));")
        for bank in range(2):
            rows.append(f'GTP_RAM32X2DP lin{bank}_{pair} (.DI({{pad[{pair*2+1}],pad[{pair*2}]}}),.WCLK(clk));')
    return '\n'.join(rows)+'\nendmodule\n'

source=fixture();assert audit(source)['padded_di_pins']==56
faults=[source.replace('PAP_DONT_TOUCH','UNKNOWN',1),
        source.replace('CCCCCCCCAAAAAAAA','CCCCCCCCAAAAAAAB',1),
        source.replace('.I0(lin_pack[20])','.I0(lin_pack[21])',1),
        source.replace('.I1(lin_pack[21])',".I1(1'b0)",1),
        source.replace('.DI({pad[21],pad[20]})','.DI({lin_pack[21],pad[20]})',1),
        source.replace('.DI({pad[21],pad[20]})','.DI({pad[20],pad[21]})',1),
        source.replace('GTP_RAM32X2DP lin1_10','MISSING_RAM lin1_10',1),
        source.replace('.u_linear_hold_lut ','.missing_pad ',1)]
for i,fault in enumerate(faults):
    try:audit(fault)
    except AssertionError:continue
    raise AssertionError(('Native pad checker accepted a fault',i))
print(f'PIKAFISH_LINEAR_HOLD_CHECKER_MUTATIONS_PASS positive=1 rejected={len(faults)}')
