"""Deliberate mapped-netlist faults must fail the ROB pad retention gate."""
from audit_rob_vaddr_pad_ads import audit


def fixture():
    pad = '\n'.join(
        "(* PAP_DONT_TOUCH *) GTP_LUT6D #(.INIT(64'hCCCCCCCC_AAAAAAAA)) "
        + f"\\data_pad[{i}].u_hold_dual_lut "
        + f"(.I0(dataIn[{2*i}]),.I1(dataIn[{2*i+1}]),"
        + ".I2(1'b0),.I3(1'b0),.I4(1'b0),.I5(1'b1),"
        + f".Z5(dataOut[{2*i}]),.Z(dataOut[{2*i+1}]));" for i in range(16))
    fields = (['io_memFwd_uncached'] + [f'io_memFwd_size[{i}]' for i in range(2,-1,-1)]
              + [f'io_memFwd_wstrb[{i}]' for i in range(3,-1,-1)]
              + [f'memVaddrWrite[{i}]' for i in range(31,-1,-1)]
              + [f'io_memFwd_paddr[{i}]' for i in range(31,-1,-1)])
    rob = ('module Rob ();\nPangoRobVaddrPad memVaddrWrite_memVaddrPad '
           '(.dataIn(io_memFwd_vaddr),.dataOut(memVaddrWrite));\n'
           'RobHead80 headSelector (.io_mask(headMask));\n'
           'memPayloadFwd_32x72 memPayloadFwd_ext (.R0_clk(clock),.W0_addr(io_memFwd_robid),'
           '.W0_data({' + ','.join(fields) + '}));\nendmodule\n')
    ram = '\n'.join('GTP_RAM32X2DP ' + f'm{bank}_{i} '
        + f'(.DI({{W0_data[{2*i+1}],W0_data[{2*i}]}}),'
        + f'.DO({{R{bank}_data[{2*i+1}],R{bank}_data[{2*i}]}}),'
        + '.WCLK(R0_clk),.WE(W0_en),.WADDR(W0_addr));'
        for bank in range(2) for i in range(36))
    head = '\n'.join(f'GTP_DFF_R q{i} (.D(zero),.Q(io_mask[{i}]),.CLK(clock));' for i in range(16))
    return ('module PangoRobVaddrPad ();\n' + pad + '\nendmodule\n' + rob
            + 'module memPayloadFwd_32x72 ();\n' + ram + '\nendmodule\n'
            + 'module RobHead80 ();\n' + head + '\nendmodule\n')


def main():
    original = fixture()
    good = audit(original)
    assert good['padded_di_pins'] == 64 and good['head_register_bits'] == 16
    faults = {
        'init': ("64'hCCCCCCCC_AAAAAAAA", "64'h0"),
        'attribute': ('(* PAP_DONT_TOUCH *)', ''),
        'pad_source': ('.dataIn(io_memFwd_vaddr)', ".dataIn(1'b0)"),
        'pad_input_bit': ('.I0(dataIn[0])', '.I0(dataIn[1])'),
        'pad_output_bit': ('.Z5(dataOut[0])', '.Z5(dataOut[1])'),
        'output_disconnected': ('.dataOut(memVaddrWrite)', '.dataOut(unused)'),
        'ram_parent_bypass': ('memVaddrWrite[9]', 'io_memFwd_vaddr[9]'),
        'ram_di_swapped': ('.DI({W0_data[41],W0_data[40]})', '.DI({W0_data[40],W0_data[40]})'),
        'ram_type': ('GTP_RAM32X2DP m0_0', 'GTP_RAM64X1DP m0_0'),
        'head_ff_duplicate': ('.Q(io_mask[0])', '.Q(io_mask[1])'),
        'head_ff_removed': ('GTP_DFF_R q0', 'GTP_LUT1 q0'),
    }
    for name, (before, after) in faults.items():
        assert before in original
        try:
            audit(original.replace(before, after, 1))
        except (ValueError, AssertionError, KeyError):
            continue
        raise AssertionError('Accepted ROB pad/head fault: ' + name)
    print('ROB_VADDR_PAD_ADS_MUTATIONS_PASS faults=' + str(len(faults)))


if __name__ == '__main__': main()
