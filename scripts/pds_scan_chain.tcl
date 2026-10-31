cfg_set_tcl_break -flag true
cfg_connect -ip 127.0.0.1 -port %s
cfg_scan_chain
after 1000
cfg_read_device_property -mode 0 -device_index 0
cfg_read_device_property -mode 3 -device_index 0
cfg_disconnect
cfg_close
