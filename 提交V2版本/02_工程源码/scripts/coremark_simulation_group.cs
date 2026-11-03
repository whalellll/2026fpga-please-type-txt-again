// Windows process containment for simulation/build commands. A suspended child
// enters its own kill-on-close job before any MSYS exec or compiler can run.
using System;
using System.ComponentModel;
using System.Diagnostics;
using System.IO;
using System.Runtime.InteropServices;
using System.Text;
using System.Threading;

namespace CpuSimulation {
    public static class GroupProcess {
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
        static extern uint WaitForMultipleObjects(uint count, IntPtr[] handles,
            [MarshalAs(UnmanagedType.Bool)] bool waitAll, uint milliseconds);
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
        // Four independent long RTL simulations share one kill-on-close job.
        // The PID record is written immediately after each child starts so a
        // caller can stop the exact owner even if its console is detached.
        public static void RunGroup(string executable, string[] arguments,
            string directory, string[] stdout, string[] stderr,
            string[] names, int timeoutSeconds, string pidRecord) {
            if (arguments == null || arguments.Length == 0 || arguments.Length > 64 ||
                stdout == null || stderr == null || names == null ||
                stdout.Length != arguments.Length || stderr.Length != arguments.Length ||
                names.Length != arguments.Length || timeoutSeconds < 1 ||
                timeoutSeconds > 86400)
                throw new ArgumentException("Invalid simulation group");
            IntPtr job = IntPtr.Zero, input = IntPtr.Zero;
            var processes = new ProcessInformation[arguments.Length];
            var elapsed = Stopwatch.StartNew();
            try {
                job = CreateJobObject(IntPtr.Zero, null);
                if (job == IntPtr.Zero) throw NativeError("Create simulation group job");
                var limits = new ExtendedLimits();
                limits.Basic.Flags = 0x2000; // JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
                if (!SetInformationJobObject(job, 9, ref limits,
                    (uint)Marshal.SizeOf(typeof(ExtendedLimits))))
                    throw NativeError("Set simulation group job limits");
                int owner = Process.GetCurrentProcess().Id;
                File.WriteAllText(pidRecord,
                    "owner_pid=" + owner + "\r\n" +
                    "started_utc=" + DateTime.UtcNow.ToString("o") + "\r\n" +
                    "deadline_utc=" + DateTime.UtcNow.AddSeconds(timeoutSeconds).ToString("o") + "\r\n" +
                    "stop_owner=Stop-Process -Id " + owner + " -Force\r\n" +
                    "containment=Windows Job, kill all children on owner exit or timeout\r\n");
                input = OpenRedirect("NUL", 0x80000000, 3);
                for (int i = 0; i < arguments.Length; i++) {
                    IntPtr output = IntPtr.Zero, error = IntPtr.Zero;
                    try {
                        output = OpenRedirect(stdout[i], 0x40000000, 2);
                        error = OpenRedirect(stderr[i], 0x40000000, 2);
                        var startup = new StartupInfo();
                        startup.Size = Marshal.SizeOf(typeof(StartupInfo));
                        startup.Flags = 0x101; // std handles and hidden window
                        startup.Input = input; startup.Output = output; startup.Error = error;
                        var command = new StringBuilder("\"" + executable + "\" " + arguments[i]);
                        if (!CreateProcess(executable, command, IntPtr.Zero, IntPtr.Zero, true,
                            0x08000004, IntPtr.Zero, directory, ref startup, out processes[i]))
                            throw NativeError("Create suspended simulation group process");
                        if (!AssignProcessToJobObject(job, processes[i].Process))
                            throw NativeError("Assign simulation group process to job");
                        if (ResumeThread(processes[i].Thread) == 0xffffffff)
                            throw NativeError("Resume simulation group process");
                        File.AppendAllText(pidRecord,
                            names[i] + "_pid=" + processes[i].ProcessId + "\r\n" +
                            names[i] + "_stop=Stop-Process -Id " +
                            processes[i].ProcessId + " -Force\r\n");
                    } finally {
                        Close(output); Close(error);
                    }
                }
                var pending = new System.Collections.Generic.List<int>();
                for (int i = 0; i < processes.Length; i++) pending.Add(i);
                while (pending.Count != 0) {
                    long remaining = (long)timeoutSeconds * 1000 - elapsed.ElapsedMilliseconds;
                    if (remaining <= 0) throw new TimeoutException("Simulation group timed out");
                    var handles = new IntPtr[pending.Count];
                    for (int p = 0; p < pending.Count; p++)
                        handles[p] = processes[pending[p]].Process;
                    uint wait = WaitForMultipleObjects((uint)handles.Length, handles,
                        false, (uint)remaining);
                    if (wait == 0xffffffff) throw NativeError("Wait for simulation group process");
                    if (wait == 258) throw new TimeoutException("Simulation group timed out");
                    if (wait >= pending.Count) throw new Exception("Unexpected simulation group wait result: " + wait);
                    int i = pending[(int)wait];
                    uint exitCode;
                    if (!GetExitCodeProcess(processes[i].Process, out exitCode))
                        throw NativeError("Read simulation group exit code");
                    if (exitCode != 0)
                        throw new Exception("Simulation group process failed: " + names[i] +
                            ", exit " + exitCode + ", log " + stdout[i]);
                    pending.RemoveAt((int)wait);
                }
                while (ActiveProcesses(job) != 0) {
                    if (elapsed.ElapsedMilliseconds >= (long)timeoutSeconds * 1000)
                        throw new TimeoutException("Simulation group descendants timed out");
                    Thread.Sleep(50);
                }
                File.AppendAllText(pidRecord,
                    "completed_utc=" + DateTime.UtcNow.ToString("o") + "\r\n" +
                    "status=ALL_EXIT_ZERO\r\n");
            } catch (Exception ex) {
                if (job != IntPtr.Zero) TerminateJobObject(job, 1);
                for (int i = 0; i < processes.Length; i++) {
                    if (processes[i].Process != IntPtr.Zero) {
                        TerminateProcess(processes[i].Process, 1);
                        WaitForSingleObject(processes[i].Process, 5000);
                    }
                }
                if (File.Exists(pidRecord))
                    File.AppendAllText(pidRecord,
                        "stopped_utc=" + DateTime.UtcNow.ToString("o") + "\r\n" +
                        "status=STOPPED_OR_FAILED\r\n" +
                        "reason=" + ex.GetType().Name + ": " + ex.Message + "\r\n");
                throw;
            } finally {
                Close(job);
                for (int i = 0; i < processes.Length; i++) {
                    Close(processes[i].Thread); Close(processes[i].Process);
                }
                Close(input);
            }
        }
    }
}
