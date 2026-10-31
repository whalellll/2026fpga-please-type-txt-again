cfg_set_tcl_break -flag true
cfg_connect -ip 127.0.0.1 -port 65420
cfg_scan_chain
after 1000
cfg_read_device_property -mode 0 -device_index 0
cfg_assign_file -file G:/fpga/c75review_d8e3b863_boardverified20261019/artifacts/soc_top.sbit -device_index 0
cfg_program -device_index 0
cfg_read_device_property -mode 3 -device_index 0
cfg_disconnect
cfg_close
