// Compiled in memory by receive_camera.ps1; no receiver executable is needed.
using System;
using System.Collections.Generic;
using System.Drawing;
using System.Drawing.Imaging;
using System.Globalization;
using System.IO;
using System.Net;
using System.Net.Sockets;
using System.Runtime.InteropServices;
using System.Text;

public static class CameraReceiver
{
    const int BoardPort = 49061, PcPort = 49062, Header = 40;
    const int Width = 1280, Height = 720, Chunk = 1024, Bytes = Width * Height * 2;
    static readonly uint[] Table = MakeTable();
    static volatile bool Stopping;

    sealed class Packet
    {
        public byte Type;
        public uint Session, Frame, Seq, Total, FrameCrc, PacketCrc;
        public ushort PayloadLength;
        public byte[] Data;
    }

    sealed class Active
    {
        public uint Session, Frame, FrameCrc, Next;
        public DateTime Last;
        public string RawPath;
        public FileStream Stream;
        public readonly List<uint> ChunkCrc = new List<uint>();
    }

    sealed class Completed
    {
        public uint Session, Frame, FrameCrc, Seq;
        public string PngPath, JsonPath;
    }

    static uint[] MakeTable()
    {
        uint[] table = new uint[256];
        for (uint i = 0; i < 256; i++) {
            uint c = i;
            for (int j = 0; j < 8; j++) c = (c >> 1) ^ ((c & 1) != 0 ? 0xedb88320u : 0u);
            table[i] = c;
        }
        return table;
    }

    static uint Update(uint crc, byte[] bytes, int offset, int count)
    {
        for (int i = 0; i < count; i++) crc = Table[(crc ^ bytes[offset + i]) & 255] ^ (crc >> 8);
        return crc;
    }

    static ushort U16(byte[] b, int i) { return (ushort)((b[i] << 8) | b[i + 1]); }
    static uint U32(byte[] b, int i) { return ((uint)b[i] << 24) | ((uint)b[i + 1] << 16) | ((uint)b[i + 2] << 8) | b[i + 3]; }
    static void W16(byte[] b, int i, ushort v) { b[i] = (byte)(v >> 8); b[i + 1] = (byte)v; }
    static void W32(byte[] b, int i, uint v) { b[i] = (byte)(v >> 24); b[i + 1] = (byte)(v >> 16); b[i + 2] = (byte)(v >> 8); b[i + 3] = (byte)v; }

    static Packet Parse(byte[] b)
    {
        if (b.Length < Header || b[0] != 'C' || b[1] != 'A' || b[2] != 'M' || b[3] != 'P' ||
            b[4] != 1 || U16(b, 6) != Header || U16(b, 24) != Width || U16(b, 26) != Height ||
            U16(b, 28) != 1 || U32(b, 20) != Bytes || U16(b, 30) != b.Length - Header ||
            U16(b, 30) > Chunk) return null;
        uint crc = Update(0xffffffffu, b, 0, 36);
        crc = Update(crc, b, Header, b.Length - Header) ^ 0xffffffffu;
        if (U32(b, 36) != crc) return null;
        return new Packet { Type = b[5], Session = U32(b, 8), Frame = U32(b, 12),
            Seq = U32(b, 16), Total = U32(b, 20), FrameCrc = U32(b, 32),
            PacketCrc = crc, PayloadLength = U16(b, 30), Data = b };
    }

    static void Reply(UdpClient udp, IPEndPoint peer, byte type, Packet request)
    {
        byte[] b = new byte[Header];
        b[0] = (byte)'C'; b[1] = (byte)'A'; b[2] = (byte)'M'; b[3] = (byte)'P';
        b[4] = 1; b[5] = type; W16(b, 6, Header);
        W32(b, 8, request.Session); W32(b, 12, request.Frame);
        W32(b, 16, request.Seq); W32(b, 20, Bytes);
        W16(b, 24, Width); W16(b, 26, Height); W16(b, 28, 1);
        W32(b, 32, request.FrameCrc);
        W32(b, 36, Update(0xffffffffu, b, 0, 36) ^ 0xffffffffu);
        udp.Send(b, b.Length, peer);
    }

    static void Delete(string path)
    {
        if (path != null && File.Exists(path)) File.Delete(path);
    }

    static void Discard(Active a)
    {
        if (a == null) return;
        if (a.Stream != null) { a.Stream.Dispose(); a.Stream = null; }
        Delete(a.RawPath);
    }

    static uint ConvertPng(string rawPath, string pngPart)
    {
        uint crc = 0xffffffffu;
        byte[] raw = new byte[Width * 2], bgr = new byte[Width * 3];
        using (FileStream input = new FileStream(rawPath, FileMode.Open, FileAccess.Read, FileShare.None))
        using (Bitmap bitmap = new Bitmap(Width, Height, PixelFormat.Format24bppRgb)) {
            if (input.Length != Bytes) throw new InvalidDataException("Incomplete raw image");
            BitmapData locked = bitmap.LockBits(new Rectangle(0, 0, Width, Height),
                ImageLockMode.WriteOnly, PixelFormat.Format24bppRgb);
            try {
                for (int y = 0; y < Height; y++) {
                    int read = 0;
                    while (read < raw.Length) {
                        int n = input.Read(raw, read, raw.Length - read);
                        if (n == 0) throw new EndOfStreamException();
                        read += n;
                    }
                    crc = Update(crc, raw, 0, raw.Length);
                    for (int x = 0; x < Width; x++) {
                        int rgb = raw[2 * x] | (raw[2 * x + 1] << 8);
                        int r = (rgb >> 11) & 31, g = (rgb >> 5) & 63, b = rgb & 31;
                        bgr[3 * x] = (byte)((b << 3) | (b >> 2));
                        bgr[3 * x + 1] = (byte)((g << 2) | (g >> 4));
                        bgr[3 * x + 2] = (byte)((r << 3) | (r >> 2));
                    }
                    Marshal.Copy(bgr, 0, IntPtr.Add(locked.Scan0, y * locked.Stride), bgr.Length);
                }
            } finally { bitmap.UnlockBits(locked); }
            bitmap.Save(pngPart, ImageFormat.Png);
        }
        return crc ^ 0xffffffffu;
    }

    static Completed Save(Active a, string directory)
    {
        a.Stream.Flush(true); a.Stream.Dispose(); a.Stream = null;
        DateTimeOffset now = DateTimeOffset.Now;
        string prefix = "CMOS2_" + now.ToString("yyyyMMdd_HHmmss_fff", CultureInfo.InvariantCulture) +
            "_frame" + a.Frame.ToString("D10", CultureInfo.InvariantCulture);
        string png = null, json = null, pngPart = null, jsonPart = null;
        for (int suffix = 0; suffix < 10000; suffix++) {
            string stem = Path.Combine(directory, prefix + (suffix == 0 ? "" : "_" + suffix));
            png = stem + ".png"; json = stem + ".json";
            if (!File.Exists(png) && !File.Exists(json)) break;
            if (suffix == 9999) throw new IOException("No free photo filename");
        }
        pngPart = png + ".part"; jsonPart = json + ".part";
        bool jsonMoved = false;
        try {
            uint actualCrc = ConvertPng(a.RawPath, pngPart);
            if (actualCrc != a.FrameCrc) throw new InvalidDataException("Whole-frame CRC32 mismatch");
            string metadata = "{\n" +
                "  \"captured_at_pc\": \"" + now.ToString("o", CultureInfo.InvariantCulture) + "\",\n" +
                "  \"frame_number\": " + a.Frame.ToString(CultureInfo.InvariantCulture) + ",\n" +
                "  \"width\": 1280,\n  \"height\": 720,\n" +
                "  \"source\": \"CMOS2\",\n" +
                "  \"raw_pixel_format\": \"RGB565 little-endian, top-to-bottom rows\",\n" +
                "  \"raw_crc32\": \"" + a.FrameCrc.ToString("x8", CultureInfo.InvariantCulture) + "\"\n}\n";
            File.WriteAllText(jsonPart, metadata, new UTF8Encoding(false));
            // Publish the PNG last: its appearance is the commit point.
            // A crash before this point cannot leave an apparently saved
            // image without its metadata.
            File.Move(jsonPart, json); jsonMoved = true;
            File.Move(pngPart, png);
            Console.WriteLine(Path.GetFullPath(png));
            return new Completed { Session = a.Session, Frame = a.Frame,
                FrameCrc = a.FrameCrc, Seq = a.Next, PngPath = png, JsonPath = json };
        } catch {
            Delete(pngPart); Delete(jsonPart);
            if (jsonMoved) Delete(json);
            throw;
        } finally { Delete(a.RawPath); }
    }

    public static void Run(string outputDirectory, string listenAddress, string boardAddress)
    {
        string directory = Path.GetFullPath(outputDirectory);
        Directory.CreateDirectory(directory);
        IPAddress board = IPAddress.Parse(boardAddress);
        Active active = null; Completed complete = null;
        using (UdpClient udp = new UdpClient(new IPEndPoint(IPAddress.Parse(listenAddress), PcPort))) {
            udp.Client.ReceiveTimeout = 250;
            foreach (string pattern in new[] { ".camera_*.rgb565.part", "CMOS2_*.png.part", "CMOS2_*.json.part" })
                foreach (string stale in Directory.GetFiles(directory, pattern)) Delete(stale);
            Stopping = false;
            ConsoleCancelEventHandler onCancel = delegate(object sender, ConsoleCancelEventArgs args) {
                args.Cancel = true; Stopping = true;
            };
            Console.CancelKeyPress += onCancel;
            Console.WriteLine("Camera receiver listening on UDP " + PcPort + "; output: " + directory);
            Console.WriteLine("Press Ctrl+C to stop.");
            try {
            while (!Stopping) {
                if (active != null && (DateTime.UtcNow - active.Last).TotalSeconds > 5) {
                    Console.Error.WriteLine("Camera session timed out; partial data removed.");
                    Discard(active); active = null;
                }
                IPEndPoint peer = new IPEndPoint(IPAddress.Any, 0);
                byte[] bytes;
                try { bytes = udp.Receive(ref peer); }
                catch (SocketException ex) {
                    if (ex.SocketErrorCode == SocketError.TimedOut) continue;
                    throw;
                }
                if (!peer.Address.Equals(board) || peer.Port != BoardPort) continue;
                Packet p = Parse(bytes);
                if (p == null) continue;
                if (p.Type == 4 && p.Seq == 0 && p.PayloadLength == 0) {
                    if (active != null && active.Session == p.Session && active.Frame == p.Frame &&
                        active.FrameCrc == p.FrameCrc) {
                        Discard(active); active = null;
                    }
                    if (complete != null && complete.Session == p.Session && complete.Frame == p.Frame &&
                        complete.FrameCrc == p.FrameCrc) {
                        Delete(complete.PngPath); Delete(complete.JsonPath); complete = null;
                    }
                    continue;
                }
                if (p.Type == 1 && p.Seq == 0 && p.PayloadLength == 0) {
                    if (active != null && active.Session == p.Session && active.Frame == p.Frame &&
                        active.FrameCrc == p.FrameCrc) { active.Last = DateTime.UtcNow; Reply(udp, peer, 0x81, p); continue; }
                    if (active != null) { Reply(udp, peer, 0x84, p); continue; }
                    string raw = Path.Combine(directory, ".camera_" + Guid.NewGuid().ToString("N") + ".rgb565.part");
                    active = new Active { Session = p.Session, Frame = p.Frame,
                        FrameCrc = p.FrameCrc, RawPath = raw,
                        Stream = new FileStream(raw, FileMode.CreateNew, FileAccess.Write, FileShare.None),
                        Last = DateTime.UtcNow };
                    Reply(udp, peer, 0x81, p); continue;
                }
                if (complete != null && p.Type == 3 && p.Session == complete.Session &&
                    p.Frame == complete.Frame && p.FrameCrc == complete.FrameCrc &&
                    p.Seq == complete.Seq) { Reply(udp, peer, 0x83, p); continue; }
                if (active == null || active.Session != p.Session || active.Frame != p.Frame ||
                    active.FrameCrc != p.FrameCrc) continue;
                active.Last = DateTime.UtcNow;
                if (p.Type == 2) {
                    int expectedLength = (int)Math.Min(Chunk, Bytes - (long)p.Seq * Chunk);
                    if (expectedLength <= 0 || p.PayloadLength != expectedLength) { Reply(udp, peer, 0x84, p); continue; }
                    if (p.Seq == active.Next) {
                        active.Stream.Write(p.Data, Header, p.PayloadLength);
                        active.ChunkCrc.Add(p.PacketCrc); active.Next++;
                        Reply(udp, peer, 0x82, p);
                    } else if (p.Seq < active.Next && active.ChunkCrc[(int)p.Seq] == p.PacketCrc) {
                        Reply(udp, peer, 0x82, p);
                    }
                    continue;
                }
                if (p.Type == 3 && p.PayloadLength == 0) {
                    if (p.Seq != active.Next || active.Stream.Length != Bytes) {
                        Reply(udp, peer, 0x84, p); continue;
                    }
                    try {
                        complete = Save(active, directory);
                        active = null;
                        Reply(udp, peer, 0x83, p);
                    } catch (Exception ex) {
                        Console.Error.WriteLine("Photo save failed: " + ex.Message);
                        Discard(active); active = null;
                        Reply(udp, peer, 0x84, p);
                    }
                }
            }
            } finally {
                Discard(active);
                Console.CancelKeyPress -= onCancel;
            }
        }
    }
}
