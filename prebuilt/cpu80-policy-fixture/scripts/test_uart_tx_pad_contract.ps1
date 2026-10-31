param([string]$ReportPath='')
$ErrorActionPreference='Stop'
. (Join-Path $PSScriptRoot 'build_snapshot.ps1')
. (Join-Path $PSScriptRoot 'test_uart_tx_pad_fixture.ps1')
$snapshot=[pscustomobject]@{release='V6.5';run_id='1'*32;inputs=[pscustomobject]@{
    'scripts/audit_uart_tx_pad_ads.py'='2'*64; 'scripts/audit_icache_pad_ads.py'='3'*64
    'rtl/soc/uart_tx_fifo.v'='4'*64}}
$cpu=[pscustomobject]@{input_snapshot_sha256='5'*64;netlist_sha256='6'*64
    uart_tx_pad_contract=(New-TestUartTxPadEvidence $snapshot ('5'*64) ('6'*64))}
$checks=[Collections.Generic.List[string]]::new()
Assert-FpgaUartTxPadContract $cpu $snapshot
$checks.Add('new_frozen_contract_accepted')
$native=$cpu | ConvertTo-Json -Depth 12 | ConvertFrom-Json
for ($pair=0; $pair -lt 2; $pair++) {
    $native.uart_tx_pad_contract.pairs[$pair].inputs=@(('pad_address_in['+(2*$pair)+']'),('pad_address_in['+(2*$pair+1)+']'))
}
Assert-FpgaUartTxPadContract $native $snapshot
$checks.Add('native_merged_pointer_contract_accepted')
foreach ($mutation in @(
    @{name='missing_contract'; action={param($c) $c.uart_tx_pad_contract=$null}},
    @{name='foreign_run'; action={param($c) $c.uart_tx_pad_contract.run_id='a'*32}},
    @{name='wrong_snapshot'; action={param($c) $c.uart_tx_pad_contract.input_snapshot_sha256='a'*64}},
    @{name='wrong_vm'; action={param($c) $c.uart_tx_pad_contract.vm_sha256='a'*64}},
    @{name='wrong_checker'; action={param($c) $c.uart_tx_pad_contract.checker_sha256='a'*64}},
    @{name='wrong_parser'; action={param($c) $c.uart_tx_pad_contract.parser_sha256='a'*64}},
    @{name='wrong_rtl'; action={param($c) $c.uart_tx_pad_contract.uart_rtl_sha256='a'*64}},
    @{name='missing_pair'; action={param($c) $c.uart_tx_pad_contract.pairs=@($c.uart_tx_pad_contract.pairs[0])}},
    @{name='tied_pair_input'; action={param($c) $c.uart_tx_pad_contract.pairs[0].inputs[0]="1'b0"}},
    @{name='mixed_pointer_buses'; action={param($c) $c.uart_tx_pad_contract.pairs[1].inputs=@('pad_address_in[2]','pad_address_in[3]')}},
    @{name='unknown_pointer_bus'; action={param($c) $c.uart_tx_pad_contract.pairs[0].inputs=@('foreign[0]','foreign[1]')}},
    @{name='pointer_output_alias'; action={param($c) $c.uart_tx_pad_contract.pairs[0].outputs[0]='pad_address_in[0]'}},
    @{name='wrong_init'; action={param($c) $c.uart_tx_pad_contract.init='00000000_00000000'}},
    @{name='missing_driver_check'; action={param($c) $c.uart_tx_pad_contract.unique_drivers=$false}},
    @{name='bypass'; action={param($c) $c.uart_tx_pad_contract.bypass=$true}},
    @{name='missing_ram'; action={param($c) $c.uart_tx_pad_contract.memories=@($c.uart_tx_pad_contract.memories[0])}},
    @{name='bypassed_one_ram'; action={param($c) $c.uart_tx_pad_contract.memories[0].waddr="{1'b0,wr_ptr[3],pad[2],pad[1],pad[0]}"}},
    @{name='wrong_pin_permutation'; action={param($c) $c.uart_tx_pad_contract.memories[0].waddr_low_to_high_pointer_bits=@(0,0,2,3)}},
    @{name='wrong_data_coverage'; action={param($c) $c.uart_tx_pad_contract.memories[0].data_bits=@(0,0)}},
    @{name='overstated_physical_retention'; action={param($c) $c.uart_tx_pad_contract.post_pnr_physical_retention_proven=$true}},
    @{name='overstated_hold'; action={param($c) $c.uart_tx_pad_contract.routed_hold_margin_proven=$true}}
)) {
    $copy=$cpu | ConvertTo-Json -Depth 12 | ConvertFrom-Json
    & $mutation.action $copy
    $rejected=$false
    try { Assert-FpgaUartTxPadContract $copy $snapshot } catch {
        if ($_.Exception.Message -notlike 'UART TX pad ADS *') { throw }
        $rejected=$true
    }
    if (!$rejected) { throw "Accepted invalid UART contract: $($mutation.name)" }
    $checks.Add($mutation.name+'_rejected')
}
$old=$snapshot | ConvertTo-Json -Depth 5 | ConvertFrom-Json
$old.inputs.PSObject.Properties.Remove('scripts/audit_uart_tx_pad_ads.py')
Assert-FpgaUartTxPadContract ([pscustomobject]@{}) $old
$checks.Add('historical_v65_snapshot_keeps_original_scope')
$result=[ordered]@{status='PASS';scope='SYNTHETIC_NO_PDS_NO_HARDWARE';count=$checks.Count;checks=@($checks.ToArray())}
if ($ReportPath) { $result | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath $ReportPath -Encoding UTF8 }
Write-Output "UART_TX_PAD_CONTRACT_TESTS_PASS checks=$($checks.Count)"
