# Device mapping and routing consume the exact ADS ADF audited by build_fpga.
# The source-stage project is generated from soc.tcl and stops at synthesize.
add_constraint "soc.fdc"
add_constraint "ddr3_test.rcf"

set_arch -family Logos2 -device PG2L100H -speedgrade -6 -package FBG676
dev_map -input_db_file "synthesize/soc_top_syn.adf"
# Prefer timing performance and target a positive post-route hold margin.
pnr -plc_decongestion 4 -gplace_seed 3 -optimize_multi_corner_timing -fix_hold_violation -mode performance -fix_hold_violation_threshold 200 -fix_hold_violation_iterations 12
report_timing -report_max_skew
gen_bit_stream -force_to_run -create_bit_file TRUE -create_bin_file
