"""Synthetic mapping and mutation tests, no PDS or board actions."""
from audit_mac_weight_pad_ads import audit


def fixture(paired=False):
    s = ['module Bank1R1W_1_compact;']
    def pad(name, a, b, x, y):
        return ("(* PAP_DONT_TOUCH *) GTP_LUT6D #(.INIT(64'hCCCCCCCCAAAAAAAA)) " + name +
                ' (.I0(' + a + '),.I1(' + b + "),.I2(1'b0),.I3(1'b0),.I4(1'b0),.I5(1'b1)," +
                '.Z5(' + x + '),.Z(' + y + '));')
    for i in range(16):
        s.append(pad('\\g_word_input_hold.g_pair[' + str(i) + '].u_word_input_hold_lut ',
                     f'io_wordData[{i*2}]', f'io_wordData[{i*2+1}]', f'pad[{i*2}]', f'pad[{i*2+1}]'))
    for i in (66, 928):
        s.append(pad('u_weight_hold_lut_' + str(i), f'pad[{i%32}]', f'pad[{(i+1)%32}]',
                     f'legacy[{i}]', f'legacy[{i+1}]'))
    if paired:
        s.append("GTP_LUT2 #(.INIT(4'h1)) even_enable (.I0(io_wordIndex[0]),.I1(inhibit),.Z(even_on));")
        for word in range(1, 32, 2):
            pins = ','.join(f'.I{i}(io_wordIndex[{i}])' for i in range(5))
            s.append(f"GTP_LUT6 #(.INIT(64'h{1 << word:016X})) odd_{word} " +
                     f'({pins},.I5(inhibit),.Z(\\g_words.g_word[{word}].selected ));')
        for word in range(0, 32, 4):
            init = (1 << (16 + word//2)) | (1 << (32 + 16 + (word+2)//2))
            pins = ','.join(f'.I{i}(io_wordIndex[{i+1}])' for i in range(4))
            s.append(f"GTP_LUT6D #(.INIT(64'h{init:016X})) even_{word} " +
                     f'({pins},.I4(even_on),.I5(1\'b1),.Z5(\\g_words.g_word[{word}].selected ),' +
                     f'.Z(\\g_words.g_word[{word+2}].selected ));')
    for slot in range(1024):
        data = f'legacy[{slot}]' if slot in (66, 67, 928, 929) else f'pad[{slot%32}]'
        addr = lambda bus: '{' + ','.join(f'{bus}[{i}]' for i in range(5, -1, -1)) + '}'
        we = f',.WE(\\g_words.g_word[{slot//32}].selected )' if paired else ''
        s.append(f'GTP_RAM64X1DP \\g_words.g_word[{slot//32}].memory_{slot%32} ' +
                 f'(.DI({data}),.DO(q[{slot}]),.WCLK(io_clk),.RADDR({addr("io_raddr")}),.WADDR({addr("io_waddr")}){we});')
    return '\n'.join(s) + '\nendmodule'


s = fixture()
assert audit(s)['di_pins_checked'] == 1024
for old, new in (
    ('PAP_DONT_TOUCH', 'UNKNOWN'),
    ('CCCCCCCCAAAAAAAA', 'CCCCCCCCAAAAAAAB'),
    ('.I0(io_wordData[0])', ".I0(1'b0)"),
    (".I5(1'b1)", ".I5(1'b0)"),
    ('.DI(pad[0])', '.DI(io_wordData[0])'),
    ('.DI(pad[0])', '.DI(pad[1])'),
    ('.I0(pad[2])', '.I0(io_wordData[2])'),
    ('GTP_RAM64X1DP', 'GTP_RAM32X1DP'),
    ('.Z5(pad[0])', '.Z5(io_wordData[0])'),
    ('.WCLK(io_clk)', '.WCLK(other_clk)'),
):
    bad = s.replace(old, new, 1)
    assert bad != s
    try:
        audit(bad)
    except (ValueError, AssertionError):
        continue
    raise AssertionError('Accepted mutation: ' + old)
try:
    audit(s.replace('endmodule', 'assign bypass=pad[0];\nendmodule'))
except (ValueError, AssertionError):
    pass
else:
    raise AssertionError('Accepted alias')
print('WEIGHT_PAD_ADS_TESTS_PASS mutations=11 ram_di_pins=1024')

s = fixture(paired=True)
assert audit(s)['decoder_truth_cases'] == 2048
for old, new in (
    ("4'h1", "4'h2"),
    ("64'h0002000000010000", "64'h0002000000010001"),
    ('.I4(even_on)', '.I4(inhibit)'),
    ('.WE(\\g_words.g_word[0].selected )', '.WE(\\g_words.g_word[1].selected )'),
    ('.Z5(\\g_words.g_word[0].selected )', '.Z5(arbitrary_output)'),
    ('.I5(inhibit)', ".I5(1'b0)"),
    ('.I0(io_wordIndex[0]),.I1(inhibit)', '.I0(even_on),.I1(inhibit)'),
    ('.DI(pad[0])', '.DI(io_wordData[0])'),
    ('CCCCCCCCAAAAAAAA', 'CCCCCCCCAAAAAAAB'),
    ('endmodule', "GTP_LUT2 #(.INIT(4'h1)) duplicate (.I0(inhibit),.I1(inhibit),.Z(even_on));\nendmodule"),
):
    bad = s.replace(old, new, 1)
    assert bad != s, old
    try:
        audit(bad)
    except (ValueError, AssertionError):
        continue
    raise AssertionError('Accepted paired mutation: ' + old)
print('WEIGHT_PAD_PAIRED_DECODER_TESTS_PASS mutations=10 truth_cases=2048 ram_we_pins=1024')
