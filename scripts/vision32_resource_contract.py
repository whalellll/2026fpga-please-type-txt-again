"""Fail-closed native check for the replacement P4/OC8 vision profile."""
import re


def vision32_resource_contract(netlist, report):
    modules = re.findall(r'(?m)^module\s+(\w+)\b', netlist)
    for name in ('vision32_layer', 'vision32_pe'):
        assert modules.count(name) == 1, ('Vision module missing/duplicated', name)
    for name in ('mac_conv_mmio_frontend', 'mac_conv_compute_core', 'mac_weight_double_buffer', 'mac_conv_weight_dma'):
        assert name not in modules, ('Legacy conv unexpectedly retained', name)
    pe = re.findall(r'(?ms)^module vision32_pe\b.*?^endmodule', netlist)
    assert len(pe) == 1
    pe_apm = len(re.findall(r'\bGTP_APM_E2\s', pe[0]))
    assert pe_apm == 32, ('Expected exactly32 physical PE APMs', pe_apm)
    rows = []
    for line in report.splitlines():
        f = line.split('|')
        if len(f) < 8 or not re.fullmatch(r'\s*\d+\s*', f[2]):
            continue
        if f[1].strip().removeprefix('+').strip() == 'g_vision32.u_vision32':
            rows.append(dict(lut=float(f[2]), ff=float(f[3]), lutram=float(f[4]), apm=float(f[5]), drm=float(f[6])))
    assert len(rows) == 1, 'Vision SNR subtree missing/duplicated'
    row = rows[0]
    assert row['lut'] > 0 and row['ff'] > 0
    assert 32 <= row['apm'] <= 64, ('Vision total APM out of resource screen', row)
    assert 0 <= row['drm'] <= 8, ('Vision exceeds retained8DRM screen', row)
    cache = None
    if row['drm'] == 0:
        from vision32_cache_contract import cache_contract
        cache = cache_contract(netlist)
        assert row['lutram'] >= cache['weight_ram64x1_cells']+160, 'Complete LUTRAM caches absent from SNR'
    total = re.search(r'Total DRM =\s*([\d.]+)', report)
    assert total and float(total[1]) <= 140, 'Whole-chip140DRM limit exceeded'
    return dict(**row, pe_apm=pe_apm, cache_mapping_proof=cache)
