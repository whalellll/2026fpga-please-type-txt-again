"""Behavior tests for the microarchitecture analysis and isolated source editor."""
import hashlib
import json
from pathlib import Path
import subprocess
import tempfile
import unittest

import microarch_timing_tool as tool


REPORT = '''Startpoint : core/unit/source/CLK
Endpoint : core/unit/result/D
Path Group : cpu_clk
Path Type : max (slow corner)
Clock Skew : -0.100
 Clock cpu_clk (rising edge) 0.000 0.000 r
 net (fanout=9000) 1.000 1.000 clock_tree
 CLMA/Q tco 0.200 1.200 r core/unit/source/Q
 net (fanout=12) 1.300 2.500 core/unit/select
 CLMA/Y td 0.100 2.600 r core/unit/mux/Z
 net (fanout=68) 2.000 4.600 core/unit/value
 Data arrival time 4.600 Logic Levels: 2
 Logic: 0.300ns(8.333%), Route: 3.300ns(91.667%)
 Slack (VIOLATED) -0.500
'''


class AnalysisTests(unittest.TestCase):
    def test_data_fanout_excludes_clock_tree(self):
        p = tool.parse_report(REPORT)[0]
        self.assertEqual(p['max_data_fanout'], 68)
        self.assertEqual(len(p['data_nets']), 2)
        self.assertAlmostEqual(p['route_ns'], 3.3)
        self.assertEqual(p['logic_levels'], 2)
        self.assertEqual(p['slack_ns'], -.5)

    def test_missing_or_partial_paths_fail(self):
        for report in ('garbage', REPORT.replace('Route: 3.300ns(91.667%)',''),
                       REPORT.replace('Slack (VIOLATED) -0.500','')):
            with self.subTest(report=report[-70:]):
                with self.assertRaises(ValueError): tool.parse_report(report)

    def test_bad_numbers_and_clock_are_not_guessed(self):
        for report in (REPORT.replace('Path Group : cpu_clk','Path Group :'),
                       REPORT.replace('-0.500', 'NaN')):
            with self.assertRaises(ValueError): tool.parse_report(report)

    def test_multiple_corners_remain_distinct(self):
        rows=tool.parse_report(REPORT+REPORT.replace('slow corner','fast corner'))
        self.assertEqual([r['corner'] for r in rows],['slow','fast'])

    def test_nonselected_unconstrained_io_is_excluded_not_certified(self):
        io='Startpoint : reset/CLK\nEndpoint : phy_rst (port)\nPath Group : **default**\n'
        self.assertEqual(len(tool.parse_report(REPORT+io,clock='cpu_clk')),1)
        with self.assertRaises(ValueError):tool.parse_report(REPORT+io)

    def test_hierarchy_uses_generated_rtl_not_name_guessing(self):
        hierarchy=tool.rtl_hierarchy('module Top(input c); Unit unit (.c(c)); endmodule\nmodule Unit(input c); reg source; endmodule')
        self.assertEqual(tool.resolve_resource('core/unit/source/Q',hierarchy,'Top'),('Unit','source'))
        self.assertIsNone(tool.resolve_resource('core/unmapped/source/Q',hierarchy,'Top'))

    def test_source_inventory_distinguishes_state_and_comb(self):
        declarations=tool.scala_declarations('val ready = RegInit(false.B)\nval pick = ready && valid\nval data = Mux(pick, a, b)\n')
        self.assertEqual(declarations['ready']['kind'],'register')
        self.assertIn('pick',declarations['data']['identifiers'])
        self.assertEqual(declarations['pick']['kind'],'combinational_hint')

    def test_wrapper_core_instance_is_consumed(self):
        h=tool.rtl_hierarchy('module Top(); Core core(); endmodule\nmodule Core(); Unit unit(); endmodule\nmodule Unit(); reg source; endmodule')
        self.assertEqual(tool.resolve_resource('u_cpu/core/unit/source/Q',h,'Top'),('Unit','source'))


class EditorTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name)/'cpu-source'
        self.root.mkdir()
        self.path=self.root/'cpu/src/main/scala/Unit.scala'
        self.path.parent.mkdir(parents=True)
        self.original=b'val hold = RegInit(false.B)\r\nval select = a && b\r\nval out = Mux(select, x, y)\r\n'
        self.path.write_bytes(self.original)
        self.snapshot={'cpu_root':str(self.root),'cpu_source_files':{
            'cpu/src/main/scala/Unit.scala':hashlib.sha256(self.original).hexdigest()}}
        self.spec={'strategy':'logic_rewrite','reason':'reduce select depth','edits':[{
            'path':'cpu/src/main/scala/Unit.scala','replacements':[{
                'before':'val select = a && b','after':'val select = b && a'}]}]}
        self.output=Path(self.temp.name)/'candidate'

    def test_edit_produces_real_diff_and_preserves_source_and_crlf(self):
        result=tool.stage_edits(self.snapshot,self.spec,self.output)
        self.assertEqual(self.path.read_bytes(),self.original)
        changed=(self.output/'source/cpu/src/main/scala/Unit.scala').read_bytes()
        self.assertIn(b'val select = b && a\r\n',changed)
        self.assertEqual(changed.count(b'\r\n'),3)
        self.assertIn('+val select = b && a',(self.output/'candidate.patch').read_text())
        self.assertFalse(result['functional_validated'])
        self.assertFalse(result['timing_validated'])

    def test_stale_source_refuses_without_output(self):
        self.path.write_bytes(self.original+b'// edited\n')
        with self.assertRaises(ValueError):tool.stage_edits(self.snapshot,self.spec,self.output)
        self.assertFalse(self.output.exists())

    def test_existing_output_refused(self):
        self.output.mkdir()
        with self.assertRaises(ValueError):tool.stage_edits(self.snapshot,self.spec,self.output)

    def test_all_changes_validated_before_candidate_is_created(self):
        self.spec['edits'].append({'path':'cpu/src/main/scala/Missing.scala','replacements':[]})
        with self.assertRaises(ValueError):tool.stage_edits(self.snapshot,self.spec,self.output)
        self.assertFalse(self.output.exists())

    def test_protected_register_removal_is_rejected(self):
        self.spec['edits'][0]['replacements']=[{'before':'val hold = RegInit(false.B)','after':'val hold = false.B'}]
        with self.assertRaisesRegex(ValueError,'register'):tool.stage_edits(self.snapshot,self.spec,self.output)

    def test_missing_or_ambiguous_context_is_rejected(self):
        for before in ('missing token','val '):
            self.spec['edits'][0]['replacements'][0]['before']=before
            with self.subTest(before=before):
                with self.assertRaises(ValueError):tool.stage_edits(self.snapshot,self.spec,self.output)
        self.assertFalse(self.output.exists())

    def test_escape_and_absolute_paths_are_rejected(self):
        for name in ('../Unit.scala','/etc/passwd','C:/outside.scala'):
            self.spec['edits'][0]['path']=name
            with self.subTest(name=name):
                with self.assertRaises(ValueError):tool.stage_edits(self.snapshot,self.spec,self.output)

    def test_pipeline_requires_control_and_latency_contract(self):
        self.spec['strategy']='pipeline_two_stage'
        with self.assertRaisesRegex(ValueError,'contract'):tool.stage_edits(self.snapshot,self.spec,self.output)
        self.spec['latency_contract']={'added_cycles':1,'controls':'valid/ready, flush and reset updated in patch','validation':'transaction scoreboard, stalls, flush, throughput and STA required'}
        self.assertEqual(tool.stage_edits(self.snapshot,self.spec,self.output)['status'],'EDIT_CANDIDATE_NOT_GENERATED_OR_VALIDATED')

    def test_empty_or_noop_spec_is_not_an_optimization(self):
        for spec in ({'strategy':'logic_rewrite','reason':'test','edits':[]},
                     {'strategy':'logic_rewrite','reason':'test','edits':[{'path':'cpu/src/main/scala/Unit.scala','replacements':[{'before':'a && b','after':'a && b'}]}]}):
            with self.assertRaises(ValueError):tool.stage_edits(self.snapshot,spec,self.output)

    def replication_fixture(self):
        raw=b'import chisel3._\nval hold = RegInit(false.B)\nval select = a && b\nval first = Mux(select, x, y)\nval second = Mux(select, z, w)\n'
        self.path.write_bytes(raw)
        self.snapshot['cpu_source_files']['cpu/src/main/scala/Unit.scala']=hashlib.sha256(raw).hexdigest()
        return {'path':'cpu/src/main/scala/Unit.scala','symbol':'select','reason':'partition selector consumers','groups':[
            {'name':'selectFirst','consumers':['val first = Mux(select, x, y)']},
            {'name':'selectSecond','consumers':['val second = Mux(select, z, w)']}]}

    def test_replication_creates_two_expressions_and_retargets_consumers(self):
        request=self.replication_fixture()
        spec=tool.replication_spec(self.snapshot,request)
        tool.stage_edits(self.snapshot,spec,self.output)
        changed=(self.output/'source/cpu/src/main/scala/Unit.scala').read_text()
        self.assertIn('val selectFirst = a && b\ndontTouch(selectFirst)',changed)
        self.assertIn('val second = Mux(selectSecond, z, w)',changed)
        self.assertIn('val hold = RegInit(false.B)',changed)

    def test_replication_rejects_state_and_nonunique_consumers(self):
        request=self.replication_fixture()
        request['symbol']='hold'
        with self.assertRaises(ValueError):tool.replication_spec(self.snapshot,request)
        request=self.replication_fixture()
        request['groups'][1]['consumers']=request['groups'][0]['consumers']
        with self.assertRaises(ValueError):tool.replication_spec(self.snapshot,request)

    def test_replication_rejects_helper_calls_with_unknown_side_effects(self):
        request=self.replication_fixture()
        raw=self.path.read_bytes().replace(b'a && b',b'unknownHelper(a, b)')
        self.path.write_bytes(raw)
        self.snapshot['cpu_source_files'][request['path']]=hashlib.sha256(raw).hexdigest()
        with self.assertRaisesRegex(ValueError,'Unknown Scala call'):tool.replication_spec(self.snapshot,request)


class BoundAnalysisTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name)
        self.cpu=self.root/'cpu-repo';self.cpu.mkdir()
        self.source=self.cpu/'cpu/src/main/scala/Unit.scala'
        self.source.parent.mkdir(parents=True)
        self.source.write_text('class Unit extends Module {\nval source = RegInit(false.B)\nval select = source && valid\nval value = Mux(select, a, b)\nval result = RegNext(value)\n}\n')
        def git(*args):
            return subprocess.run(['git','-C',str(self.cpu),*args],check=True,stdout=subprocess.PIPE,stderr=subprocess.PIPE).stdout
        git('init','-q');git('config','core.autocrlf','false');git('add','.');git('-c','user.name=Fixture','-c','user.email=fixture@example.invalid','commit','-qm','fixture')
        commit=git('rev-parse','HEAD').decode().strip()
        self.project=self.root/'soc';(self.project/'rtl/cpu').mkdir(parents=True)
        rtl='module Top(); Unit unit(); endmodule\nmodule Unit(); reg source; reg result; wire select; wire value; endmodule\n'
        (self.project/'rtl/cpu/CoreTop.sv').write_text(rtl)
        metadata={'sha256':tool.digest((self.project/'rtl/cpu/CoreTop.sv').read_bytes()),'source_reference_commit':commit,'module':'Top'}
        tool.save(self.project/'rtl/cpu/source.json',metadata)
        self.report=self.root/'paths.rtr';self.report.write_text(REPORT)
        self.binding=self.root/'binding.json'
        parsed=tool.parse_report(REPORT)[0]
        tool.save(self.binding,{'formal_run_id':'fixture','original_files_unchanged':True,'files_sha256':{'paths.rtr':tool.digest(self.report.read_bytes())},
                                'paths':[dict((k,parsed[k]) for k in ('startpoint','endpoint','corner','delay_type','clock_group','slack_ns','logic_levels'))]})
        self.snapshot=self.root/'snapshot.json'
        tool.save(self.snapshot,{'run_id':'fixture','inputs':{name:tool.digest((self.project/name).read_bytes()) for name in ('rtl/cpu/CoreTop.sv','rtl/cpu/source.json')}})
        self.output=self.root/'analysis'

    def analyze(self):
        return tool.analyze(self.project,self.cpu,self.report,self.binding,self.snapshot,self.output)

    def test_real_git_source_and_report_binding(self):
        result=self.analyze()
        self.assertEqual(result['path_count'],1)
        self.assertEqual(result['paths'][0]['unit_chain'],['Unit'])
        self.assertIn('select',[h['symbol'] for h in result['paths'][0]['source_hints']])
        self.assertEqual(len(result['cpu_source_files']),1)

    def test_changed_report_is_rejected_before_output(self):
        self.report.write_text(REPORT+'\nchanged\n')
        with self.assertRaisesRegex(ValueError,'report hash'):self.analyze()
        self.assertFalse(self.output.exists())

    def test_mixed_run_is_rejected(self):
        data=tool.load(self.binding);data['formal_run_id']='other';tool.save(self.binding,data)
        with self.assertRaisesRegex(ValueError,'run mismatch'):self.analyze()

    def test_changed_chisel_is_rejected(self):
        self.source.write_text(self.source.read_text()+'val extra = true.B\n')
        with self.assertRaisesRegex(ValueError,'frozen commit'):self.analyze()


if __name__=='__main__':unittest.main(verbosity=2)
