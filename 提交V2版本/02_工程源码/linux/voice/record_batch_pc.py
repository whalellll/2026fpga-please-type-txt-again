#!/usr/bin/env python3
"""Record a long board-microphone batch, then propose and review word clips.

Boundaries are energy proposals, never automatic transcription or acceptance.
All clips from one batch share a parent_recording_sha256 for grouped splitting.
"""
import argparse
import array
import hashlib
import json
import os
from pathlib import Path
import queue
import re
import sys
import threading
import time
import uuid
import zlib

import numpy as np
from record_dataset_pc import Board, MAX_SAMPLES, TOKENS, Recorder, pcm_info, wav_blob, write_json

LABELS = {c: p for p, c in TOKENS}
LABELS.update({p: p for p, c in TOKENS})
LABELS.update({'仕': 'shi', '相': 'xiang'})


def pc_volume_serial(root):
    if os.name != 'nt': return None
    import ctypes
    serial = ctypes.c_ulong()
    if ctypes.windll.kernel32.GetVolumeInformationW(str(Path(root)) + '\\', None, 0,
                                                  ctypes.byref(serial), None, None, None, 0):
        return serial.value
    return None


def pc_sd_voice_directories(card, roots=None):
    if 'volume_serial' not in card: return []
    if roots is None:
        if os.name != 'nt': return []
        import ctypes
        mask = ctypes.windll.kernel32.GetLogicalDrives()
        roots = [Path(chr(65 + i) + ':/') for i in range(26) if mask & (1 << i)]
    return [Path(root) / 'VOICE' for root in roots
            if pc_volume_serial(root) == card['volume_serial'] and (Path(root) / 'VOICE').is_dir()]


def latest_sd_recording(directory, speaker, split):
    for wav in sorted(Path(directory).glob('REC*.WAV'), reverse=True):
        try:
            request = json.loads(wav.with_suffix('.JSON').read_text(encoding='utf8')).get('request', {})
            if request.get('speaker') == speaker and request.get('split') == split: return wav
        except (OSError, ValueError): pass
    return None


def parse_words(text):
    words = [w for w in re.split(r'[\s,，、;；]+', text.strip()) if w]
    if not words or any(w not in LABELS for w in words):
        raise ValueError('请用空格分开词，例如：马 六 进 七 炮。重来/取消/退出各作为一个完整词。')
    return [LABELS[w] for w in words]


def propose_segments(samples, gap_ms=300, multiplier=3.0):
    """10ms DC-centered RMS with hysteresis; preserve raw PCM for review."""
    values = np.asarray(samples, dtype=np.float64)
    count = len(values) // 160
    frames = values[:count * 160].reshape(count, 160)
    centered = frames - frames.mean(axis=1, keepdims=True)
    energy = np.sqrt(np.mean(centered * centered, axis=1))
    floor = float(np.percentile(energy, 20))
    high, low = max(8.0, floor * multiplier), max(5.0, floor * multiplier * 0.57)
    quiet_limit = max(10, int(gap_ms) // 10)
    intervals = []
    active, run, quiet, start, last = False, 0, 0, 0, 0
    for i, value in enumerate(energy):
        if not active:
            run = run + 1 if value >= high else 0
            if run >= 3:
                active, start, last, quiet = True, max(0, i - run + 1 - 8), i, 0
        else:
            if value >= low:
                last, quiet = i, 0
            else:
                quiet += 1
            if quiet >= quiet_limit:
                end = min(len(values), (last + 16) * 160)
                if end - start * 160 >= 1600:
                    intervals.append((start * 160, end))
                active, run = False, 0
    if active:
        intervals.append((start * 160, min(len(values), (last + 16) * 160)))
    merged = []
    for start, end in intervals:
        if merged and start < merged[-1][1]:
            merged[-1] = (merged[-1][0], max(end, merged[-1][1]))
        else:
            merged.append((start, end))
    return merged, {'noise_rms_estimate': floor, 'start_rms': high, 'stop_rms': low, 'gap_ms': gap_ms}


class BatchRecorder:
    def __init__(self, root, args):
        import tkinter as tk
        from tkinter import ttk, messagebox, filedialog
        self.tk, self.ttk, self.box, self.files = tk, ttk, messagebox, filedialog
        self.root, self.args = root, args
        self.events, self.busy, self.closing = queue.Queue(), False, False
        self.session = time.strftime('%Y%m%d_%H%M%S') + '_' + uuid.uuid4().hex[:6]
        self.folder = args.output / args.speaker / self.session
        self.folder.mkdir(parents=True, exist_ok=False)
        self.batch, self.rows, self.session_split = None, [], None
        self.port, self.split = tk.StringVar(value=args.port), tk.StringVar(value=args.split)
        self.seconds, self.words = tk.StringVar(value=str(args.seconds)), tk.StringVar(value=args.words)
        self.transport = tk.StringVar(value='SD卡（不回传）' if Path(__file__).with_name('sd_card_config.json').exists() else '串口回传PC')
        config_path = Path(__file__).with_name('sd_card_config.json')
        self.card = json.loads(config_path.read_text(encoding='utf8')) if config_path.exists() else {}
        self.pc_sd_dirs, self.media_status = [], tk.StringVar()
        self.gap, self.multiplier = tk.StringVar(value='300'), tk.StringVar(value='3.0')
        self.begin, self.end, self.label = tk.StringVar(value='0.00'), tk.StringVar(value='1.00'), tk.StringVar()
        self.status = tk.StringVar(value='每批建议5～8个词。前1秒安静；红色提示后按词表读，每词间停顿0.6～1秒。')
        root.title('板上麦克风 · 批量录音与切分')
        root.geometry('1100x850')
        root.option_add('*Font', ('Microsoft YaHei UI', 10))
        frame = ttk.Frame(root, padding=12); frame.pack(fill='both', expand=True)
        ttk.Label(frame, text='一次录多个词 → 按停顿初切 → 逐段试听确认', font=('Microsoft YaHei UI', 16, 'bold')).pack(anchor='w')
        ttk.Label(frame, text='录板上INMP441；一次只回传一批。初切不是自动识字；“重来/取消/退出”各连读为一个词。').pack(anchor='w')
        line = ttk.Frame(frame); line.pack(fill='x', pady=7)
        ttk.Label(line, text='串口').pack(side='left'); self.port_box = ttk.Entry(line, textvariable=self.port, width=9); self.port_box.pack(side='left', padx=5)
        self.split_box = ttk.Combobox(line, textvariable=self.split, values=['train', 'validation', 'test'], state='readonly', width=11); self.split_box.pack(side='left', padx=5)
        ttk.Label(line, text='录音秒数').pack(side='left')
        self.seconds_box = ttk.Combobox(line, textvariable=self.seconds, values=['10', '15', '20', '30', '45', '60'], state='readonly', width=6); self.seconds_box.pack(side='left', padx=5)
        self.transport_box = ttk.Combobox(line, textvariable=self.transport, values=['SD卡（不回传）', '串口回传PC'], state='readonly', width=16); self.transport_box.pack(side='left', padx=5)
        self.record_button = ttk.Button(line, text='开始录一批', command=self.record); self.record_button.pack(side='left', padx=5)
        self.import_button = ttk.Button(line, text='导入长WAV', command=self.import_wave); self.import_button.pack(side='left', padx=5)
        self.finish_button = ttk.Button(line, text='结束本批，准备下一批', command=self.finish); self.finish_button.pack(side='left', padx=5)
        line = ttk.Frame(frame); line.pack(fill='x')
        ttk.Label(line, text='本批依次读（空格分词）').pack(side='left')
        self.words_box = ttk.Entry(line, textvariable=self.words); self.words_box.pack(side='left', fill='x', expand=True, padx=5)
        line = ttk.Frame(frame); line.pack(fill='x', pady=3)
        ttk.Label(line, textvariable=self.media_status, wraplength=860, foreground='#185a83').pack(side='left', fill='x', expand=True)
        self.sd_import_button = ttk.Button(line, text='从SD卡导入录音', command=self.import_sd_wave); self.sd_import_button.pack(side='right', padx=5)
        self.status_label = ttk.Label(frame, textvariable=self.status, wraplength=1050); self.status_label.pack(anchor='w', pady=8)
        self.canvas = tk.Canvas(frame, height=135, background='#10232b', highlightthickness=0); self.canvas.pack(fill='x')
        self.canvas.bind('<Button-1>', lambda e: self.cursor(e, True))
        self.canvas.bind('<Button-3>', lambda e: self.cursor(e, False))
        ttk.Label(frame, text='波形左键设起点、右键设终点。按片段试听/调整，再逐段确认；单词片段最长约2.015秒。').pack(anchor='w')
        line = ttk.Frame(frame); line.pack(fill='x', pady=6)
        ttk.Label(line, text='停顿ms').pack(side='left'); ttk.Entry(line, textvariable=self.gap, width=6).pack(side='left', padx=4)
        ttk.Label(line, text='起音/底噪倍数').pack(side='left'); ttk.Entry(line, textvariable=self.multiplier, width=6).pack(side='left', padx=4)
        self.cut_button = ttk.Button(line, text='按停顿重新初切', command=self.cut); self.cut_button.pack(side='left', padx=8)
        self.tree = ttk.Treeview(frame, columns=['start', 'end', 'seconds', 'label', 'status'], show='headings', height=9)
        for key, title in [('start', '起点秒'), ('end', '终点秒'), ('seconds', '时长'), ('label', '建议/人工标签'), ('status', '状态')]:
            self.tree.heading(key, text=title); self.tree.column(key, width=160, stretch=True)
        self.tree.pack(fill='both', expand=True); self.tree.bind('<<TreeviewSelect>>', self.select)
        line = ttk.Frame(frame); line.pack(fill='x', pady=7)
        ttk.Label(line, text='起/止秒').pack(side='left')
        ttk.Entry(line, textvariable=self.begin, width=7).pack(side='left', padx=3)
        ttk.Entry(line, textvariable=self.end, width=7).pack(side='left', padx=3)
        self.label_box = ttk.Combobox(line, textvariable=self.label, values=[c + ' [' + p + ']' for p, c in TOKENS], state='readonly', width=15); self.label_box.pack(side='left', padx=5)
        self.actions = []
        for title, action in [('保存边界', self.edit), ('新增手动片段', self.add), ('删候选', self.delete), ('试听', self.play), ('放大试听', lambda: self.play(True)), ('确认标签并保存', self.accept)]:
            button = ttk.Button(line, text=title, command=action); button.pack(side='left', padx=2); self.actions.append(button)
        self.log = tk.Text(frame, height=4, state='disabled', wrap='word'); self.log.pack(fill='x')
        ttk.Label(frame, text='保存目录：' + str(self.folder), wraplength=1050).pack(anchor='w')
        write_json(self.folder / 'SESSION.json', {'schema': 1, 'speaker': args.speaker, 'session': self.session,
                   'workflow': 'batch-human-reviewed', 'initial_split': args.split,
                   'script_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                   'parent_group_policy': 'All clips with the same parent_recording_sha256 stay in one evaluation subset'})
        root.protocol('WM_DELETE_WINDOW', self.close); root.after(80, self.poll)
        self.transport.trace_add('write', lambda *_: self.refresh_media(False))
        self.refresh_media()

    def refresh_media(self, schedule=True):
        self.pc_sd_dirs = pc_sd_voice_directories(self.card)
        if self.pc_sd_dirs:
            self.media_status.set('SD卡位于电脑：%s。可导入录音标定；录新音需安全弹出后插回开发板。' % self.pc_sd_dirs[0])
        else:
            self.media_status.set('电脑未检测到绑定的SD卡；导入可选择已复制的WAV。录新音前请确认卡已插回开发板。')
        self.sd_import_button.configure(state='normal' if self.pc_sd_dirs and not self.busy and not self.batch else 'disabled')
        blocked = self.transport.get() == 'SD卡（不回传）' and bool(self.pc_sd_dirs)
        self.record_button.configure(state='disabled' if blocked or self.busy or self.batch else 'normal')
        if schedule: self.root.after(2000, self.refresh_media)

    def note(self, text):
        self.status.set(text); self.log.configure(state='normal'); self.log.insert('end', text + '\n'); self.log.see('end'); self.log.configure(state='disabled')

    def lock(self):
        if self.session_split is None: self.session_split = self.split.get()
        if self.session_split != self.split.get(): raise ValueError('同轮分组固定；新分组请另开窗口。')
        self.split_box.configure(state='disabled')

    def record(self):
        if self.busy or self.batch:
            self.box.showinfo('先处理本批', '请先完成本批审核并点“结束本批”。'); return
        try:
            if self.transport.get() == 'SD卡（不回传）' and pc_sd_voice_directories(self.card):
                self.box.showinfo('SD卡在电脑上', '请点“从SD卡导入录音”进行标定。继续录新音时，先安全弹出SD卡，再插回开发板。'); return
            planned = parse_words(self.words.get())
            seconds, port = int(self.seconds.get()), self.port.get()
            sd = None
            if self.transport.get() == 'SD卡（不回传）':
                card = json.loads(Path(__file__).with_name('sd_card_config.json').read_text(encoding='utf8'))
                sd = {'card': card, 'request': {'speaker': self.args.speaker, 'session': self.session,
                      'split': self.session_split, 'planned_tokens': planned,
                      'batch_id': uuid.uuid4().hex, 'planned_is_ground_truth': False}}
            self.lock()
        except Exception as exc:
            self.box.showerror('输入有误', str(exc)); return
        self.busy = True
        for widget in [self.record_button, self.import_button, self.sd_import_button, self.finish_button, self.cut_button, self.port_box, self.words_box, self.seconds_box, self.transport_box, self.label_box, *self.actions]: widget.configure(state='disabled')
        self.note('准备录音；先不要说话，等红色提示。')
        def work():
            board = None
            try:
                board = Board(port, lambda t: self.events.put(('note', t)))
                blob, metadata = board.capture(lambda: self.events.put(('cue', seconds)), seconds=seconds, sd=sd)
                self.events.put(('sd_saved', metadata) if sd is not None else ('recorded', (blob, metadata, planned)))
            except Exception as exc: self.events.put(('error', str(exc)))
            finally:
                if board: board.close()
                self.events.put(('done', None))
        threading.Thread(target=work, daemon=False).start()

    def poll(self):
        while not self.events.empty():
            kind, value = self.events.get()
            if kind == 'note': self.note(value)
            elif kind == 'cue':
                self.status_label.configure(foreground='#c62828'); self.note('● 正在录%d秒！前1秒安静，然后按上方顺序逐词读，词间停顿0.6～1秒。' % value)
            elif kind == 'recorded':
                try: self.load(*value)
                except Exception as exc: self.note('导入录音失败：' + str(exc)); self.box.showerror('保留原录音', str(exc))
            elif kind == 'sd_saved':
                path = self.folder / ('sd_saved_' + uuid.uuid4().hex + '.json'); write_json(path, value)
                self.note('已存SD：%s + JSON，回读校验通过。可继续下一批；取卡前等待操作结束，复制VOICE目录后导入WAV切分。' % value['sd_receipt']['wav'])
            elif kind == 'error': self.note('失败：' + value); self.box.showerror('未完成', value)
            elif kind == 'done':
                self.busy = False; self.status_label.configure(foreground='#1b5e20')
                for widget in [self.record_button, self.import_button, self.finish_button, self.cut_button, self.port_box, self.words_box, *self.actions]: widget.configure(state='normal')
                self.seconds_box.configure(state='readonly'); self.transport_box.configure(state='readonly'); self.label_box.configure(state='readonly')
                self.refresh_media(False)
                if self.closing: self.root.destroy(); return
        self.root.after(80, self.poll)

    def import_sd_wave(self):
        self.refresh_media(False)
        if not self.pc_sd_dirs:
            self.box.showinfo('未找到电脑端SD卡', '请将SD卡通过读卡器连接电脑，或用“导入长WAV”选择已复制的录音。'); return
        directory = self.pc_sd_dirs[0]
        latest = latest_sd_recording(directory, self.args.speaker, self.split.get())
        path = self.files.askopenfilename(initialdir=str(directory), initialfile=latest.name if latest else '',
                                          filetypes=[('PCM WAV', '*.wav *.WAV')])
        if path: self.import_wave(path)

    def import_wave(self, path=None):
        if self.busy or self.batch: return
        if path is None:
            self.refresh_media(False)
            options = {'initialdir': str(self.pc_sd_dirs[0])} if self.pc_sd_dirs else {}
            path = self.files.askopenfilename(filetypes=[('PCM WAV', '*.wav *.WAV')], **options)
        if not path: return
        try:
            blob = Path(path).read_bytes()
            pcm_info(blob, max_samples=60 * 16000)
            metadata = {'transport': 'Manual WAV import; no board capture/overflow acceptance claimed', 'import_sha256': hashlib.sha256(blob).hexdigest()}
            sidecar = Path(path).with_suffix('.JSON')
            if sidecar.exists():
                origin = json.loads(sidecar.read_text(encoding='utf8')); request = origin.get('request', {})
                if origin.get('transport') == 'board SD FAT32':
                    if origin['wav_crc32'] != '%08x' % (zlib.crc32(blob) & 0xffffffff) or request.get('raw_sha256') != metadata['import_sha256']:
                        raise ValueError('SD WAV与JSON的CRC/SHA不一致，不能导入为同批数据')
                    if request.get('split') != self.split.get(): raise ValueError('请先将本轮分组选为SD录音原分组：' + str(request.get('split')))
                    if request.get('speaker') != self.args.speaker: raise ValueError('SD录音的speaker与本窗口不同，请使用原说话人ID新开窗口')
                    self.words.set(' '.join(dict(TOKENS)[token] for token in request['planned_tokens']))
                    metadata['sd_origin'] = origin
            planned = parse_words(self.words.get()); self.lock()
            self.load(blob, metadata, planned)
            self.refresh_media(False)
        except Exception as exc: self.box.showerror('无法导入', str(exc))

    def load(self, blob, metadata, planned):
        pcm, samples, metrics = pcm_info(blob, max_samples=60 * 16000)
        identity = 'batch_' + time.strftime('%H%M%S') + '_' + uuid.uuid4().hex[:8]
        raw = self.folder / (identity + '.raw.wav'); raw.write_bytes(blob)
        meta = dict(metadata, schema=1, id=identity, raw_path=raw.name, raw_sha256=hashlib.sha256(blob).hexdigest(),
                    speaker=self.args.speaker, session=self.session, split=self.session_split,
                    planned_tokens=planned, planned_is_ground_truth=False, audio_metrics=metrics, status='batch_pending_human_review')
        write_json(self.folder / (identity + '.batch.json'), meta)
        self.batch = {'pcm': pcm, 'samples': samples, 'metadata': meta, 'planned': planned}
        self.rows = []; self.cut()

    def cut(self):
        if not self.batch: return
        if any(r.get('accepted') for r in self.rows):
            self.box.showinfo('已有保存', '本批已有确认片段；请手动调整剩余候选，避免重复接纳。'); return
        try:
            gap, multiplier = int(self.gap.get()), float(self.multiplier.get())
            if not 100 <= gap <= 1000 or not 1.2 <= multiplier <= 10: raise ValueError('停顿100～1000ms，倍数1.2～10')
            intervals, details = propose_segments(self.batch['samples'], gap, multiplier)
            match = len(intervals) == len(self.batch['planned'])
            self.rows = [{'start': a, 'end': b, 'token': self.batch['planned'][i] if match else '', 'accepted': False}
                         for i, (a, b) in enumerate(intervals)]
            self.refresh(); self.draw()
            self.note('初切%d段，计划%d词；%s。底噪估计RMS=%.1f。候选需逐段试听确认。' %
                      (len(intervals), len(self.batch['planned']), '数量一致，已填建议标签' if match else '数量不一致，未自动套标签，请调整边界并手动选词', details['noise_rms_estimate']))
        except Exception as exc: self.box.showerror('切分参数', str(exc))

    def refresh(self, selected=0):
        self.tree.delete(*self.tree.get_children())
        for i, r in enumerate(self.rows):
            seconds = (r['end'] - r['start']) / 16000
            state = '已确认保存' if r['accepted'] else ('过长，需手动调整' if seconds > MAX_SAMPLES / 16000 else '待人工确认')
            self.tree.insert('', 'end', iid=str(i), values=['%.3f' % (r['start'] / 16000), '%.3f' % (r['end'] / 16000), '%.3f' % seconds, dict(TOKENS).get(r['token'], '未标注'), state])
        if self.rows:
            key = str(min(selected, len(self.rows) - 1)); self.tree.selection_set(key); self.tree.see(key); self.select()

    def selected(self):
        selection = self.tree.selection()
        return int(selection[0]) if selection else None

    def select(self, event=None):
        i = self.selected()
        if i is None: return
        row = self.rows[i]; self.begin.set('%.3f' % (row['start'] / 16000)); self.end.set('%.3f' % (row['end'] / 16000))
        self.label.set(dict(TOKENS)[row['token']] + ' [' + row['token'] + ']' if row['token'] else '')
        self.draw()

    def boundaries(self):
        if not self.batch: raise ValueError('先录音或导入WAV')
        a, b = round(float(self.begin.get()) * 16000), round(float(self.end.get()) * 16000)
        if not 0 <= a < b <= len(self.batch['samples']): raise ValueError('边界需位于原录音范围内')
        return a, b

    def edit(self):
        i = self.selected()
        if self.busy or i is None: return
        try:
            if self.rows[i]['accepted']: raise ValueError('已确认文件保留；本工具不覆盖已保存片段')
            self.rows[i]['start'], self.rows[i]['end'] = self.boundaries(); self.refresh(i)
        except Exception as exc: self.box.showerror('无法调整', str(exc))

    def add(self):
        if self.busy: return
        try:
            a, b = self.boundaries(); self.rows.append({'start': a, 'end': b, 'token': '', 'accepted': False}); self.refresh(len(self.rows) - 1)
        except Exception as exc: self.box.showerror('无法新增', str(exc))

    def delete(self):
        i = self.selected()
        if self.busy or i is None: return
        if self.rows[i]['accepted']:
            self.box.showinfo('已保存', '已确认文件保留，不在此处删除。'); return
        self.rows.pop(i); self.refresh(i)

    def cursor(self, event, begin):
        if not self.batch or self.busy: return
        seconds = max(0, min(1, event.x / max(1, self.canvas.winfo_width()))) * len(self.batch['samples']) / 16000
        (self.begin if begin else self.end).set('%.3f' % seconds); self.draw()

    def draw(self):
        self.canvas.delete('all')
        if not self.batch: return
        samples = np.asarray(self.batch['samples'], dtype=np.int32)
        width = max(1, self.canvas.winfo_width()); peak = max(1, int(np.abs(samples).max()))
        for x in range(width):
            chunk = samples[x * len(samples) // width:(x + 1) * len(samples) // width]
            if len(chunk): self.canvas.create_line(x, 65 - int(chunk.max()) * 55 / peak, x, 65 - int(chunk.min()) * 55 / peak, fill='#5dd9a2')
        try:
            for value, color in [(float(self.begin.get()), '#ffd166'), (float(self.end.get()), '#ff7070')]:
                x = value * 16000 / len(samples) * width; self.canvas.create_line(x, 0, x, 135, fill=color, width=2)
        except ValueError: pass

    def play(self, gain=False):
        if self.busy: return
        try:
            import winsound
            a, b = self.boundaries(); values = np.asarray(self.batch['samples'][a:b], dtype=np.int32)
            if gain: values = np.clip(values * min(32, 12000 / max(1, int(np.abs(values).max()))), -32768, 32767).astype(np.int32)
            path = self.folder / ('.audition_' + uuid.uuid4().hex + '.wav'); path.write_bytes(wav_blob(values.astype('<i2').tobytes()))
            winsound.PlaySound(str(path), winsound.SND_FILENAME | winsound.SND_ASYNC)
        except Exception as exc: self.box.showerror('无法试听', str(exc))

    def accept(self):
        i = self.selected()
        if self.busy or i is None or self.rows[i]['accepted']: return
        try:
            a, b = self.boundaries()
            if not 400 <= b - a <= MAX_SAMPLES: raise ValueError('单词片段需25ms～约2.015秒，完整保留发音；请手动调整过长片段')
            token = re.search(r'\[([a-z]+)\]', self.label.get())
            if not token: raise ValueError('请先手动选择正确词标签')
            if any(r['accepted'] and a < r['end'] and b > r['start'] for r in self.rows): raise ValueError('与已保存片段重叠，请调整边界')
            token = token[1]; meta = self.batch['metadata']; identity = meta['id'] + '_' + uuid.uuid4().hex[:6] + '_' + token
            path = self.folder / (identity + '.wav'); blob = wav_blob(self.batch['pcm'][a * 2:b * 2]); path.write_bytes(blob)
            accepted = dict(meta, id=identity, token=token, status='human_accepted', path=path.name,
                            sha256=hashlib.sha256(blob).hexdigest(), trim_samples=[a, b], selected_audio_metrics=pcm_info(blob)[2],
                            parent_recording_id=meta['id'], parent_recording_sha256=meta['raw_sha256'])
            write_json(self.folder / (identity + '.accepted.json'), accepted)
            self.rows[i].update(start=a, end=b, token=token, accepted=True)
            Recorder.manifests(self)
            self.refresh(next((j for j, r in enumerate(self.rows) if not r['accepted']), i))
            self.note('已保存 %s；本批已确认%d/%d段。同一批原录音的片段共享分组标识。' % (dict(TOKENS)[token], sum(r['accepted'] for r in self.rows), len(self.rows)))
        except Exception as exc: self.box.showerror('未保存', str(exc))

    def finish(self):
        if self.busy or not self.batch: return
        if any(not r['accepted'] for r in self.rows) and not self.box.askyesno('未确认片段', '未确认片段不会进入数据集，原始长录音仍保留。结束本批？'): return
        self.batch, self.rows = None, []; self.tree.delete(*self.tree.get_children()); self.canvas.delete('all'); self.note('本批结束，可修改词表并录下一批。')
        self.refresh_media(False)

    def close(self):
        if self.busy: self.closing = True; self.note('等待录音/回传及识别恢复后关闭，请勿拔线。')
        else: self.root.destroy()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--port', default='COM17'); parser.add_argument('--speaker', default='speaker01')
    parser.add_argument('--split', choices=['train', 'validation', 'test'], default='train')
    parser.add_argument('--seconds', type=int, choices=[10, 15, 20, 30, 45, 60], default=15)
    parser.add_argument('--words', default='马 六 进 七 炮')
    parser.add_argument('--import-wav', type=Path, help='Open an existing WAV for manual review, without recording')
    parser.add_argument('--output', type=Path, default=Path(__file__).resolve().parents[3] / '数据集' / 'voice_real')
    args = parser.parse_args()
    if not re.fullmatch(r'[A-Za-z0-9_-]{1,40}', args.speaker): parser.error('Invalid speaker ID')
    import tkinter as tk
    root = tk.Tk(); recorder = BatchRecorder(root, args)
    if args.import_wav: root.after(200, lambda: recorder.import_wave(str(args.import_wav)))
    root.mainloop()


if __name__ == '__main__': main()
