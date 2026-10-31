// Windows process containment for simulation/build commands. A suspended child
// enters its own kill-on-close job before any MSYS exec or compiler can run.
using System;
using System.ComponentModel;
using System.Diagnostics;
using System.Runtime.InteropServices;
using System.Text;
using System.Threading;

namespace CpuSimulation {
    public static class BoundedProcess {
        [StructLayout(LayoutKind.Sequential)]
        struct SecurityAttributes {
            public int Length;
            public IntPtr Descriptor;
            [MarshalAs(UnmanagedType.Bool)] public bool Inherit;
        }
        [StructLayout(LayoutKind.Sequential, CharSet = CharSet.Unicode)]
        struct StartupInfo {
            public int Size;
            public string Reserved, Desktop, Title;
            public uint X, Y, XSize, YSize, XChars, YChars, Fill, Flags;
            public ushort ShowWindow, ReservedSize;
            public IntPtr ReservedData, Input, Output, Error;
        }
        [StructLayout(LayoutKind.Sequential)]
        struct ProcessInformation {
            public IntPtr Process, Thread;
            public uint ProcessId, ThreadId;
        }
        [StructLayout(LayoutKind.Sequential)]
        struct BasicLimits {
            public long ProcessTime, JobTime;
            public uint Flags;
            public UIntPtr MinWorkingSet, MaxWorkingSet;
            public uint ActiveProcessLimit;
            public UIntPtr Affinity;
            public uint PriorityClass, SchedulingClass;
        }
        [StructLayout(LayoutKind.Sequential)]
        struct IoCounters {
            public ulong ReadOps, WriteOps, OtherOps, ReadBytes, WriteBytes, OtherBytes;
        }
        [StructLayout(LayoutKind.Sequential)]
        struct ExtendedLimits {
            public BasicLimits Basic;
            public IoCounters Io;
            public UIntPtr ProcessMemory, JobMemory, PeakProcessMemory, PeakJobMemory;
        }
        [StructLayout(LayoutKind.Sequential)]
        struct Accounting {
            public long UserTime, KernelTime, PeriodUserTime, PeriodKernelTime;
            public uint PageFaults, TotalProcesses, ActiveProcesses, TerminatedProcesses;
        }
        [DllImport("kernel32.dll", CharSet = CharSet.Unicode, SetLastError = true)]
        static extern IntPtr CreateJobObject(IntPtr attributes, string name);
        [DllImport("kernel32.dll", SetLastError = true)]
        static extern bool SetInformationJobObject(IntPtr job, int type,
            ref ExtendedLimits limits, uint size);
        [DllImport("kernel32.dll", SetLastError = true)]
        static extern bool QueryInformationJobObject(IntPtr job, int type,
            out Accounting accounting, uint size, IntPtr returnedSize);
        [DllImport("kernel32.dll", SetLastError = true)]
        static extern bool AssignProcessToJobObject(IntPtr job, IntPtr process);
        [DllImport("kernel32.dll", CharSet = CharSet.Unicode, SetLastError = true)]
        static extern IntPtr CreateFile(string name, uint access, uint share,
            ref SecurityAttributes attributes, uint creation, uint flags, IntPtr template);
        [DllImport("kernel32.dll", CharSet = CharSet.Unicode, SetLastError = true)]
        static extern bool CreateProcess(string application, StringBuilder command,
            IntPtr processAttributes, IntPtr threadAttributes, bool inheritHandles,
            uint flags, IntPtr environment, string directory, ref StartupInfo startup,
            out ProcessInformation process);
        [DllImport("kernel32.dll", SetLastError = true)]
        static extern uint ResumeThread(IntPtr thread);
        [DllImport("kernel32.dll", SetLastError = true)]
        static extern uint WaitForSingleObject(IntPtr handle, uint milliseconds);
        [DllImport("kernel32.dll", SetLastError = true)]
        static extern bool GetExitCodeProcess(IntPtr process, out uint exitCode);
        [DllImport("kernel32.dll", SetLastError = true)]
        static extern bool TerminateJobObject(IntPtr job, uint exitCode);
        [DllImport("kernel32.dll", SetLastError = true)]
        static extern bool TerminateProcess(IntPtr process, uint exitCode);
        [DllImport("kernel32.dll")]
        static extern bool CloseHandle(IntPtr handle);

        static Exception NativeError(string operation) {
            return new Win32Exception(Marshal.GetLastWin32Error(), operation);
        }
        static IntPtr OpenRedirect(string path, uint access, uint creation) {
            var attributes = new SecurityAttributes();
            attributes.Length = Marshal.SizeOf(typeof(SecurityAttributes));
            attributes.Inherit = true;
            IntPtr handle = CreateFile(path, access, 7, ref attributes, creation, 0, IntPtr.Zero);
            if (handle == new IntPtr(-1)) throw NativeError("Open redirect: " + path);
            return handle;
        }
        static uint ActiveProcesses(IntPtr job) {
            Accounting value;
            if (!QueryInformationJobObject(job, 1, out value,
                (uint)Marshal.SizeOf(typeof(Accounting)), IntPtr.Zero))
                throw NativeError("Query simulation job");
            return value.ActiveProcesses;
        }
        static void Close(IntPtr handle) {
            if (handle != IntPtr.Zero && handle != new IntPtr(-1)) CloseHandle(handle);
        }
        public static int Run(string executable, string arguments, string directory,
            string stdout, string stderr, int timeoutSeconds) {
            if (timeoutSeconds < 1 || timeoutSeconds > 86400)
                throw new ArgumentOutOfRangeException("timeoutSeconds");
            IntPtr job = IntPtr.Zero, input = IntPtr.Zero, output = IntPtr.Zero, error = IntPtr.Zero;
            var process = new ProcessInformation();
            var elapsed = Stopwatch.StartNew();
            try {
                job = CreateJobObject(IntPtr.Zero, null);
                if (job == IntPtr.Zero) throw NativeError("Create simulation job");
                var limits = new ExtendedLimits();
                limits.Basic.Flags = 0x2000; // JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
                if (!SetInformationJobObject(job, 9, ref limits,
                    (uint)Marshal.SizeOf(typeof(ExtendedLimits))))
                    throw NativeError("Set simulation job limits");
                input = OpenRedirect("NUL", 0x80000000, 3);
                output = OpenRedirect(stdout, 0x40000000, 2);
                error = OpenRedirect(stderr, 0x40000000, 2);
                var startup = new StartupInfo();
                startup.Size = Marshal.SizeOf(typeof(StartupInfo));
                startup.Flags = 0x101; // STARTF_USESTDHANDLES | STARTF_USESHOWWINDOW
                startup.Input = input; startup.Output = output; startup.Error = error;
                var command = new StringBuilder("\"" + executable + "\"" +
                    (String.IsNullOrEmpty(arguments) ? "" : " " + arguments));
                if (!CreateProcess(executable, command, IntPtr.Zero, IntPtr.Zero, true,
                    0x08000004, IntPtr.Zero, directory, ref startup, out process))
                    throw NativeError("Create suspended simulation process");
                if (!AssignProcessToJobObject(job, process.Process))
                    throw NativeError("Assign simulation process to job");
                if (ResumeThread(process.Thread) == 0xffffffff)
                    throw NativeError("Resume simulation process");
                uint wait = WaitForSingleObject(process.Process, (uint)timeoutSeconds * 1000);
                if (wait == 0xffffffff) throw NativeError("Wait for simulation process");
                if (wait == 258) throw new TimeoutException("Process exceeded " + timeoutSeconds + " seconds");
                uint exitCode;
                if (!GetExitCodeProcess(process.Process, out exitCode))
                    throw NativeError("Read simulation process exit code");
                // A shell may exit before its descendants. Keep the same total
                // deadline and ownership until the complete job is empty.
                while (exitCode == 0 && ActiveProcesses(job) != 0) {
                    if (elapsed.ElapsedMilliseconds >= (long)timeoutSeconds * 1000)
                        throw new TimeoutException("Process descendants exceeded " + timeoutSeconds + " seconds");
                    Thread.Sleep(50);
                }
                return unchecked((int)exitCode);
            } catch {
                if (job != IntPtr.Zero) TerminateJobObject(job, 1);
                // Assignment failure must also clean up the suspended child.
                if (process.Process != IntPtr.Zero) {
                    TerminateProcess(process.Process, 1);
                    WaitForSingleObject(process.Process, 5000);
                }
                throw;
            } finally {
                Close(job); // also kills descendants when the parent failed
                Close(process.Thread); Close(process.Process);
                Close(input); Close(output); Close(error);
            }
        }
    }
}
