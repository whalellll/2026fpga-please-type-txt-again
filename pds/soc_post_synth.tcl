# Device mapping and routing consume the exact ADS ADF audited by build_fpga.
# The source-stage project is generated from soc.tcl and stops at synthesize.
add_constraint "soc.fdc"
add_constraint "ddr3_test.rcf"

set_arch -family Logos2 -device PG2L100H -speedgrade -6 -package FBG676
dev_map -input_db_file "synthesize/soc_top_syn.adf"
# A separate map-only invocation creates PCF before native Tcl parse. Mapping
# repeats from the same audited SYN ADF; reapply after actual mapping as well.
set placement_out [open {device_map/soc_top.pcf} a]
set placement_extra [open {gui1080_tage.pcf} r]
puts $placement_out [read $placement_extra]
close $placement_extra
close $placement_out
puts GUI1080_STRICT_PLACEMENT_REAPPLIED_AFTER_MAP
set csr_out [open {device_map/soc_top.pcf} a]
set csr_extra [open {cpu75_csr_reference.pcf} r]
puts $csr_out [read $csr_extra]
close $csr_extra
close $csr_out
puts CPU75_CSR_STRICT_PLACEMENT_REAPPLIED_AFTER_MAP
# Prefer timing performance and target a positive post-route hold margin.
pnr -plc_decongestion 4 -gplace_seed 3 -optimize_multi_corner_timing -fix_hold_violation -mode performance -fix_hold_violation_threshold 200 -fix_hold_violation_iterations 12
report_timing -report_max_skew
report_power
gen_netlist
gen_bit_stream -force_to_run -create_bit_file TRUE -create_bin_file
