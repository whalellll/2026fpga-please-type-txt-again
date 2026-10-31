"""Check that reference placement cannot silently bind an unrelated cell."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from ddr_reference_placement import select_placements, parse_sites, parse_cells, verify_placements, in_scope

ROOT = "I_ips_ddr_top/u_ddrphy_top/"
REG = ROOT + "ddrphy_slice_top/i_dqs_group[2].ddrphy_data_slice/ddrphy_dqs_rddata_align/ck_dqs_diff[1]/opit_0_inv_L6QL5Q1"


class ReferencePlacementTest(unittest.TestCase):
    def test_closure_scope_includes_write_control_and_mask_luts(self):
        for cell in ('phy_wrdata_en_r[3]/opit_0_inv_L6QQ',
                     'phy_wrdata_mask_r[3]/opit_0_inv', 'N642_0/LUT6D_inst',
                     'N659[4]/LUT6_inst', 'adj_wrdata_mask_3[0]/LUT6_inst'):
            self.assertTrue(in_scope(ROOT + 'ddrphy_wdata_path_adj/' + cell, 'closure'))
        self.assertTrue(in_scope(REG.replace('ck_dqs_diff[1]', 'rddata_r1[63]'), 'closure'))
        self.assertFalse(in_scope(REG.replace('ck_dqs_diff[1]', 'read_pattern_error'), 'closure'))

    def test_explicit_override_preserves_other_placements(self):
        from ddr_reference_placement import apply_overrides
        original = {REG: ('CLMA_333_642', None), REG + '_other': ('CLMA_327_558', None)}
        updated = apply_overrides(original, {REG + '_perm': ('CLMA_333_648', 'FYA')})
        self.assertEqual(updated[REG], ('CLMA_333_648', 'FYA'))
        self.assertEqual(updated[REG + '_other'], original[REG + '_other'])
        self.assertEqual(original[REG], ('CLMA_333_642', None))

    def test_override_cannot_add_unmatched_cell(self):
        from ddr_reference_placement import apply_overrides
        with self.assertRaisesRegex(ValueError, 'unselected'):
            apply_overrides({REG: ('CLMA_333_642', None)}, {'unrelated/opit_0': ('CLMA_333_648', None)})
        with self.assertRaisesRegex(ValueError, 'ambiguous'):
            apply_overrides({REG: ('CLMA_333_642', None)},
                {REG: ('CLMA_333_648', None), REG + '_perm': ('CLMA_333_648', None)})

    def test_permutation_suffix_keeps_type_and_pre_route_name(self):
        old = {REG: ("CLMA_333_642", "FYA")}
        new = {REG + "_perm": ("CLMA_327_558", "FYA")}
        a = {REG + "_perm": "gopLUT6QL5Q"}
        result, missing = select_placements(old, new, a, a)
        self.assertEqual(result, {REG: old[REG]})
        self.assertEqual(missing, [])

    def test_changed_packing_is_not_reused(self):
        old = {REG: ("CLMA_333_642", "FYA")}
        result, missing = select_placements(old, old,
            {REG: "gopLUT6QL5Q"}, {REG: "gopLUT6Q"})
        self.assertEqual(result, {})
        self.assertEqual(missing, [REG])

    def test_ambiguous_alias_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "ambiguous"):
            select_placements({REG: ("CLMA_333_642", "FYA")},
                {REG: ("CLMA_327_558", "FYA"), REG + "_perm": ("CLMA_327_564", "FYA")}, {}, {})

    def test_missing_current_cell_is_not_reused(self):
        result, missing = select_placements({REG: ("CLMA_333_642", "FYA")}, {}, {}, {})
        self.assertEqual(result, {})
        self.assertEqual(missing, [REG])

    def test_no_timing_commands_allowed(self):
        with self.assertRaises(ValueError):
            parse_sites("set_false_path -from [get_clocks ddrphy_sysclk]")

    def test_export_flags_are_removed_and_duplicates_rejected(self):
        text = f"# reference\ndef_inst_site {{{REG}}} CLMA_333_642 FYA -no_check\n"
        self.assertEqual(parse_sites(text), {REG: ("CLMA_333_642", "FYA")})
        with self.assertRaises(ValueError):
            parse_sites(text + text)

    def test_only_terminal_permutation_suffix_is_an_alias(self):
        renamed = REG.replace("ck_dqs_diff[1]", "ck_dqs_diff[0]")
        result, missing = select_placements({REG: ("CLMA_333_642", "FYA")},
            {renamed: ("CLMA_327_558", "FYA")}, {REG: "gopQ"}, {renamed: "gopQ"})
        self.assertEqual(result, {})
        self.assertEqual(missing, [REG])

    def test_netlist_reads_cells_not_net_names(self):
        self.assertEqual(parse_cells(f"Port\nfoo;3\nInst\n{REG};gopLUT6QL5Q\nPin\nCLK;1\n"),
                         {REG: "gopLUT6QL5Q"})

    def test_actual_post_route_binding_is_required(self):
        requested = {REG: ("CLMA_333_642", "FYA")}
        self.assertEqual(verify_placements(requested,
                         {REG + "_perm": ("CLMA_333_642", "FYA")}), 1)
        for actual in ({}, {REG: ("CLMA_327_558", "FYA")},
                       {REG: ("CLMA_333_642", "FYB")}):
            with self.assertRaisesRegex(ValueError, "not honored"):
                verify_placements(requested, actual)

    def test_register_scope_keeps_data_and_critical_controls(self):
        self.assertTrue(in_scope(REG, "registers"))
        self.assertTrue(in_scope(REG.replace("ck_dqs_diff[1]", "rddata_r1[39]"), "registers"))
        self.assertFalse(in_scope(REG.replace("ck_dqs_diff[1]", "read_pattern_error"), "registers"))
        self.assertFalse(in_scope("unrelated/rddata_r1[39]", "registers"))

    def test_critical_scope_frees_other_data_registers(self):
        self.assertTrue(in_scope(REG, "critical"))
        self.assertTrue(in_scope(REG.replace("ck_dqs_diff[1]", "rddata_r1[39]"), "critical"))
        self.assertFalse(in_scope(REG.replace("ck_dqs_diff[1]", "rddata_r1[38]"), "critical"))

    def test_site_only_constraint_still_requires_the_exact_site(self):
        requested = {REG: ("CLMA_333_642", None)}
        self.assertEqual(verify_placements(requested, {REG: ("CLMA_333_642", "FYB")}), 1)
        with self.assertRaises(ValueError):
            verify_placements(requested, {REG: ("CLMA_327_558", "FYB")})
        self.assertEqual(parse_sites(f"def_inst_site {{{REG}}} CLMA_333_642\n"), requested)


if __name__ == "__main__":
    unittest.main()
