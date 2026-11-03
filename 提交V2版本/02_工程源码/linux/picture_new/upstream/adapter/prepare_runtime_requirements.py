from pathlib import Path
HERE=Path(__file__).resolve().parent
source=HERE.parent/'vision-model-20261020/requirements.txt'
lines=source.read_text(encoding='utf-8').splitlines()
target=HERE/'requirements-pc-reference.txt'
if target.exists():raise SystemExit('receiver requirement adaptation already exists')
assert 'sahi==0.12.8' in lines
target.write_text('# Receiver PC inference environment. Original requirements remain unchanged.\n'
                  '# SAHI is an optional export helper, unused by golden recognition.\n'
                  '# Its >=4.12 OpenCV requirement conflicts with the frozen NumPy1.26/OpenCV4.10 stack.\n'
                  +'\n'.join(line for line in lines if line!='sahi==0.12.8')
                  +'\nopencv-python==4.10.0.84\n',encoding='utf-8')
print('P20_PC_REQUIREMENTS_ADAPTED optional_sahi_excluded=1 exact_core_versions_preserved=1')
