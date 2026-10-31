"""Drive the current SoC dense MAC with every job from DCT1 probe cases."""
import argparse
import hashlib
import json
import os
import shlex
import struct
import subprocess
from pathlib import Path

from dense_tiled_conv import input_scalar, make_jobs, read_cases


def words(data):
    return ''.join('%08x\n' % w[0] for w in struct.iter_unpack('<I', data))


def main():
    import numpy as np
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--vectors', type=Path, required=True)
    parser.add_argument('--distro', default='chiplab_sim')
    parser.add_argument('--core', type=Path, default=Path('rtl/mac_accel/MacAccelCore.v'),
                        help='Candidate MAC core source; captured in source identity evidence')
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    core = args.core if args.core.is_absolute() else root/args.core
    core_relative = core.resolve().relative_to(root).as_posix()
    if not core.is_file():
        raise ValueError('candidate core source is missing')
    directory = args.vectors.resolve()
    relative = directory.relative_to(root).as_posix()
    if not relative.startswith('build/'):
        raise ValueError('candidate output must be under build/')
    manifest = json.loads((directory/'manifest.json').read_text(encoding='utf-8'))
    binary = directory/'cases.bin'
    if hashlib.sha256(binary.read_bytes()).hexdigest() != manifest['cases_sha256']:
        raise ValueError('probe identity changed')
    payload, golden, descriptors, jobs = bytearray(), bytearray(), [], []
    for case in read_cases(binary):
        spec = case['spec']
        w = np.frombuffer(case['weights'], dtype=np.int8).astype(np.int64).reshape(spec.cout, spec.k)
        for job in make_jobs(spec, case['input'], case['weights']):
            a = np.array([[input_scalar(spec, case['input'], job.p0+p, job.k0+k)
                           for k in range(job.k)] for p in range(job.pixels)], dtype=np.int64)
            partial = a @ w[job.co0:job.co0+job.cout, job.k0:job.k0+job.k].T
            descriptors.extend((job.pixels, job.k, job.cout, len(job.inputs)//4, len(job.weights)//4,
                                partial.size, len(payload)//4, len(golden)//4))
            payload += job.inputs+job.weights
            golden += partial.astype('<i4').tobytes()
            jobs.append({'case': case['name'], 'p0': job.p0, 'co0': job.co0, 'k0': job.k0,
                         'pixels': job.pixels, 'cout': job.cout, 'k': job.k})
    (directory/'jobs.hex').write_text(words(struct.pack('<%dI' % len(descriptors), *descriptors)), encoding='ascii')
    (directory/'payload.hex').write_text(words(payload), encoding='ascii')
    (directory/'partial_golden.hex').write_text(words(golden), encoding='ascii')
    source = root/'sim/tb_soc_mac_accel.sv'
    harness_sha256 = hashlib.sha256(source.read_bytes()).hexdigest()
    prefix = source.read_text(encoding='utf-8').split('    // Same-shape 1x1/4-input/16-output legacy baseline.')[0]
    if not prefix.endswith('\n'): raise ValueError('SoC harness marker changed')
    prefix = prefix.replace('module tb_soc_mac_accel;', 'module tb_soc_mac_dense_tiled;')
    prefix = prefix.replace('(64*1024)', '(1024*1024)')
    body = r'''
    localparam JOBS=@@JOBS@@;
    reg [31:0] descriptors[0:JOBS*8-1];
    reg [31:0] payload[0:@@PAYLOAD@@-1];
    reg [31:0] golden[0:@@GOLDEN@@-1];
    integer j,i,p,k,co,iw,ww,ow,po,go,timeout;
    integer read_bytes,write_bytes,total_cycles,total_read,total_write;
    reg measuring=0;reg[31:0]value,cycles;
    always @(posedge clk) if(measuring) begin
        if(s1_arvalid&&s1_arready)begin
            if(s1_arlen>=8 || s1_araddr[11:0]+((s1_arlen+1)<<2)>4096)
                fail("invalid dense read burst");
            read_bytes=read_bytes+((s1_arlen+1)<<2);
        end
        if(s1_awvalid&&s1_awready)begin
            if(s1_awlen>=8 || s1_awaddr[11:0]+((s1_awlen+1)<<2)>4096)
                fail("invalid dense write burst");
            write_bytes=write_bytes+((s1_awlen+1)<<2);
        end
    end
    initial begin
        repeat(10000000)@(posedge clk);$fatal(1,"dense tiled global timeout");
    end
    initial begin
        $readmemh("@@REL@@/jobs.hex",descriptors);
        $readmemh("@@REL@@/payload.hex",payload);
        $readmemh("@@REL@@/partial_golden.hex",golden);
        repeat(4)@(posedge clk);@(negedge clk);resetn=1;
        total_cycles=0;total_read=0;total_write=0;
        for(j=0;j<JOBS;j=j+1)begin
            p=descriptors[j*8];k=descriptors[j*8+1];co=descriptors[j*8+2];
            iw=descriptors[j*8+3];ww=descriptors[j*8+4];ow=descriptors[j*8+5];
            po=descriptors[j*8+6];go=descriptors[j*8+7];
            // Test-only CPU staging; the actual MAC uses the unchanged AXI arbiter.
            for(i=0;i<iw;i=i+1)u_ram.memory[i]=payload[po+i];
            for(i=0;i<ww;i=i+1)u_ram.memory[2048+i]=payload[po+iw+i];
            for(i=0;i<ow+32;i=i+1)u_ram.memory[18432+i]=32'h5a5a5a5a;
            reg_write(9'h08,32'h2);
            reg_write(9'h10,(k<<16)|p);
            reg_write(9'h14,32'h53000000|co);
            reg_write(9'h18,32'h1b000000);
            reg_write(9'h1c,32'h1b002000);
            reg_write(9'h20,32'h1b000000);
            reg_write(9'h24,32'h1b012000);
            read_bytes=0;write_bytes=0;measuring=1;
            reg_write(9'h08,32'h1);
            reg_rd_addr=9'h0c;#1;timeout=0;
            while(!reg_rd_data[1]&&!reg_rd_data[2]&&timeout<1000000)begin
                @(posedge clk);#1;timeout=timeout+1;
            end
            measuring=0;
            if(timeout==1000000 || reg_rd_data[2])fail("dense job failed/timeout");
            if(read_bytes!=(iw+ww)*4 || write_bytes!=ow*4)begin
                $display("traffic j=%0d got=%0d/%0d expected=%0d/%0d",j,read_bytes,write_bytes,(iw+ww)*4,ow*4);
                fail("dense DDR traffic mismatch");
            end
            reg_rd_addr=9'h28;#1;cycles=reg_rd_data;
            total_cycles=total_cycles+cycles;total_read=total_read+read_bytes;total_write=total_write+write_bytes;
            for(i=0;i<ow;i=i+1)begin
                cpu_read_word(32'h1b012000+i*4,value);
                if(value!==golden[go+i])begin
                    $display("j=%0d k=%0d cout=%0d element=%0d got=%0d expected=%0d",j,k,co,i,$signed(value),$signed(golden[go+i]));
                    fail("dense partial result mismatch");
                end
            end
            if(u_ram.memory[18432+ow]!==32'h5a5a5a5a)fail("dense output tail overwrite");
            $display("DENSE_TILED_RTL_JOB_PASS index=%0d pixels=%0d k=%0d cout=%0d cycles=%0d read_bytes=%0d write_bytes=%0d",j,p,k,co,cycles,read_bytes,write_bytes);
        end
        $display("DENSE_TILED_CONV_SOC_PASS jobs=%0d cycles=%0d read_bytes=%0d write_bytes=%0d",JOBS,total_cycles,total_read,total_write);
        $finish;
    end
endmodule
'''
    replacements = {'@@JOBS@@': str(len(jobs)), '@@PAYLOAD@@': str(len(payload)//4),
                    '@@GOLDEN@@': str(len(golden)//4), '@@REL@@': relative}
    for key, value in replacements.items(): body = body.replace(key, value)
    bench = directory/'dense_tiled_testbench.sv'
    bench.write_text(prefix+body, encoding='utf-8', newline='\n')
    sources = ['rtl/soc/axi_2x1_arbiter.v', 'rtl/mac_accel/mac_accel_dma_kernel.v',
               'rtl/mac_accel/mac_accel_axi_master32.v', 'rtl/mac_accel/xiangqi_sparse_eval.v',
               'rtl/mac_accel/pff1_stagea_gather.v', 'rtl/mac_accel/mac_accel_ddr_kernel_top.v']
    sources += [p.relative_to(root).as_posix() for p in sorted((root/'rtl/mac_accel').glob('mac_conv_*.v'))]
    sources += ['rtl/mac_accel/mac_weight_double_buffer.v', core_relative,
                'sim/gtp_apm_e2_perf_sim.v', 'sim/axi_shared_ram.sv', relative+'/dense_tiled_testbench.sv']
    for s in sources:
        if not (root/s).is_file(): raise ValueError('missing source '+s)
    source_hashes = {s: hashlib.sha256((root/s).read_bytes()).hexdigest() for s in sources}
    wsl_root = '/mnt/'+root.drive[0].lower()+root.as_posix()[2:] if os.name == 'nt' else str(root)
    executable = relative+'/dense_tiled_testbench.vvp'
    script = '#!/bin/bash\nset -euo pipefail\ncd '+shlex.quote(wsl_root)+'\n'
    script += 'iverilog -g2012 -s tb_soc_mac_dense_tiled -o '+shlex.quote(executable)+' '+' '.join(map(shlex.quote, sources))+'\n'
    script += 'vvp '+shlex.quote(executable)+'\n'
    (directory/'run_dense_sim.sh').write_text(script, encoding='utf-8', newline='\n')
    command = ['wsl','-d',args.distro,'--','bash',wsl_root+'/'+relative+'/run_dense_sim.sh'] if os.name == 'nt' else ['bash',str(directory/'run_dense_sim.sh')]
    result = subprocess.run(command, cwd=root, capture_output=True)
    text = (result.stdout+result.stderr).decode('utf-8', errors='replace')
    (directory/'rtl_simulation.log').write_text(text, encoding='utf-8')
    evidence = {'native_exit': result.returncode, 'jobs': jobs, 'model_sha256': manifest['model_sha256'],
                'cases_sha256': manifest['cases_sha256'], 'original_harness_sha256': harness_sha256,
                'simulation_sources': source_hashes,
                'board_acceptance': False, 'mac_core_source': core_relative}
    changed = [s for s in sources if hashlib.sha256((root/s).read_bytes()).hexdigest()!=source_hashes[s]]
    evidence['source_changes_during_run'] = changed
    (directory/'rtl_evidence.json').write_text(json.dumps(evidence, indent=2)+'\n', encoding='utf-8')
    # WSL startup diagnostics on Windows may be UTF-16 on stderr. Preserve them
    # in the log while printing the ASCII RTL result stream only.
    print(result.stdout.decode('utf-8', errors='backslashreplace'), end='')
    if result.returncode or changed or 'DENSE_TILED_CONV_SOC_PASS' not in text: raise SystemExit(result.returncode or 1)


if __name__ == '__main__': main()
