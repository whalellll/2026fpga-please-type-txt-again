#!/usr/bin/env python3
"""Synthetic mapped-cone fixtures; these are never FPGA evidence."""
import unittest

from audit_rob_owner_ads import Hierarchy, RF_PATH, audit, expand


def fixture():
    ports=['input clock','input reset','input io_flush','input io_clear_0']
    cells=[]
    for port in (0,1,2,4):
        ports += ['input io_write_%d'%port,'input [4:0] io_writeTag_%d'%port]
    for lane in (2,4):
        ports += ['input [4:0] io_tagRead_%d'%lane,'output [31:0] io_tagData_%d'%lane]
    for tag in range(32):
        for stem in ('tagLive_','resultValid_'):
            cells.append("GTP_DFF_R %s%d_ff (.Q(%s%d),.D(1'b0),.R(reset),.CLK(clock));"%(stem,tag,stem,tag))
        for bit in range(1,4):
            cells.append("GTP_DFF_R \\resultOwner_%d_reg[%d] (.Q(resultOwner_%d_reg[%d]),.D(io_write_0),.R(reset),.CLK(clock));"%(tag,bit,tag,bit))
    for bank,port in enumerate((0,1,2,4)):
        level=['tagLive_%d'%tag for tag in range(32)]
        for bit in range(5):
            next_level=[]
            for index in range(len(level)//2):
                name='bank%d_mux_%d_%d'%(bank,bit,index)
                cells.append('GTP_MUX2 mux_%s (.Z(%s),.I0(%s),.I1(%s),.S(io_writeTag_%d[%d]));'%(name,name,level[2*index],level[2*index+1],port,bit))
                next_level.append(name)
            level=next_level
        cells.append("GTP_LUT4 #(.INIT(16'h0008)) enable%d (.Z(we%d),.I0(io_write_%d),.I1(%s),.I2(io_flush),.I3(reset));"%(bank,bank,port,level[0]))
        reads=','.join('.R%d_data(_resultBanks_%d_ext_R%d_data)'%(read,bank,read) for read in range(7))
        cells.append('resultBanks_32x32 resultBanks_%d_ext (.W0_en(we%d),%s);'%(bank,bank,reads))
    for lane,read in ((2,4),(4,2)):
        selectors={}
        for selector in ('valid','owner1','owner2','owner3'):
            level=['resultValid_%d'%tag if selector=='valid' else
                   'resultOwner_%d_reg[%s]'%(tag,selector[-1]) for tag in range(32)]
            for bit in range(5):
                next_level=[]
                for index in range(len(level)//2):
                    name='read%d_%s_%d_%d'%(lane,selector,bit,index)
                    cells.append('GTP_MUX2 mux_%s (.Z(%s),.I0(%s),.I1(%s),.S(io_tagRead_%d[%d]));'%(name,name,level[2*index],level[2*index+1],lane,bit))
                    next_level.append(name)
                level=next_level
            selectors[selector]=level[0]
        for bit in range(32):
            value='_resultBanks_0_ext_R%d_data[%d]'%(read,bit)
            for bank in (1,2,3):
                output='read%d_bit%d_bank%d'%(lane,bit,bank)
                cells.append('GTP_MUX2 mux_%s (.Z(%s),.I0(%s),.I1(_resultBanks_%d_ext_R%d_data[%d]),.S(%s));'%(output,output,value,bank,read,bit,selectors['owner'+str(bank)]))
                value=output
            cells.append("GTP_LUT2 #(.INIT(4'b1000)) mask%d_%d (.Z(io_tagData_%d[%d]),.I0(%s),.I1(%s));"%(lane,bit,lane,bit,value,selectors['valid']))
    text='module RobTagRegisterFile (\n'+',\n'.join(ports)+'\n);\n'+'\n'.join(cells)+'\nendmodule\n'
    text+='module resultBanks_32x32 (\ninput W0_en,\n'+',\n'.join('output [31:0] R%d_data'%r for r in range(7))+'\n);\nendmodule\n'
    types=['soc_top','CpuTop','CpuWrapper','CoreTop','Core','CoreBackend','Rob','RobTagRegisterFile']
    for parent,child,instance in zip(types,types[1:],RF_PATH):
        text+='module %s (\ninput unused\n);\n%s %s ();\nendmodule\n'%(parent,child,instance)
    return text


class RobAuditTest(unittest.TestCase):
    def test_expected_active_banks(self):
        result=audit(fixture())
        self.assertEqual(result['status'],'PASS')
        self.assertEqual(sum(x['checked_vectors'] for x in result['banks']),6144)
        self.assertEqual(result['owner_ff'],96)

    def test_constant_write_enable_rejected(self):
        with self.assertRaisesRegex(ValueError,'WE truth table differs'):
            audit(fixture().replace("16'h0008","16'h0000",1))

    def test_wrong_tag_selector_rejected(self):
        with self.assertRaisesRegex(ValueError,'WE truth table differs|Wrong tagLive'):
            audit(fixture().replace('.S(io_writeTag_0[0])','.S(io_writeTag_0[1])',1))

    def test_clear_into_bank_enable_rejected(self):
        with self.assertRaisesRegex(ValueError,'Decode/allocation still reaches'):
            audit(fixture().replace('.I2(io_flush)','.I2(io_clear_0)',1))

    def test_missing_valid_bit_rejected(self):
        with self.assertRaisesRegex(ValueError,'Missing mapped ROB FF resultValid_31'):
            audit(fixture().replace('.Q(resultValid_31)','.Q(wrongValid31)'))

    def test_missing_read_port_rejected(self):
        with self.assertRaisesRegex(ValueError,'Missing or changed result-bank read binding'):
            audit(fixture().replace('.R6_data(_resultBanks_0_ext_R6_data)', '.R6_data(wrong_read_port)',1))

    def test_constant_read_mask_rejected(self):
        with self.assertRaisesRegex(ValueError,'Constant mapped control'):
            audit(fixture().replace("4'b1000","4'b0000",1))

    def test_read_valid_bypass_rejected(self):
        with self.assertRaisesRegex(ValueError,'Valid masking was removed'):
            audit(fixture().replace('.I1(read2_valid_4_0)',".I1(1'b1)",1))

    def test_clear_into_owner_rejected(self):
        with self.assertRaisesRegex(ValueError,'Decode/allocation still reaches owner|Clear/allocation reaches promoted owner control'):
            audit(fixture().replace('.D(io_write_0)','.D(io_clear_0)',1))

    def test_unknown_cell_fails_closed(self):
        with self.assertRaisesRegex(ValueError,'Unknown or unbound sequential driver|Unsupported structural primitive'):
            audit(fixture().replace('GTP_LUT4 #','GTP_UNREVIEWED #',1))

    def test_multiple_drivers_rejected(self):
        with self.assertRaisesRegex(ValueError,'Multiple mapped drivers'):
            audit(fixture().replace('.Z(we1)','.Z(we0)',1))

    def test_hierarchy_binding_and_order(self):
        source="""module soc_top (
input [3:0] bus
);
child c (.x({bus[0],bus[1],bus[2],bus[3]}),.y(out));
endmodule
module child (
input [3:0] x,
output y
);
GTP_LUT1 #(.INIT(2'b10)) b (.Z(y),.I0(x[2]));
endmodule
"""
        graph=Hierarchy(source)
        self.assertEqual(graph.evaluate((),'out',{((),'bus[1]'):1}),1)
        self.assertEqual(expand('{2\'b10,bus[3:2]}',4),['bus[2]','bus[3]',"1'b0","1'b1"])

    def test_structural_walk_crosses_hierarchy_and_stops_at_ff(self):
        source="""module soc_top (
input allocation
);
GTP_DFF ff (.Q(wb),.D(allocation),.CLK(allocation));
child c (.write(wb),.clear(allocation),.y(out));
endmodule
module child (
input write,
input clear,
output y
);
GTP_LUT2 #(.INIT(4'b1010)) b (.Z(y),.I0(write),.I1(clear));
endmodule
"""
        graph=Hierarchy(source)
        seen,leaves=graph.dependencies((),'out')
        self.assertEqual(leaves,{((),'wb')})
        self.assertNotIn((('c',),'clear'),seen)
        self.assertEqual(graph.assert_nonconstant((),'out')['primitive'],'GTP_LUT2')
        with self.assertRaisesRegex(ValueError,'Constant mapped control'):
            Hierarchy(source.replace("4'b1010","4'b0000")).assert_nonconstant((),'out')


if __name__=='__main__': unittest.main()
