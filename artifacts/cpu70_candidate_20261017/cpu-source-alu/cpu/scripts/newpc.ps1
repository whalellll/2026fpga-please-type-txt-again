param(
    [ValidateSet('VerifyPackage','Doctor','Emit','Unit','Functional','Ialign32','CoreMark','Synthesis','PdsPrepare','PdsCheck','PdsSynthesis')]
    [string]$Stage = 'Doctor',
    [string]$Config = (Join-Path $PSScriptRoot '../toolchain.local.json')
)
$ErrorActionPreference = 'Stop'
$root = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
$Config = [IO.Path]::GetFullPath($Config)
$savedPath = $env:PATH
$savedJavaHome = $env:JAVA_HOME
$savedCoursierRepositories = $env:COURSIER_REPOSITORIES
Push-Location -LiteralPath $root
try {
    if ($Stage -in @('PdsPrepare','PdsCheck','PdsSynthesis')) {
        $pdsArguments = @{}
        if (Test-Path -LiteralPath $Config) {
            $pdsConfig = Get-Content -LiteralPath $Config -Raw -Encoding UTF8 | ConvertFrom-Json
            if ($pdsConfig.PdsShell) { $pdsArguments.PdsShell = $pdsConfig.PdsShell }
            if ($pdsConfig.PdsStageRoot) { $pdsArguments.StageRoot = $pdsConfig.PdsStageRoot }
            if ($pdsConfig.PythonPath) { $pdsArguments.PythonPath = $pdsConfig.PythonPath }
        }
        if ($Stage -eq 'PdsCheck') { $pdsArguments.ValidateOnly = $true; $pdsArguments.VerifyWithPds = $true }
        if ($Stage -eq 'PdsSynthesis') { $pdsArguments.ValidateOnly = $true; $pdsArguments.Synthesize = $true }
        & "$PSScriptRoot/prepare_pds_project.ps1" @pdsArguments
        return
    }
    if ($Stage -eq 'VerifyPackage') {
        $manifestPath = Join-Path $root 'handoff/package-manifest.json'
        if (!(Test-Path -LiteralPath $manifestPath)) { throw 'Missing handoff/package-manifest.json; use the packaged project.' }
        $manifest = Get-Content -LiteralPath $manifestPath -Raw -Encoding UTF8 | ConvertFrom-Json
        if ($manifest.schema_version -eq 3) {
            $packageArgs = @{ Root = (Split-Path $root -Parent) }
            if (Test-Path -LiteralPath $Config) {
                $packageConfig = Get-Content -LiteralPath $Config -Raw -Encoding UTF8 | ConvertFrom-Json
                if ($packageConfig.PythonPath) { $packageArgs.PythonPath = $packageConfig.PythonPath }
                if ($packageConfig.NativeBash) {
                    $msys = Split-Path (Split-Path (Split-Path $packageConfig.NativeBash -Parent) -Parent) -Parent
                    $packageArgs.HostGccPath = Join-Path $msys 'mingw64/bin/gcc.exe'
                }
            }
            & (Join-Path $PSScriptRoot 'verify_cpu_package.ps1') @packageArgs
            return
        }
        if ($manifest.schema_version -ne 2 -or $manifest.root_scope -ne 'src_repository' -or !$manifest.files -or !$manifest.files.Count) {
            throw 'Expected a nonempty CPU repository-scope package manifest (schema 2).'
        }
        $listed = [Collections.Generic.HashSet[string]]::new([StringComparer]::OrdinalIgnoreCase)
        foreach ($entry in $manifest.files) {
            if (!$entry.path -or !$listed.Add([string]$entry.path)) { throw 'Empty or duplicate package entry.' }
        }
        foreach ($required in @('README.md', 'AGENTS.md', '.gitignore', '.gitattributes',
            'CHANGELOG.md', 'VERSION',
            'cpu/README.md', 'cpu/generated/manifest.json',
            'cpu/generated/core/CoreTop.sv', 'cpu/generated/sim/CoreTop.sv',
            'cpu/generated/core/emit-config.json', 'cpu/generated/sim/emit-config.json',
            'cpu/scripts/newpc.ps1', 'cpu/handoff/NEW_COMPUTER_GUIDE.md',
            'cpu/handoff/ARCHITECTURE_INTERFACE_CLOCKS.md',
            'cpu/handoff/validation/v3_1/source-pds/synthesis.json',
            'cpu/handoff/validation/v3_1/source-coremark/group.json',
            'cpu/handoff/validation/v3_1/source-coremark/summary.json',
            'cpu/coremark_test_soc/pds/coremark_test_soc.pds',
            'cpu/coremark_test_soc/sim/coremark_ima/manifest.json',
            'cpu/coremark_test_soc/sim/coremark_validation/manifest.json')) {
            if (!$listed.Contains($required)) { throw "Package inventory missing required input: $required" }
        }
        $verifyRoot = $root
        if ($manifest.schema_version -eq 2 -and $manifest.root_scope -eq 'src_repository') {
            $verifyRoot = Split-Path $root -Parent
        }
        $bad = @()
        foreach ($entry in $manifest.files) {
            $file = [IO.Path]::GetFullPath((Join-Path $verifyRoot $entry.path))
            if (!$file.StartsWith($verifyRoot + '\', [StringComparison]::OrdinalIgnoreCase)) { throw "Package manifest path escaped root: $($entry.path)" }
            if (!(Test-Path -LiteralPath $file -PathType Leaf)) { $bad += "Missing: $($entry.path)"; continue }
            if ((Get-FileHash -LiteralPath $file -Algorithm SHA256).Hash -ne $entry.sha256) { $bad += "Changed: $($entry.path)" }
        }
        if ($bad.Count) { throw ($bad -join "`n") }
        foreach ($firmware in @(
            @{ Directory = 'coremark_ima'; Mode = 'performance'; Seed1 = 0; Seed2 = 0 },
            @{ Directory = 'coremark_validation'; Mode = 'validation'; Seed1 = 0x3415; Seed2 = 0x3415 }
        )) {
            $firmwareRoot = Join-Path $root "coremark_test_soc/sim/$($firmware.Directory)"
            $firmwareManifest = Get-Content -LiteralPath (Join-Path $firmwareRoot 'manifest.json') -Raw -Encoding UTF8 | ConvertFrom-Json
            if ($firmwareManifest.evidence_class -cne 'formal_candidate' -or
                $firmwareManifest.run_mode -cne $firmware.Mode -or
                $firmwareManifest.iterations -ne 2600 -or $firmwareManifest.cpu_hz -ne 49500000 -or
                $firmwareManifest.total_data_size_bytes -ne 2000 -or
                $firmwareManifest.compiler_version -cne '16.2.0' -or
                $firmwareManifest.optimization -cne '-O2' -or
                $firmwareManifest.seeds.seed1 -ne $firmware.Seed1 -or
                $firmwareManifest.seeds.seed2 -ne $firmware.Seed2 -or
                $firmwareManifest.seeds.seed3 -ne 0x66 -or
                $firmwareManifest.seeds.seed4 -ne 2600 -or
                $firmwareManifest.seeds.seed5 -ne 0) {
                throw "Package firmware differs from the fixed V3.1 $($firmware.Mode) release input."
            }
        }
        & "$PSScriptRoot/verify_build_inputs.ps1" -GeneratedCpu -FirmwareDirectory (Join-Path $root 'coremark_test_soc/sim/coremark_ima')
        & "$PSScriptRoot/verify_build_inputs.ps1" -FirmwareDirectory (Join-Path $root 'coremark_test_soc/sim/coremark_validation')
        Write-Output "PACKAGE_VERIFY_PASS: $($manifest.files.Count) files"
        return
    }
    $cfg = Get-Content -LiteralPath $Config -Raw -Encoding UTF8 | ConvertFrom-Json
    if ($cfg.CoursierRepositories) { $env:COURSIER_REPOSITORIES = $cfg.CoursierRepositories }
    $sbtJvmArguments = @('-Xmx3g', '-Dsbt.color=false')
    if ($cfg.MavenRepositories) {
        $repositoryFile = $cfg.MavenRepositories
        if (![IO.Path]::IsPathRooted($repositoryFile)) {
            $repositoryFile = Join-Path (Split-Path $Config -Parent) $repositoryFile
        }
        $repositoryFile = [IO.Path]::GetFullPath($repositoryFile)
        if (!(Test-Path -LiteralPath $repositoryFile -PathType Leaf)) { throw "Missing MavenRepositories file: $repositoryFile" }
        $sbtJvmArguments += @('-Dsbt.override.build.repos=true', "-Dsbt.repository.config=$repositoryFile")
    }
    if ($cfg.SbtJvmArguments) { $sbtJvmArguments += @($cfg.SbtJvmArguments) }
    $sbtArguments = @()
    if ($cfg.SbtArguments) { $sbtArguments += @($cfg.SbtArguments) }
    function Invoke-Java([string[]]$Arguments, [string]$Failure) {
        $savedPreference = $ErrorActionPreference
        $javaExit = $null
        try {
            # Windows PowerShell 5.1 may turn ordinary native stderr into an
            # ErrorRecord when redirected. Java/sbt success is its exit code.
            $ErrorActionPreference = 'Continue'
            & $cfg.Java @Arguments
            $javaExit = $LASTEXITCODE
        } finally { $ErrorActionPreference = $savedPreference }
        if ($null -eq $javaExit -or $javaExit -ne 0) { throw "$Failure (Java exit code $javaExit)" }
    }
    if ($Stage -in @('Doctor','Emit','Unit')) {
        foreach ($field in @('Java','SbtLauncher')) {
            if (!(Test-Path -LiteralPath $cfg.$field -PathType Leaf)) { throw "Missing $field path in config: $($cfg.$field)" }
        }
        $env:JAVA_HOME = Split-Path (Split-Path $cfg.Java -Parent) -Parent
        $env:PATH = (Split-Path $cfg.Java -Parent) + ';' + $env:PATH
    }
    if ($cfg.NativePath) { $env:PATH = $cfg.NativePath + ';' + $env:PATH }
    $envArgs = @()
    if ($cfg.Verilator) { $envArgs += "VERILATOR=$($cfg.Verilator)" }
    if ($cfg.RiscvPrefix) { $envArgs += "RISCV_PREFIX=$($cfg.RiscvPrefix)" }
    function Invoke-TestShell([string]$Script, [string[]]$ScriptArguments = @()) {
        $savedPreference = $ErrorActionPreference
        $shellExit = $null
        try {
            if ($cfg.NativeBash) {
                if (!(Test-Path -LiteralPath $cfg.NativeBash -PathType Leaf)) { throw 'NativeBash must point to the installed MSYS2 bash.exe' }
                $savedVerilator = $env:VERILATOR
                $savedRiscvPrefix = $env:RISCV_PREFIX
                try {
                    if ($cfg.Verilator) { $env:VERILATOR = $cfg.Verilator }
                    if ($cfg.RiscvPrefix) { $env:RISCV_PREFIX = $cfg.RiscvPrefix }
                    $timeout = 5400
                    if ($Stage -eq 'CoreMark') {
                        $firmwareManifestPath = Join-Path $root 'coremark_test_soc/sim/coremark_ima/manifest.json'
                        $firmwareManifest = Get-Content -LiteralPath $firmwareManifestPath -Raw -Encoding UTF8 | ConvertFrom-Json
                        if ($firmwareManifest.evidence_class -eq 'formal_candidate') { $timeout = 14400 }
                    }
                    if ($null -ne $cfg.SimulationTimeoutSeconds) {
                        if (![int]::TryParse([string]$cfg.SimulationTimeoutSeconds, [ref]$timeout) -or
                            $timeout -lt 1 -or $timeout -gt 86400) {
                            throw 'SimulationTimeoutSeconds must be an integer between 1 and 86400.'
                        }
                    }
                    if (!('CpuSimulation.BoundedProcess' -as [type])) {
                        Add-Type -Path (Join-Path $PSScriptRoot 'bounded_process.cs')
                    }
                    # Quote each Windows argv value; do not assemble a shell command.
                    $nativeArguments = @('--noprofile', '--norc', $Script) + $ScriptArguments
                    $argumentLine = (@($nativeArguments | ForEach-Object {
                        $escaped = [regex]::Replace([string]$_, '(\\*)"', '$1$1\"')
                        '"' + [regex]::Replace($escaped, '(\\+)$', '$1$1') + '"'
                    })) -join ' '
                    $logDirectory = Join-Path $root 'work/logs/newpc-native'
                    New-Item -ItemType Directory -Path $logDirectory -Force | Out-Null
                    $runName = $Stage + '-' + [DateTime]::UtcNow.ToString('yyyyMMdd-HHmmss') + '-' + [guid]::NewGuid().ToString('N').Substring(0,6)
                    $stdoutLog = Join-Path $logDirectory ($runName + '.stdout.log')
                    $stderrLog = Join-Path $logDirectory ($runName + '.stderr.log')
                    Write-Output "NATIVE_SHELL_START limit=${timeout}s owner_powershell_pid=$PID stdout=$stdoutLog stderr=$stderrLog"
                    Write-Output 'Ending this PowerShell process closes the job and stops its descendants. Ctrl+C may wait while the native call blocks.'
                    try {
                        $shellExit = [CpuSimulation.BoundedProcess]::Run(
                            $cfg.NativeBash, $argumentLine, $root, $stdoutLog, $stderrLog, $timeout)
                    } catch {
                        throw "Native simulation stopped (job closed): $($_.Exception.GetBaseException().Message). Logs: $stdoutLog ; $stderrLog"
                    }
                    if ($shellExit -ne 0) { throw "Simulation shell failed ($shellExit): $Script. Logs: $stdoutLog ; $stderrLog" }
                    Select-String -LiteralPath $stdoutLog -Pattern '(^|[^A-Z])(?:[A-Z0-9_]+_PASS|COREMARK_DONE)\b' |
                        Select-Object -Last 12 | ForEach-Object { Write-Output $_.Line }
                    Write-Output "NATIVE_SHELL_PASS exit=$shellExit stdout=$stdoutLog stderr=$stderrLog"
                } finally {
                    $env:VERILATOR = $savedVerilator
                    $env:RISCV_PREFIX = $savedRiscvPrefix
                }
            } else {
                $ErrorActionPreference = 'Continue'
                & wsl.exe -d $cfg.WslDistribution --cd $root -- env @envArgs bash $Script @ScriptArguments
                $shellExit = $LASTEXITCODE
            }
        } finally { $ErrorActionPreference = $savedPreference }
        if ($null -eq $shellExit -or $shellExit -ne 0) {
            throw "Simulation shell failed ($shellExit): $Script"
        }
    }
    switch ($Stage) {
        Doctor {
            Write-Output 'Doctor: usually under 1 minute. Initializes fixed firmware; no installation or downloads. Native shell timeout and stop method are printed below.'
            & "$PSScriptRoot/prepare_handoff.ps1"
            Invoke-Java -Arguments @('-version') -Failure 'Java version check failed'
            Invoke-TestShell 'scripts/doctor_handoff.sh'
            if (Test-Path -LiteralPath $cfg.PdsShell -PathType Leaf) { Write-Output 'PDS executable exists; version/license still require Synthesis.' }
            else { Write-Warning 'PDS executable missing: simulation can continue; synthesis cannot.' }
            if ($cfg.PdsStageRoot -match '[^\x20-\x7E]') { throw 'PdsStageRoot must be an ASCII path' }
        }
        Emit {
            Write-Output 'Emit: warm cache about 30 seconds; first download may take 5-20 minutes. Ctrl+C stops it.'
            Invoke-TestShell 'scripts/verify_generated.sh' @('capture')
            Invoke-Java -Arguments ($sbtJvmArguments + @('-De91c.socProbes=false', '-jar', $cfg.SbtLauncher) + $sbtArguments + @('runMain e91c.core.EmitCore generated/core --synthesis')) -Failure 'Synthesis RTL emit failed'
            Invoke-Java -Arguments ($sbtJvmArguments + @('-De91c.socProbes=true', '-jar', $cfg.SbtLauncher) + $sbtArguments + @('runMain e91c.core.EmitCore work/handoff-probes')) -Failure 'Simulation RTL emit failed'
            Copy-Item -LiteralPath "$root/work/handoff-probes/CoreTop.sv" -Destination "$root/generated/sim/CoreTop.sv" -Force
            Copy-Item -LiteralPath "$root/work/handoff-probes/emit-config.json" -Destination "$root/generated/sim/emit-config.json" -Force
            Invoke-TestShell 'scripts/verify_generated.sh' @('record')
        }
        Unit {
            Write-Output 'Unit: several minutes with dependencies cached; exhaustive decoding and a new/busy machine can take longer. Ctrl+C stops it.'
            Invoke-Java -Arguments ($sbtJvmArguments + @('-jar', $cfg.SbtLauncher) + $sbtArguments + @('testOnly e91c.DecoderSpec e91c.MachineCsrSpec e91c.SupervisorCsrSpec e91c.IntegrationAddressMapSpec e91c.PhysicalMemoryAttributesSpec e91c.PmaMmuSpec e91c.PmaCacheBoundarySpec e91c.RsMemWritebackSpec e91c.LoadOrderSpec e91c.FrontendPipelineSpec')) -Failure 'Unit tests failed'
        }
        Synthesis {
            if (!(Test-Path -LiteralPath $cfg.PdsShell -PathType Leaf)) { throw 'Install/configure PDS before synthesis.' }
            Write-Output 'Synthesis: about 7-10 minutes on the original PC; new PC may differ. Ctrl+C stops it.'
            & "$PSScriptRoot/synthesize_dma_soc.ps1" -Config $Config -CpuPeriodNs 9.0909
        }
        default {
            if ($Stage -eq 'CoreMark') {
                Write-Output 'CoreMark: calibration takes under a minute; formal timed RTL can take several hours. The native shell timeout and stop method are printed below.'
            } else {
                Write-Output "$Stage`: tool speed and host load determine duration; model compilation can take several minutes each. Functional simulations have a 3M-cycle limit each. Native shell timeout and stop method are printed below. Uses fresh work/handoff-probes/CoreTop.sv."
            }
            Invoke-TestShell 'scripts/run_handoff_stage.sh' @($Stage)
        }
    }
} finally {
    $env:PATH = $savedPath
    $env:JAVA_HOME = $savedJavaHome
    $env:COURSIER_REPOSITORIES = $savedCoursierRepositories
    Pop-Location
}
