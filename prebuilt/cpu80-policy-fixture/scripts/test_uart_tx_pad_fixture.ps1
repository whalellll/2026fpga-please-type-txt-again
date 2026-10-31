# Synthetic mapping shape only; never hardware acceptance evidence.
function New-TestUartTxPadEvidence($Snapshot, [string]$SnapshotHash, [string]$VmHash) {
    $inputs = ConvertTo-FpgaMap $Snapshot.inputs
    return [ordered]@{
        schema=1; status='PASS'; scope='MAPPED_UART_TX_WADDR_PADS'; hierarchy='soc_top/u_local/u_tx'
        run_id=$Snapshot.run_id; input_snapshot_sha256=$SnapshotHash; vm_sha256=$VmHash
        checker_sha256=$inputs['scripts/audit_uart_tx_pad_ads.py']
        parser_sha256=$inputs['scripts/audit_icache_pad_ads.py']; uart_rtl_sha256=$inputs['rtl/soc/uart_tx_fifo.v']
        primitive='GTP_LUT6D'; init='CCCCCCCC_AAAAAAAA'; preservation_attribute='PAP_DONT_TOUCH'
        address_bits=4; upstream_ff_bits=4; memory_cells=4; data_bits=8; waddr_pins_checked=16
        module_sha256='a'*64; unique_drivers=$true; bypass=$false
        post_pnr_physical_retention_proven=$false; routed_hold_margin_proven=$false
        pairs=@(0..1 | ForEach-Object {
            @{pair=$_; instance="\write_address_pad[$_].u_hold_dual_lut"
              inputs=@(('wr_ptr['+(2*$_)+']'),('wr_ptr['+(2*$_+1)+']'))
              outputs=@(('pad['+(2*$_)+']'),('pad['+(2*$_+1)+']'))}
        })
        memories=@(0..3 | ForEach-Object {
            @{instance="fifo_$_"; primitive='GTP_RAM32X2DP'; waddr="{1'b0,pad[3],pad[2],pad[1],pad[0]}"
              data_bits=@((2*$_+1),(2*$_)); waddr_low_to_high_pointer_bits=@(0,1,2,3)}
        })
    }
}
