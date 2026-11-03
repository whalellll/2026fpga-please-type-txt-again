"""Focused SD namespace, actual loader-binding and relocation checks."""
import argparse
import json
from pathlib import Path
import shutil
import struct
import tempfile
import unittest
import zlib
from sd_namespace import names, verify_compiled_loader, ROLES

p=argparse.ArgumentParser();p.add_argument('--candidate',type=Path,required=True);args=p.parse_args()
CANDIDATE=args.candidate.resolve()


def symbols(elf):
    table=struct.unpack_from('<I',elf,32)[0]
    size,count=struct.unpack_from('<HH',elf,46)
    sections=[struct.unpack_from('<10I',elf,table+i*size) for i in range(count)]
    result={}
    for section in sections:
        if section[1]!=2:continue
        string=sections[section[6]]
        strings=elf[string[4]:string[4]+string[5]]
        for at in range(section[4],section[4]+section[5],section[9]):
            name,value,*_=struct.unpack_from('<IIIBBH',elf,at)
            result[strings[name:strings.find(b'\0',name)].decode()]=value
    return sections,result


class NamespaceTest(unittest.TestCase):
    def setUp(self):
        self.contract=json.loads((CANDIDATE/'sd_contract.json').read_text())

    def test_namespace_and_real_compiled_binding(self):
        layout=names('PN01');other=names('PN02')
        self.assertTrue(set(layout.values()).isdisjoint(other.values()))
        self.assertEqual(len(verify_compiled_loader(CANDIDATE,self.contract)[1]),6)
        for invalid in ('../PN01','PN001','pn01','Image','P19','PN_1'):
            with self.assertRaises(ValueError):names(invalid)

    def test_mixed_loader_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            target=Path(folder)
            for name in ('loader-picture-candidate.bin','loader-picture-candidate.elf'):
                shutil.copyfile(CANDIDATE/name,target/name)
            binary=target/'loader-picture-candidate.bin';raw=binary.read_bytes()
            self.assertEqual(raw.count(b'PN01K.BIN\0'),1)
            binary.write_bytes(raw.replace(b'PN01K.BIN\0',b'PN02K.BIN\0'))
            with self.assertRaisesRegex(ValueError,'different payload'):verify_compiled_loader(target,self.contract)
            binary.write_bytes(raw)
            elf=bytearray((target/'loader-picture-candidate.elf').read_bytes());struct.pack_into('<I',elf,24,0x01400000)
            (target/'loader-picture-candidate.elf').write_bytes(elf)
            with self.assertRaisesRegex(ValueError,'RV32 ELF'):verify_compiled_loader(target,self.contract)

    def test_real_selector_relocation_rv32_instructions(self):
        elf=(CANDIDATE/'xq-boot-menu.elf').read_bytes();raw=(CANDIDATE/'xq-boot-menu.bin').read_bytes()
        sections,sym=symbols(elf)
        self.assertEqual(sym['__image_bytes'],len(raw));self.assertEqual(len(raw)%4,0)
        for section in sections:
            if section[2]&2 and section[1]!=8:
                self.assertGreaterEqual(section[3],0x01400000)
                self.assertLessEqual(section[3]+section[5],0x01400000+len(raw))
        # Execute the real linked trampoline and BSS initialization as RV32I.
        base=0x01000000;memory=bytearray(b'\xa5')*0x500000
        memory[:len(raw)]=raw;original=bytes(memory[:len(raw)])
        reg=[0]*32;pc=base
        def sext(value,bits):return value-(1<<bits) if value&(1<<(bits-1)) else value
        def offset(address):
            address&=0x7fffffff
            self.assertTrue(base<=address<base+len(memory));return address-base
        for steps in range(100000):
            if pc==sym['main']:break
            ins=struct.unpack_from('<I',memory,offset(pc))[0]
            op=ins&127;rd=(ins>>7)&31;rs1=(ins>>15)&31;rs2=(ins>>20)&31;fn=(ins>>12)&7
            nxt=(pc+4)&0xffffffff;imm=sext(ins>>20,12)
            if op==0x37:reg[rd]=ins&0xfffff000
            elif op==0x17:reg[rd]=pc+(ins&0xfffff000)
            elif op==0x13 and fn==0:reg[rd]=reg[rs1]+imm
            elif op==0x03 and fn==2:reg[rd]=struct.unpack_from('<I',memory,offset((reg[rs1]+imm)&0xffffffff))[0]
            elif op==0x23 and fn==2:
                displacement=sext(((ins>>25)<<5)|((ins>>7)&31),12)
                address=(reg[rs1]+displacement)&0xffffffff
                self.assertTrue(0x01400000<=address&0x7fffffff<sym['__bss_end'])
                struct.pack_into('<I',memory,offset(address),reg[rs2])
            elif op==0x63:
                displacement=sext(((ins>>31)<<12)|(((ins>>7)&1)<<11)|(((ins>>25)&63)<<5)|(((ins>>8)&15)<<1),13)
                taken=reg[rs1]==reg[rs2] if fn==0 else reg[rs1]>=reg[rs2] if fn==7 else None
                self.assertIsNotNone(taken)
                if taken:nxt=pc+displacement
            elif op==0x6f:
                displacement=sext(((ins>>31)<<20)|(((ins>>12)&255)<<12)|(((ins>>20)&1)<<11)|(((ins>>21)&1023)<<1),21)
                reg[rd]=nxt;nxt=pc+displacement
            elif op==0x67 and fn==0:
                target=(reg[rs1]+imm)&0xfffffffe;reg[rd]=nxt;nxt=target
            elif op==0x0f:pass
            else:self.fail(f'Unsupported startup instruction {ins:08x} at {pc:08x}')
            reg[rd]&=0xffffffff;reg[0]=0;pc=nxt&0xffffffff
        else:self.fail('Relocation did not reach main')
        self.assertEqual(bytes(memory[:len(raw)]),original)
        self.assertEqual(bytes(memory[offset(0x01400000):offset(0x01400000)+len(raw)]),raw)
        self.assertEqual(memory[offset(sym['__bss_start']):offset(sym['__bss_end'])],b'\0'*(sym['__bss_end']-sym['__bss_start']))
        self.assertEqual(reg[2],sym['__stack_top']);self.assertEqual(reg[3],sym['__global_pointer$'])


def synthetic_header():
    folder=CANDIDATE/'host-installer-fixture';folder.mkdir(exist_ok=True)
    plan=json.loads((CANDIDATE/'namespace-install-plan.json').read_text())
    old=Path(plan['original_entry']['path']).read_bytes()
    parts={'loader':(CANDIDATE/'loader-picture-candidate.bin').read_bytes(),
           'menu':(CANDIDATE/'xq-boot-menu.bin').read_bytes(),
           'config':(CANDIDATE/'XQBOOT.CFG').read_bytes(),'test_old':old}
    data=[bytes((i*29+j)%256 for j in range(2048+i*128)) for i in range(6)]
    parts.update({f'test_data_{i}':item for i,item in enumerate(data)})
    cid=plan['expected_cid'];text='#define NS_EXPECTED_CID {'+','.join('0x'+cid[i:i+8]+'u' for i in range(0,32,8))+'}\n'
    text+=f'#define NS_TEST_CID_TEXT "{cid}"\n#define NS_OLD_BYTES {len(old)}u\n#define NS_OLD_CRC 0x{zlib.crc32(old):08x}u\n'
    text+=f'#define NS_NEW_ENTRY_CRC 0x{zlib.crc32(parts["menu"]+old[len(parts["menu"]):]):08x}u\n'
    entries=[]
    for i,item in enumerate(plan['source_files_and_private_copies']):
        stem,ext=item['name'].split('.')
        entries.append(f'{{"{item["source"]}","{item["name"]}","{stem.ljust(8)+ext.ljust(3)}",{len(data[i])}u,0x{zlib.crc32(data[i]):08x}u,0x{item["address"]:08x}u}}')
    text+='#define NS_COPY_ITEMS {'+','.join(entries)+'}\n'
    for name,content in parts.items():
        text+=f'#define NS_{name.upper()}_BYTES {len(content)}u\n#define NS_{name.upper()}_CRC 0x{zlib.crc32(content):08x}u\n'
        text+=f'static const uint8_t ns_{name}[] __attribute__((aligned(4)))={{'+','.join(str(x) for x in content)+'};\n'
    text+='static const uint8_t *ns_test_data[]={'+','.join(f'ns_test_data_{i}' for i in range(6))+'};\n'
    (folder/'sd_namespace_install.h').write_text(text)
    print('SYNTHETIC_INSTALLER_FIXTURE_READY')


if __name__=='__main__':
    synthetic_header()
    unittest.main(argv=['test_sd_namespace'],verbosity=2)
