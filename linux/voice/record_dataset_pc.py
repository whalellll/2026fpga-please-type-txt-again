#!/usr/bin/env python3
"""PC guided recorder for the board's /dev/pango-audio0 (not the PC microphone).

Requires pyserial; GUI, WAV handling and playback use Python/Windows standard
libraries. Raw recordings remain outside the source/delivery tree.
"""
import argparse
import array
import base64
import csv
import gzip
import hashlib
import io
import json
import math
import os
from pathlib import Path
import queue
import re
import shlex
import sys
import threading
import time
import uuid
import wave

TOKENS = list(zip(
    "ju ma pao bing zu shuai jiang shi xiang yi er san si wu liu qi ba jiu jin tui ping chonglai quxiao tuichu".split(),
    "车 马 炮 兵 卒 帅 将 士 象 一 二 三 四 五 六 七 八 九 进 退 平 重来 取消 退出".split()))
PILOT = ["ma", "liu", "jin", "qi", "pao"]
MODES = {"pilot": "试录5词", "remaining": "补录其余19词", "all": "完整24词", "background": "静音/背景"}
KNOWN_ASR = {"/tmp/voice-gui-display/xqvoice-display", "/usr/bin/xqvoice"}
MAX_SAMPLES = 400 + 199 * 160


class SDCardNotPresentError(RuntimeError):
    pass


def write_json(path, value):
    with path.open("x", encoding="utf8") as f:
        json.dump(value, f, ensure_ascii=False, indent=2)
        f.write("\n")


def pcm_info(blob, max_samples=MAX_SAMPLES):
    with wave.open(io.BytesIO(blob), "rb") as f:
        if (f.getnchannels(), f.getsampwidth(), f.getframerate(), f.getcomptype()) != (1, 2, 16000, "NONE"):
            raise RuntimeError("录音格式必须为 16 kHz / 单声道 / S16_LE PCM")
        n = f.getnframes()
        pcm = f.readframes(n)
    if len(pcm) != n * 2 or not (400 <= n <= max_samples):
        raise RuntimeError("录音截断或长度超过本次允许的输入限制")
    samples = array.array("h", pcm)
    if sys.byteorder != "little":
        samples.byteswap()
    mean = sum(samples) / n
    rms = math.sqrt(sum((v - mean) ** 2 for v in samples) / n)
    peak = max(abs(v) for v in samples)
    metrics = {"samples": n, "seconds": n / 16000, "dc_mean": mean,
               "ac_rms": rms, "ac_rms_dbfs": 20 * math.log10(max(rms, 1e-9) / 32768),
               "peak": peak, "clipped_samples": sum(v in (-32768, 32767) for v in samples)}
    return pcm, samples, metrics


def wav_blob(pcm):
    out = io.BytesIO()
    with wave.open(out, "wb") as f:
        f.setnchannels(1)
        f.setsampwidth(2)
        f.setframerate(16000)
        f.writeframes(pcm)
    return out.getvalue()


class Board:
    def __init__(self, port, report=lambda message: None):
        import serial
        self.report = report
        self.command_chunk_bytes, self.command_pause_seconds = 1, 0.01
        self.uart = serial.Serial(port=None, baudrate=115200, timeout=0.05, write_timeout=3)
        self.uart.dtr = False
        self.uart.rts = False
        self.uart.port = port
        self.uart.open()
        try:
            self.uart.write(b"\r")
            self.until(rb"(?m)^/[^\r\n]* # ?$", 12)
        except BaseException:
            self.uart.close()
            raise

    def close(self):
        self.uart.close()

    def until(self, pattern, seconds, cue=None):
        result = bytearray()
        deadline = time.monotonic() + seconds
        alerted = False
        while time.monotonic() < deadline:
            result.extend(self.uart.read(max(1, min(self.uart.in_waiting, 8192))))
            if cue and not alerted and re.search(cue[0], result):
                alerted = True
                cue[1]()
            if re.search(pattern, result):
                return bytes(result)
            if len(result) > 4_000_000:
                raise RuntimeError("串口返回过长，已停止接收")
        tail = bytes(result[-1200:]).decode("utf8", errors="replace")
        raise RuntimeError("等待板卡超时；需要 Linux / # 提示符。\n" + tail)

    def command(self, command, seconds=20, cue=None):
        marker = "XQDATA_END_" + uuid.uuid4().hex
        wrapped = command + "; _xqd_rc=$?; printf '\\n" + marker + " %s\\n' \"$_xqd_rc\""
        # LiteUART has a small RX FIFO and Linux polls it. Pace control bytes.
        encoded = (wrapped + "\r").encode("ascii")
        for offset in range(0, len(encoded), self.command_chunk_bytes):
            self.uart.write(encoded[offset:offset + self.command_chunk_bytes])
            time.sleep(self.command_pause_seconds)
        text = self.until(rb"(?m)^" + marker.encode() + rb" (\d+)\r?\n", seconds, cue)
        rc = int(re.search(rb"(?m)^" + marker.encode() + rb" (\d+)\r?\n", text)[1])
        decoded = text.decode("utf8", errors="replace").replace("\r", "")
        if rc:
            raise RuntimeError("板端命令失败 rc=" + str(rc) + "\n" + decoded[-1800:])
        return decoded

    def recognizers(self):
        text = self.command(
            "for p in $(pidof xqvoice-display xqvoice 2>/dev/null); do "
            "printf '\\nXQDATA_ASR %s ' \"$p\"; readlink /proc/$p/exe; "
            "printf 'XQDATA_ARGV %s ' \"$p\"; base64 /proc/$p/cmdline | tr -d '\\n'; "
            "printf '\\n'; done; true")
        found = []
        for match in re.finditer(r"(?m)^XQDATA_ASR (\d+) (\S+)\n", text):
            pid, exe = int(match[1]), match[2]
            argv_line = re.search(r"(?m)^XQDATA_ARGV " + str(pid) + r" ([A-Za-z0-9+/=]+)\n", text)
            if not argv_line:
                raise RuntimeError("无法核对识别进程参数，保留进程不动")
            argv = base64.b64decode(argv_line[1], validate=True).rstrip(b"\0").decode("utf8").split("\0")
            if exe not in KNOWN_ASR or len(argv) < 3 or argv[1] != "/dev/pango-audio0" or not argv[2].startswith("/"):
                raise RuntimeError("识别进程身份与本候选不符，保留进程不动：" + exe)
            found.append({"pid": pid, "exe": exe, "argv": [exe] + argv[1:]})
        if len(found) > 1:
            raise RuntimeError("检测到多个识别进程，请先消除麦克风占用冲突")
        return found

    def probe(self, capture_program="xqaudio-capture"):
        program = shlex.quote(capture_program)
        info = self.command("test -c /dev/pango-audio0 && command -v " + program + " && " + program + " --help")
        processes = self.recognizers()
        return {"device": "/dev/pango-audio0", "format": "16000 Hz mono S16_LE",
                "recognizer": processes, "capture_tool": info}

    def sd_info(self, card):
        program = shlex.quote(card["binary_path"])
        try:
            check = self.command("sha256sum " + program + "; " + program + " --info", 60)
        except RuntimeError as exc:
            if re.search(r"SD initialization error=-1(?:\s|$)", str(exc)):
                raise SDCardNotPresentError(
                    "开发板未检测到SD卡，本次尚未录音。\n"
                    "如果卡已插到电脑，请点“从SD卡导入录音”进行手工标定。\n"
                    "继续录新音时，先在Windows安全弹出SD卡，再将卡插回开发板。") from None
            raise
        if card["binary_sha256"] + "  " + card["binary_path"] not in check:
            raise RuntimeError("板端SD工具哈希不匹配；本次尚未录音")
        match = re.search(r"(?m)^(\{.*\})\s*$", check)
        if not match:
            raise RuntimeError("板端未返回有效SD卡信息，本次尚未录音")
        info = json.loads(match[1])
        if any(info[key] != card[key] for key in ("cid", "partition_lba", "volume_serial")):
            raise RuntimeError("SD卡CID/分区/卷标识与已核对卡不一致；本次尚未录音")
        return info

    def restore(self, saved):
        if not saved:
            return "原先没有识别进程，保持停止"
        if self.recognizers():
            return "识别进程已运行"
        launch = " ".join(shlex.quote(x) for x in saved["argv"])
        self.command("mkdir -p /tmp/voice-gui-display; " + launch +
                     " </dev/null >>/tmp/voice-gui-display/voice.log 2>&1 & "
                     "echo $! >/tmp/voice-gui-display/voice.pid; sleep 1; "
                     "kill -0 $(cat /tmp/voice-gui-display/voice.pid)")
        if not self.recognizers():
            raise RuntimeError("识别进程未能恢复，请保留窗口错误记录")
        return "识别进程已恢复"

    def capture(self, cue, seconds=2, sd=None):
        if type(seconds) is not int or not 1 <= seconds <= 60:
            raise ValueError("板端每批录音长度需要为1～60秒")
        if sd is not None:
            # Same bounded 4B/8ms rhythm used by the verified ACK uploader.
            self.command_chunk_bytes, self.command_pause_seconds = 4, 0.008
        saved = None
        restore_needed = False
        result = None
        restore_error = None
        board_path = "/tmp/xqdata_" + uuid.uuid4().hex + ".wav"
        try:
            config_path = Path(__file__).with_name("sd_card_config.json")
            capture_config = sd["card"] if sd is not None else (
                json.loads(config_path.read_text(encoding="utf8")) if config_path.exists() else {})
            capture_program = capture_config.get("capture_binary_path", "xqaudio-capture")
            if "capture_binary_path" in capture_config:
                checked = self.command("sha256sum " + shlex.quote(capture_program))
                if capture_config["capture_binary_sha256"] + "  " + capture_program not in checked:
                    raise RuntimeError("板端采音工具哈希不匹配，本次尚未录音")
            if sd is not None:
                self.sd_info(sd["card"])
            probe = self.probe(capture_program)
            if seconds > 30 and "1..60" not in probe["capture_tool"]:
                raise RuntimeError("板端采音工具尚未升级到60秒版本，本次尚未录音")
            found = probe["recognizer"]
            saved = found[0] if found else None
            if saved:
                restore_needed = True
                self.report("临时暂停识别进程；棋盘 GUI 保持运行")
                pid = str(saved["pid"])
                self.command("test \"$(readlink /proc/" + pid + "/exe)\" = " + shlex.quote(saved["exe"]) +
                             " && kill -TERM " + pid +
                             "; for i in 1 2 3 4 5 6 7 8 9 10 11 12 13 14 15 16 17 18 19 20; do "
                             "kill -0 " + pid + " 2>/dev/null || break; sleep 0.1; done; "
                             "! kill -0 " + pid + " 2>/dev/null")
            marker = "XQDATA_REC_" + uuid.uuid4().hex
            log = self.command("printf '\\n" + marker + "\\n'; " + shlex.quote(capture_program) + " " + board_path + " " + str(seconds), seconds + 13,
                               (rb"(?m)^" + marker.encode() + rb"\r?\n", cue))
            match = re.search(r"PCM_TRANSPORT_PASS samples=(\d+).*?overflows=(\d+)", log)
            if not match or (int(match[1]), int(match[2])) != (seconds * 16000, 0):
                raise RuntimeError("录音样本数/丢样检查未通过，不进入数据集")
            # Recording and serial export are separate: never stream during capture.
            if restore_needed:
                self.report(self.restore(saved))
                restore_needed = False
            self.report("录音完成，正在核对WAV；选择SD时只返回保存回执，不回传音频")
            sha_text = self.command("sha256sum " + board_path, max(20, seconds * 2))
            expected = re.search(r"(?m)^([0-9a-f]{64})  " + re.escape(board_path) + r"\n", sha_text)
            if not expected:
                raise RuntimeError("未取得板端 WAV SHA-256；板端文件保留：" + board_path)
            if sd is not None:
                request = dict(sd["request"], raw_sha256=expected[1], samples=seconds * 16000,
                               fifo_overflows=0, labels_confirmed=False)
                request_bytes = json.dumps(request, ensure_ascii=True).encode()
                encoded_request = base64.b64encode(request_bytes).decode()
                request_path = board_path + ".request.json"
                checked_request = self.command("printf '%s' " + shlex.quote(encoded_request) + " | base64 -d >" + request_path +
                                               "; sha256sum " + request_path)
                if hashlib.sha256(request_bytes).hexdigest() + "  " + request_path not in checked_request:
                    raise RuntimeError("录音元数据回读SHA不一致，尚未写SD；RAM原WAV保留")
                card = sd["card"]
                self.report("正在写SD的VOICE目录并回读校验；请勿取卡")
                text = self.command(shlex.quote(card["binary_path"]) + " --save " + board_path +
                                    " --metadata " + request_path + " --expect-cid " + shlex.quote(card["cid"]) +
                                    " --expect-partition " + str(int(card["partition_lba"])) +
                                    " --expect-volume " + str(int(card["volume_serial"])), 240)
                receipt = json.loads(re.search(r"(?m)^(\{.*\})\s*$", text)[1])
                if (receipt.get("status") != "SD_WAV_JSON_READBACK_COMMIT_PASS" or receipt.get("cid") != card["cid"] or
                        receipt.get("wav_bytes") != 44 + seconds * 32000):
                    raise RuntimeError("SD保存回执未通过；RAM原WAV保留：" + board_path)
                self.command("rm -f " + board_path + " " + request_path)
                return None, {"transport": "board SD FAT32; audio not downloaded", "sd_receipt": receipt,
                              "board_path": board_path, "board_sha256": expected[1], "fifo_overflows": 0,
                              "samples": seconds * 16000, "request": request, "original_recognizer": saved,
                              "ram_temporary_removed_after_verified_sd_commit": True}
            mark = uuid.uuid4().hex
            begin, end = "XQDATA_BLOB_BEGIN_" + mark, "XQDATA_BLOB_END_" + mark
            text = self.command("printf '\\n" + begin + "\\n'; gzip -c " + board_path + " | base64" +
                                "; printf '\\n" + end + "\\n'", max(45, seconds * 5 + 20))
            encoded = re.search(r"(?m)^" + begin + r"\n([A-Za-z0-9+/=\n]+)\n" + end + r"\n", text)
            if not encoded:
                raise RuntimeError("WAV 回传不完整；板端文件保留：" + board_path)
            blob = gzip.decompress(base64.b64decode(encoded[1].replace("\n", ""), validate=True))
            if hashlib.sha256(blob).hexdigest() != expected[1]:
                raise RuntimeError("WAV SHA-256 不一致；板端文件保留：" + board_path)
            _, _, metrics = pcm_info(blob, max_samples=seconds * 16000)
            result = (blob, {"board_path": board_path, "board_sha256": expected[1], "fifo_overflows": 0,
                             "audio_metrics": metrics, "original_recognizer": saved,
                             "transport": "Buffered board capture, then gzip/base64 UART export; uncompressed SHA256 matched"})
            # Keep the verified board WAV until the next reset; PC raw copy is primary.
        finally:
            if restore_needed:
                try:
                    self.report(self.restore(saved))
                except Exception as exc:
                    restore_error = str(exc)
                    self.report("注意：恢复识别失败：" + restore_error)
            if restore_error:
                raise RuntimeError("识别恢复失败：" + restore_error)
        return result


class Recorder:
    def __init__(self, root, args):
        import tkinter as tk
        from tkinter import ttk, messagebox
        self.tk, self.ttk, self.messagebox = tk, ttk, messagebox
        self.root, self.args = root, args
        self.events = queue.Queue()
        self.busy = self.closing = False
        self.pending = None
        self.accepted = 0
        self.session_split = None
        self.session = time.strftime("%Y%m%d_%H%M%S") + "_" + uuid.uuid4().hex[:6]
        self.folder = args.output / args.speaker / self.session
        self.folder.mkdir(parents=True, exist_ok=False)
        self.port = tk.StringVar(value=args.port)
        self.mode = tk.StringVar(value=MODES[args.mode])
        self.split = tk.StringVar(value=args.split)
        self.counts = {}
        self.progress = tk.StringVar()
        self.label = tk.StringVar()
        self.start = tk.StringVar(value="0.00")
        self.end = tk.StringVar(value="2.00")
        self.status = tk.StringVar(value="板上麦克风录音；等红色提示“现在说”再读词。先试听，确认后保存。")
        root.title("板上麦克风 · 真人语音数据采集")
        root.geometry("1000x780")
        root.option_add("*Font", ("Microsoft YaHei UI", 11))
        frame = ttk.Frame(root, padding=16)
        frame.pack(fill="both", expand=True)
        ttk.Label(frame, text="录制 FPGA 板上 INMP441，非 PC 麦克风", font=("Microsoft YaHei UI", 16, "bold")).pack(anchor="w")
        ttk.Label(frame, text="每段2秒｜16 kHz / 单声道 / 16位｜录音时暂停识别，完成后恢复｜不通过语音走子").pack(anchor="w", pady=(4, 12))
        row = ttk.Frame(frame); row.pack(fill="x")
        ttk.Label(row, text="串口").pack(side="left")
        ttk.Entry(row, textvariable=self.port, width=10).pack(side="left", padx=8)
        self.probe_button = ttk.Button(row, text="检查板卡连接", command=lambda: self.run(self.probe))
        self.probe_button.pack(side="left", padx=4)
        self.mode_box = ttk.Combobox(row, textvariable=self.mode, values=list(MODES.values()), state="readonly", width=15)
        self.mode_box.pack(side="left", padx=12); self.mode_box.bind("<<ComboboxSelected>>", self.update_labels)
        ttk.Label(row, text="本轮分组").pack(side="left")
        self.split_box = ttk.Combobox(row, textvariable=self.split, values=["pilot", "train", "validation", "test"], state="readonly", width=11)
        self.split_box.pack(side="left", padx=8)
        self.label_box = ttk.Combobox(frame, textvariable=self.label, state="readonly", font=("Microsoft YaHei UI", 27), height=12)
        self.label_box.pack(fill="x", pady=18)
        self.update_labels()
        ttk.Label(frame, textvariable=self.progress, wraplength=940).pack(anchor="w", pady=(0, 8))
        self.record_button = ttk.Button(frame, text="准备好了 → 开始录音", command=self.record)
        self.record_button.pack(fill="x", ipady=10)
        self.status_label = ttk.Label(frame, textvariable=self.status, wraplength=940)
        self.status_label.pack(anchor="w", pady=12)
        self.canvas = tk.Canvas(frame, height=130, background="#10232b", highlightthickness=0)
        self.canvas.pack(fill="x")
        controls = ttk.Frame(frame); controls.pack(fill="x", pady=10)
        for title, gain in (("试听原始录音", False), ("放大试听（不改原始数据）", True)):
            ttk.Button(controls, text=title, command=lambda g=gain: self.play(g)).pack(side="left", padx=4)
        ttk.Label(controls, text="截取起/止秒").pack(side="left", padx=10)
        ttk.Entry(controls, textvariable=self.start, width=6).pack(side="left")
        ttk.Entry(controls, textvariable=self.end, width=6).pack(side="left", padx=4)
        self.accept_button = ttk.Button(controls, text="确认标签并保存", command=self.accept)
        self.accept_button.pack(side="left", padx=8)
        ttk.Button(controls, text="丢弃并重录", command=self.reject).pack(side="left", padx=4)
        self.log = tk.Text(frame, height=6, wrap="word", state="disabled")
        self.log.pack(fill="both", expand=True, pady=6)
        ttk.Label(frame, text="本轮目录：" + str(self.folder), wraplength=940).pack(anchor="w")
        root.protocol("WM_DELETE_WINDOW", self.close)
        root.after(50, self.poll)
        write_json(self.folder / "SESSION.json", {"schema": 1, "speaker": args.speaker, "session": self.session,
                   "device": "INMP441 via /dev/pango-audio0", "port": args.port, "raw_is_unmodified": True,
                   "initial_mode": args.mode, "initial_split": args.split,
                   "target_per_token": args.target_per_token,
                   "script_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest()})

    def update_labels(self, event=None):
        labels = [(p, c) for p, c in TOKENS if self.mode.get() != "试录5词" or p in PILOT]
        if self.mode.get() == "试录5词":
            labels = [(p, dict(TOKENS)[p]) for p in PILOT]
        if self.mode.get() == "补录其余19词":
            labels = [(p, c) for p, c in TOKENS if p not in PILOT]
        if self.mode.get() == "静音/背景":
            labels = [("background", "静音/背景（勿说话）")]
        self.label_box["values"] = [c + "  [" + p + "]" for p, c in labels]
        self.label_box.current(0)
        self.update_progress()

    def update_progress(self, advance=False):
        values = self.label_box["values"]
        tokens = [re.search(r"\[([a-z]+)\]", value)[1] for value in values]
        counts = [self.counts.get(token, 0) for token in tokens]
        target = self.args.target_per_token
        details = "  ".join("%s %d%s" % (value.split("  [")[0], count, "/%d" % target if target else "")
                            for value, count in zip(values, counts))
        completed = "；本组目标已完成，可关闭窗口" if target and all(n >= target for n in counts) else ""
        self.progress.set("本轮已确认 %d 段%s\n%s" % (sum(counts), completed, details))
        if advance:
            current = self.label_box.current()
            for offset in range(1, len(values) + 1):
                index = (current + offset) % len(values)
                if not target or counts[index] < target:
                    self.label_box.current(index)
                    break

    def note(self, message):
        self.status.set(message)
        self.log.configure(state="normal")
        self.log.insert("end", message + "\n"); self.log.see("end")
        self.log.configure(state="disabled")

    def run(self, task):
        if self.busy:
            return
        self.busy = True
        self.task_port = self.port.get()
        for widget in (self.record_button, self.probe_button, self.label_box, self.mode_box, self.split_box, self.accept_button):
            widget.configure(state="disabled")
        def work():
            try:
                task()
            except Exception as exc:
                self.events.put(("error", str(exc)))
            finally:
                self.events.put(("done", None))
        threading.Thread(target=work, daemon=False).start()

    def probe(self):
        board = Board(self.task_port, lambda s: self.events.put(("note", s)))
        try:
            result = board.probe()
            self.events.put(("note", "板卡连接正常：/dev/pango-audio0 和 xqaudio-capture 可用；识别进程数=" + str(len(result["recognizer"]))))
        finally:
            board.close()

    def record(self):
        if self.pending:
            self.messagebox.showinfo("先处理本段", "请先确认保存或丢弃当前录音。")
            return
        token = re.search(r"\[([a-z]+)\]", self.label.get())[1]
        split = self.split.get()
        if self.session_split is None:
            self.session_split = split
        elif split != self.session_split:
            self.messagebox.showerror("分组固定", "同一采集轮只使用一个数据分组。新分组请重新打开窗口开始新一轮。")
            return
        self.run(lambda: self.capture(token, split))

    def capture(self, token, split):
        self.events.put(("note", "正在核对板卡并准备录音，暂时不要说话……"))
        board = Board(self.task_port, lambda s: self.events.put(("note", s)))
        try:
            blob, metadata = board.capture(lambda: self.events.put(("cue", None)))
        finally:
            board.close()
        identity = time.strftime("%H%M%S") + "_" + token + "_" + uuid.uuid4().hex[:8]
        raw = self.folder / (identity + ".raw.wav")
        with raw.open("xb") as f:
            f.write(blob); f.flush(); os.fsync(f.fileno())
        metadata.update(schema=1, id=identity, token=token, split=split, speaker=self.args.speaker,
                        session=self.session, raw_path=raw.name, raw_sha256=hashlib.sha256(blob).hexdigest(),
                        status="pending_human_review")
        write_json(self.folder / (identity + ".raw.json"), metadata)
        self.events.put(("recorded", (raw, blob, metadata)))

    def poll(self):
        while not self.events.empty():
            kind, value = self.events.get()
            if kind == "note": self.note(value)
            elif kind == "cue":
                self.note("● 现在说所选词！录音约2秒，读一遍即可。")
                self.status_label.configure(foreground="#c62828")
            elif kind == "error":
                self.note("失败：" + value)
                self.messagebox.showerror("录音未完成", value)
            elif kind == "recorded":
                self.pending = value
                self.status_label.configure(foreground="#1b5e20")
                _, samples, metrics = pcm_info(value[1])
                self.draw(samples)
                self.start.set("0.00"); self.end.set("2.00")
                self.note("已接收并校验。请试听确认读词正确、完整。AC RMS=%.1f（%.1f dBFS），峰值=%d，削顶=%d。" %
                          (metrics["ac_rms"], metrics["ac_rms_dbfs"], metrics["peak"], metrics["clipped_samples"]))
            elif kind == "done":
                self.busy = False
                for widget in (self.record_button, self.probe_button, self.accept_button): widget.configure(state="normal")
                for widget in (self.label_box, self.mode_box): widget.configure(state="disabled" if self.pending else "readonly")
                self.split_box.configure(state="disabled" if self.session_split is not None else "readonly")
                if self.closing:
                    self.root.destroy(); return
        self.root.after(50, self.poll)

    def draw(self, samples):
        self.canvas.delete("all")
        width, height = max(500, self.canvas.winfo_width()), 130
        peak = max(1, max(abs(v) for v in samples))
        self.canvas.create_line(0, height / 2, width, height / 2, fill="#607780")
        for x in range(width):
            values = samples[x * len(samples) // width:(x + 1) * len(samples) // width]
            if values:
                self.canvas.create_line(x, height / 2 - max(values) / peak * 53,
                                        x, height / 2 - min(values) / peak * 53, fill="#5dd9a2")
        self.canvas.create_text(8, 8, text="波形按峰值缩放；原始音量见 AC RMS", fill="white", anchor="nw")

    def play(self, gain):
        if not self.pending:
            return
        try:
            import winsound
            path, blob, _ = self.pending
            if gain:
                pcm, samples, _ = pcm_info(blob)
                multiplier = min(32, 12000 / max(1, max(abs(v) for v in samples)))
                boosted = array.array("h", [max(-32768, min(32767, round(v * multiplier))) for v in samples])
                if sys.byteorder != "little": boosted.byteswap()
                path = self.folder / (".audition_" + uuid.uuid4().hex + ".wav")
                with path.open("xb") as f: f.write(wav_blob(boosted.tobytes()))
            winsound.PlaySound(str(path), winsound.SND_FILENAME | winsound.SND_ASYNC)
        except Exception as exc:
            self.messagebox.showerror("试听失败", str(exc))

    def accept(self):
        if self.busy or not self.pending:
            return
        try:
            raw, blob, metadata = self.pending
            pcm, _, _ = pcm_info(blob)
            begin, end = float(self.start.get()), float(self.end.get())
            if not (math.isfinite(begin) and math.isfinite(end) and 0 <= begin < end <= 2):
                raise ValueError("截取范围需要满足 0 ≤ 起点 < 终点 ≤ 2秒")
            first, last = round(begin * 16000), round(end * 16000)
            if not (400 <= last - first <= MAX_SAMPLES):
                raise ValueError("有效片段长度需要为25毫秒到约2秒，并包含完整发音")
            selected = wav_blob(pcm[first * 2:last * 2])
            path = self.folder / (metadata["id"] + ".wav")
            with path.open("xb") as f: f.write(selected)
            accepted = dict(metadata, status="human_accepted", path=path.name,
                            trim_samples=[first, last], sha256=hashlib.sha256(selected).hexdigest(),
                            selected_audio_metrics=pcm_info(selected)[2])
            write_json(self.folder / (metadata["id"] + ".accepted.json"), accepted)
            self.manifests()
            self.accepted += 1
            self.counts[metadata["token"]] = self.counts.get(metadata["token"], 0) + 1
            self.pending = None
            self.label_box.configure(state="readonly"); self.mode_box.configure(state="readonly")
            self.note("已保存第%d段：%s；分组=%s。pilot/背景仅存档，不进入训练清单。" % (self.accepted, path.name, metadata["split"]))
            self.update_progress(advance=True)
        except Exception as exc:
            self.messagebox.showerror("保存失败", str(exc))

    def manifests(self):
        rows = [json.loads(f.read_text(encoding="utf8")) for f in sorted(self.folder.glob("*.accepted.json"))]
        for name, selected in (("recordings.csv", rows), ("manifest.csv", [r for r in rows if r["split"] in ("train", "validation", "test") and r["token"] != "background"])):
            temporary = self.folder / (name + ".tmp")
            with temporary.open("w", encoding="utf8", newline="") as f:
                out = csv.writer(f); out.writerow(["path", "split", "tokens", "speaker", "session", "sha256", "parent_recording_sha256"])
                for r in selected: out.writerow([r["path"], r["split"], r["token"], r["speaker"], r["session"], r["sha256"], r.get("parent_recording_sha256", r.get("raw_sha256", r["sha256"]))])
                f.flush(); os.fsync(f.fileno())
            os.replace(temporary, self.folder / name)

    def reject(self):
        if self.busy or not self.pending: return
        _, _, metadata = self.pending
        write_json(self.folder / (metadata["id"] + ".rejected.json"), dict(metadata, status="human_rejected"))
        self.pending = None
        self.label_box.configure(state="readonly"); self.mode_box.configure(state="readonly")
        self.note("已标记丢弃，原始 WAV 保留供排查；可重新录同一个词。")

    def close(self):
        if self.busy:
            self.closing = True
            self.note("等待当前操作完成并恢复识别后关闭，请勿断开板卡。")
        else:
            self.root.destroy()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", default="COM17")
    parser.add_argument("--speaker", default="speaker01")
    parser.add_argument("--mode", choices=list(MODES), default="pilot")
    parser.add_argument("--split", choices=["pilot", "train", "validation", "test"], default="pilot")
    parser.add_argument("--target-per-token", type=int, default=0,
                        help="Accepted clips per token in this new session; 0 means no target")
    parser.add_argument("--output", type=Path, default=Path(__file__).resolve().parents[3] / "数据集" / "voice_real")
    parser.add_argument("--probe", action="store_true", help="Read-only board/recognizer check; no recording")
    args = parser.parse_args()
    if not re.fullmatch(r"[A-Za-z0-9_-]{1,40}", args.speaker): parser.error("speaker must use 1..40 ASCII letters/digits/_/-")
    if args.target_per_token < 0: parser.error("target-per-token must be nonnegative")
    if args.probe:
        board = Board(args.port)
        try: print(json.dumps(board.probe(), ensure_ascii=True, indent=2))
        finally: board.close()
    else:
        import tkinter as tk
        root = tk.Tk()
        Recorder(root, args)
        root.mainloop()


if __name__ == "__main__":
    main()
