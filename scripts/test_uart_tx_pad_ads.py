"""Small synthetic ADS fixtures only; no PDS process or hardware access."""
import copy
import json
from pathlib import Path
import tempfile

from audit_uart_tx_pad_ads import audit, bind_result, sha


def fixture():
    text = ['module soc_top (input sys_clk);',
            '    axi_boot_periph u_local (.clk (sys_clk));', 'endmodule',
            'module axi_boot_periph (input clk);',
            '    uart_tx_fifo u_tx (.clk (clk));', 'endmodule',
            'module uart_tx_fifo (input clk, input push, input [7:0] push_data);',
            '    wire [3:0] wr_ptr;', '    wire [3:0] pad_address_out;']
    for pair in range(2):
        text += [f'''    (* PAP_DONT_TOUCH *) GTP_LUT6D /* native comment */ #(
            .INIT(64'b{0xCCCCCCCCAAAAAAAA:064b}))
        \\write_address_pad[{pair}].u_hold_dual_lut (
            .Z (pad_address_out[{pair*2+1}]), .Z5 (pad_address_out[{pair*2}]),
            .I0 (wr_ptr[{pair*2}]), .I1 (wr_ptr[{pair*2+1}]),
            .I2 (1'b0), .I3 (1'b0), .I4 (1'b0), .I5 (1'b1));''']
    for bit in range(4):
        text += [f'''    GTP_DFF_RE /* native FF */ #(.GRS_EN("TRUE"), .INIT(1'b0))
        \\wr_ptr[{bit}] (.Q (wr_ptr[{bit}]), .CE (push), .CLK (clk), .D (N27[{bit}]), .R (reset));''']
        text += [f'''    GTP_RAM32X2DP /* native RAM */ #(.INIT_0(32'b0), .INIT_1(32'b0))
        fifo_{bit} (.DO ({{N30[{bit*2+1}], N30[{bit*2}]}}),
            .DI ({{push_data[{bit*2+1}], push_data[{bit*2}]}}),
            .RADDR ({{1'b0, r3, r2, r1, r0}}),
            .WADDR ({{1'b0, pad_address_out[3], pad_address_out[2], pad_address_out[1], pad_address_out[0]}}),
            .WCLK (clk), .WE (push));''']
    return '\n'.join(text + ['endmodule']) + '\n'


def main():
    source = fixture()
    # Exact run8ad UART module bytes; only these two hierarchy stubs are synthetic.
    native_path = Path(__file__).resolve().parents[1] / 'sim/uart_tx_fifo_hold_pad_ads_native.v'
    assert sha(native_path) == 'fed1fea6cd4fff4c9d079a8d86e5b5a124c87fbb06cbe2901031e0cd4b727008'
    native = source.split('module uart_tx_fifo', 1)[0] + native_path.read_text(encoding='utf-8')
    checks = []
    def passed(name):
        checks.append(name); print('UART_ADS_CASE_PASS ' + name)
    for name, text in [('native_style', source), ('run8ad_native_uart_module', native), ('crlf', source.replace('\n', '\r\n')),
                       ('ram_renaming', source.replace('fifo_', 'renamed_ram_')),
                       ('consistent_address_permutation', source.replace(
                           'pad_address_out[3], pad_address_out[2]', 'pad_address_out[2], pad_address_out[3]'))]:
        result = audit(text)
        assert result['waddr_pins_checked'] == 16 and result['memory_cells'] == 4
        passed(name)
    # Each mutation must change bytes; otherwise a stale fixture cannot pass by
    # silently failing to exercise its intended negative case.
    def replace(old, new, count=1):
        assert old in source, old
        changed = source.replace(old, new, count)
        assert changed != source
        return changed
    failures = {
        'missing_pad': replace('write_address_pad[1].u_hold_dual_lut', 'unused_cell'),
        'wrong_primitive': replace('GTP_LUT6D', 'GTP_LUT6'),
        'duplicate_pair': replace('write_address_pad[1]', 'write_address_pad[0]'),
        'missing_preserve': replace('(* PAP_DONT_TOUCH *) ', ''),
        'wrong_init': replace(f"64'b{0xCCCCCCCCAAAAAAAA:064b}", "64'h0"),
        'wrong_I5': replace(".I5 (1'b1)", ".I5 (1'b0)"),
        'wrong_I2': replace(".I2 (1'b0)", ".I2 (wr_ptr[2])"),
        'tied_input': replace('.I0 (wr_ptr[0])', ".I0 (1'b0)"),
        'swapped_input': replace('.I0 (wr_ptr[0])', '.I0 (wr_ptr[1])'),
        'tied_output': replace('.Z5 (pad_address_out[0])', ".Z5 (1'b0)"),
        'overlap_output': replace('.Z5 (pad_address_out[0])', '.Z5 (pad_address_out[1])'),
        'bypass_one_ram': replace('pad_address_out[0]})', 'wr_ptr[0]})'),
        'tied_one_waddr': replace('pad_address_out[0]})', "1'b0})"),
        'duplicate_one_waddr': replace('pad_address_out[0]})', 'pad_address_out[1]})'),
        'inconsistent_permutation': replace('pad_address_out[3], pad_address_out[2]',
                                            'pad_address_out[2], pad_address_out[3]'),
        'high_address_tied_one': replace(".WADDR ({1'b0,", ".WADDR ({1'b1,"),
        'missing_data_bits': replace('GTP_RAM32X2DP', 'GTP_LUT6'),
        'foreign_memory_mapping': replace('GTP_RAM32X2DP', 'GTP_DRM18K'),
        'wrong_data_coverage': replace('push_data[7]', 'push_data[5]'),
        'wrong_we': replace('.WE (push)', ".WE (1'b0)"),
        'wrong_ram_clock': replace('.WCLK (clk)', '.WCLK (cpu_clk)'),
        'wrong_ff_clock': replace('.CLK (clk)', '.CLK (cpu_clk)'),
        'no_ff': replace('.Q (wr_ptr[0])', '.Q (other)'),
        'wrong_ff_enable': replace('.CE (push)', ".CE (1'b1)"),
        'unknown_pointer_width': replace('wire [3:0] wr_ptr;', 'wire [4:0] wr_ptr;'),
        'foreign_hierarchy': replace('uart_tx_fifo u_tx', 'uart_tx_fifo u_unused'),
        'wrong_top_clock': replace('.clk (sys_clk)', '.clk (cpu_clk)'),
        'extra_driver': source.replace(
            '    wire [3:0] wr_ptr;', '    wire [3:0] wr_ptr;\n    GTP_LUT1 other (.Z (pad_address_out[0]), .I0 (push));'),
        'alias_bypass': source.replace('    wire [3:0] wr_ptr;',
                                      '    wire [3:0] wr_ptr;\n    assign pad_address_out = wr_ptr;'),
        'input_alias': source.replace('pad_address_out[0]', 'push_data[0]'),
        'duplicate_pin': replace('.I0 (wr_ptr[0])', '.I0 (wr_ptr[0]), .I0 (wr_ptr[1])'),
    }
    for name, text in failures.items():
        try:
            audit(text)
        except (ValueError, AssertionError):
            passed(name + '_rejected')
        else:
            raise AssertionError('Accepted broken ADS fixture: ' + name)
    def native_replace(old, new, count=1):
        assert old in native, old
        changed = native.replace(old, new, count)
        assert changed != native
        return changed
    native_failures = {
        'wrong_pointer_width': native_replace('wire [3:0] pad_address_in;', 'wire [4:0] pad_address_in;'),
        'missing_pointer_declaration': native_replace('wire [3:0] pad_address_in;', ''),
        'duplicate_pointer_declaration': native_replace('wire [3:0] pad_address_in;',
                                                        'wire [3:0] pad_address_in; wire [3:0] pad_address_in;'),
        'unknown_pointer_bus': native_replace('pad_address_in', 'unreviewed_bus', -1),
        'missing_named_ff': native_replace('\\wr_ptr[0]  (', '\\other_reg[0]  ('),
        'wrong_ff_bit_name': native_replace('\\wr_ptr[0]  (', '\\wr_ptr[4]  ('),
        'swapped_q_bit': native_replace('.Q (pad_address_in[0])', '.Q (pad_address_in[1])'),
        'swapped_pad_input': native_replace('.I0 (pad_address_in[0])', '.I0 (pad_address_in[1])', -1),
        'extra_q_driver': native_replace('wire [3:0] pad_address_in;',
                                         'wire [3:0] pad_address_in;\n    GTP_LUT1 other (.Z (pad_address_in[0]), .I0 (push));'),
        'pointer_is_module_input': native_replace('input [7:0] push_data,',
                                                  'input [7:0] push_data, input [3:0] pad_address_in,'),
        'output_aliases_pointer': native_replace('fifo_write_address[0]', 'pad_address_in[0]', -1),
        'output_aliases_module_input': native_replace('fifo_write_address[0]', 'push_data[0]', -1),
        'ram_bypass': native_replace('fifo_write_address[0]})', 'pad_address_in[0]})'),
    }
    for name, text in native_failures.items():
        try:
            audit(text)
        except (ValueError, AssertionError):
            passed('run8ad_' + name + '_rejected')
        else:
            raise AssertionError('Accepted broken native ADS fixture: ' + name)
    with tempfile.TemporaryDirectory(prefix='uart-ads-contract-') as folder:
        base = Path(folder); netlist = base/'soc_top_syn.vm'; snap = base/'snapshot.json'
        netlist.write_text(source, encoding='utf-8')
        inputs = {'scripts/audit_uart_tx_pad_ads.py':sha(Path(__file__).with_name('audit_uart_tx_pad_ads.py')),
                  'scripts/audit_icache_pad_ads.py':sha(Path(__file__).with_name('audit_icache_pad_ads.py')),
                  'rtl/soc/uart_tx_fifo.v':'a'*64}
        snapshot = {'run_id':'b'*32, 'inputs':inputs}
        snap.write_text(json.dumps(snapshot), encoding='utf-8')
        bound = bind_result(audit(source), netlist, snap)
        assert bound['vm_sha256'] == sha(netlist) and bound['input_snapshot_sha256'] == sha(snap)
        passed('frozen_identity_bound')
        for key in ('scripts/audit_uart_tx_pad_ads.py', 'scripts/audit_icache_pad_ads.py'):
            changed = copy.deepcopy(snapshot); changed['inputs'][key] = '0'*64
            snap.write_text(json.dumps(changed), encoding='utf-8')
            try:
                bind_result(audit(source), netlist, snap)
            except ValueError:
                passed('wrong_' + Path(key).stem + '_rejected')
            else:
                raise AssertionError('Accepted foreign frozen recipe')
    print(f'UART_TX_PAD_ADS_TESTS_PASS checks={len(checks)} scope=SYNTHETIC_NO_PDS_NO_HARDWARE')


if __name__ == '__main__':
    main()
