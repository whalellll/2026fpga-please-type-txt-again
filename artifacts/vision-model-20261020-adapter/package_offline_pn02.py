"""Create and round-trip verify a local, uninstalled PN02 candidate ZIP."""
import argparse
import hashlib
import json
import zipfile
from pathlib import Path
from sd_namespace import CPU80_CONV, identity

R = Path(__file__).resolve().parents[2]


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--candidate', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--receipt', type=Path, required=True)
    p.add_argument('--sbit', type=Path)
    a = p.parse_args()
    root = a.candidate.resolve()
    assert root.is_relative_to(R/'build')
    assert not a.output.exists() and not a.receipt.exists()
    contract = json.loads((root/'sd_contract.json').read_text(encoding='utf-8-sig'))
    assert contract['fixed_sbit_sha256'] == CPU80_CONV
    assert contract['hardware_profile'] == 'cpu80-conv-34338722'
    assert not contract['board_validated'] and not contract['sd_written']
    expected = {'PN02SBI.BIN','PN02K.BIN','PN02FS.BIN','PN02.DTB','PN02NN.PFF','PN02ATK.BIN'}
    assert set(contract['files']) == expected
    files = {}
    identities = {}
    for name, item in contract['files'].items():
        source = root/name
        actual = identity(source)
        assert all(actual[k] == item[k] for k in ('bytes','sha256','crc32')), name
        files['sd-root/'+name] = source
    loader = root/'loader-picture-candidate.bin'
    descriptors = json.loads((R/'docs/validation/picture-merge-20261023/PN02-descriptors.json').read_text())
    assert descriptors['status'] == 'PASS' and not descriptors['board_validated']
    assert all(identity(loader)[k] == descriptors['loader'][k] for k in ('bytes','sha256','crc32'))
    for name, item in descriptors['descriptors'].items():
        assert all(contract['files'][name][k] == item[k] for k in ('bytes','crc32'))
    assert set(descriptors['descriptors']) == expected
    files['sd-root/PN02BOOT.BIN'] = loader
    files['sd_contract.json'] = root/'sd_contract.json'
    files['picture_payloads.h'] = root/'picture_payloads.h'
    if a.sbit:
        assert identity(a.sbit)['sha256'] == CPU80_CONV
        files['hardware/soc_top.sbit'] = a.sbit
    for name, source in files.items():
        identities[name] = {k:v for k,v in identity(source).items() if k != 'path'}
    manifest = dict(schema_version=1, scope='offline PN02 functional candidate; NOT BoardRelease',
                    board_validated=False, sd_written=False, flash_written=False,
                    production_ready=False, full_integer_pipeline=False,
                    fixed_sbit_sha256=CPU80_CONV, cpu_hz=80000000, sys_hz=49500000,
                    integer_acceptance='待新局归因; reported68/84 below73/84',
                    model_profile='working-r14', runtime='native integer functional-only; PC default remains FP32',
                    demo_latency_cap_s=10, engineering_targets_s=[5,3], files=identities)
    readme = '''# Picture_new CPU80 / r14 PN02 offline candidate

This archive was built and verified on a PC. It has never been installed or
booted. It is not a BoardRelease or an accuracy/latency acceptance receipt.
Requires CPU80-conv34338722 image SHA256:
30d8f0d5ccdefcf9225780965df3efd399b9b9f27eb390d849754fcd57d526f1
The old PN01/E8 boot set is incompatible and must retain its separate identity.

sd-root contains seven private PN02 names only. No public selector/config,
Flash writer or automatic installation script is included. Media installation
and JTAG are deferred until hardware is available, with fresh identity checks
and the applicable authorization. Preserve other branch names/menu entries.

Native r14 INT is for functional integration only, reported68/84 <73/84,
pending fresh-game attribution. The PC default is standard QAT FP32.
Conv dispatch defaults OFF; none of the current80 layers qualifies for ABI3.
No CPU fallback on hardware errors. Strict frame/CRC/board guards remain.
CPU80 has no E8 background-camera extension; visibility must be reaccepted.
Full voice assets and volume100 are preserved; board audio acceptance pending.

On hardware return: verify exact bitstream/CPU/SBI99/160 and six payload CRCs;
boot, validate80 layers and RGB565/frame identity, physical Space retry/cancel,
strict rejection and geometry/manual fallback, speech/MAC coexistence, games,
and total latency. Record demo<=10s plus engineering5s/3s separately.
See docs/CPU80_PICTURE_INTERFACE_NOTES_20261023.md in the source repository.
'''
    a.output.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(a.output, 'x', compression=zipfile.ZIP_DEFLATED, compresslevel=6) as z:
        for name, source in files.items():
            z.write(source, name)
        z.writestr('manifest.json', json.dumps(manifest, ensure_ascii=False, indent=2)+'\n')
        z.writestr('README.md', readme)
    with zipfile.ZipFile(a.output) as z:
        assert set(z.namelist()) == set(files)|{'manifest.json','README.md'}
        assert z.testzip() is None
        for name, item in identities.items():
            data = z.read(name)
            assert len(data) == item['bytes'] and hashlib.sha256(data).hexdigest() == item['sha256']
    assert all(identity(source)['sha256'] == identities[name]['sha256'] for name,source in files.items())
    result = dict(status='PASS', archive=identity(a.output), files=identities,
                  complete_zip_roundtrip=True, board_validated=False, media_written=False,
                  production_ready=False, bitstream_included=bool(a.sbit),
                  scope='local uninstalled candidate; not BoardRelease')
    a.receipt.parent.mkdir(parents=True, exist_ok=True)
    a.receipt.write_text(json.dumps(result, indent=2)+'\n', encoding='utf-8')
    print('PN02_OFFLINE_PACKAGE_ROUNDTRIP_PASS', a.output)


if __name__ == '__main__':
    main()
