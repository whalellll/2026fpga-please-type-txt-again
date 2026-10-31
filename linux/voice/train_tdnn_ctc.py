#!/usr/bin/env python3
"""Train/export the CPU-reference Mandarin Xiangqi TDNN-CTC model.

Manifest CSV columns: path,split,tokens.  Tokens are space-separated pinyin
symbols, for example: recordings/0001.wav,train,"ma liu jin qi".
Only 16 kHz, mono, signed-16-bit PCM WAV files are accepted.
"""

import argparse
import csv
import hashlib
import math
import random
import struct
import wave
import zlib
from pathlib import Path

import numpy as np
import torch
from torch import nn
from torch.nn import functional as F
from torch.utils.data import DataLoader, Dataset


TOKENS = [
    "<blank>", "ju", "ma", "pao", "bing", "zu", "shuai", "jiang",
    "shi", "xiang", "yi", "er", "san", "si", "wu", "liu", "qi",
    "ba", "jiu", "jin", "tui", "ping", "chonglai", "quxiao", "tuichu",
]
TOKEN_IDS = {token: index for index, token in enumerate(TOKENS)}
COEFFICIENTS_Q14 = np.asarray([
    32729, 32679, 32610, 32522, 32413, 32138, 31786, 31357, 30853, 30274,
    28899, 27246, 25330, 23170, 18205, 12540, 6393, 0, -12540, -23170,
], dtype=np.int64)
WINDOW = 400
HOP = 160
MAX_FRAMES = 200
FRAME_STRIDE = 4
CONTEXT_FRAMES = 11
HEADER_BYTES = 128


def read_wave(path: Path) -> np.ndarray:
    with wave.open(str(path), "rb") as source:
        if (source.getnchannels(), source.getsampwidth(), source.getframerate()) != (1, 2, 16000):
            raise ValueError(f"{path}: expected mono 16-bit PCM at 16 kHz")
        samples = np.frombuffer(source.readframes(source.getnframes()), dtype="<i2")
    maximum = WINDOW + (MAX_FRAMES - 1) * HOP
    if len(samples) < WINDOW or len(samples) > maximum:
        raise ValueError(f"{path}: sample count {len(samples)} is outside {WINDOW}..{maximum}")
    return samples.astype(np.int32)


def approximate_log2_q8(value: int) -> int:
    if value <= 0:
        return 0
    bit = value.bit_length() - 1
    normalized = value << (63 - bit)
    return bit * 256 + ((normalized >> 55) & 0xFF)


def raw_features(samples: np.ndarray) -> np.ndarray:
    frames = 1 + (len(samples) - WINDOW) // HOP
    starts = np.arange(frames, dtype=np.int64)[:, None] * HOP
    offsets = np.arange(WINDOW, dtype=np.int64)[None, :]
    windows = samples[starts + offsets].astype(np.int64)
    previous = np.concatenate(
        (np.zeros((frames, 1), dtype=np.int64), windows[:, :-1]), axis=1
    )
    filtered = (windows - ((31785 * previous) >> 15)) >> 4
    state1 = np.zeros((frames, len(COEFFICIENTS_Q14)), dtype=np.int64)
    state2 = np.zeros_like(state1)
    for sample in range(WINDOW):
        state = filtered[:, sample, None] + ((COEFFICIENTS_Q14 * state1) >> 14) - state2
        state2, state1 = state1, state
    energy = state1 * state1 + state2 * state2 - (
        (COEFFICIENTS_Q14 * state1 * state2) >> 14
    )
    result = np.asarray([
        [approximate_log2_q8(max(1, int(item))) for item in frame]
        for frame in energy
    ], dtype=np.int32)
    return result


def normalize(features: np.ndarray, offset_q8: int, scale_q15: int) -> np.ndarray:
    delta = features.astype(np.int64) - offset_q8
    scaled = delta * scale_q15
    values = np.where(scaled >= 0, (scaled + 16384) >> 15,
                      -(((-scaled) + 16384) >> 15))
    return np.clip(values, -128, 127).astype(np.int8)


def load_manifest(path: Path):
    rows = []
    with path.open(newline="", encoding="utf-8") as source:
        for row in csv.DictReader(source):
            tokens = row["tokens"].split()
            if not tokens or any(token not in TOKEN_IDS or token == "<blank>" for token in tokens):
                raise ValueError(f"invalid token sequence: {row['tokens']}")
            audio = Path(row["path"])
            if not audio.is_absolute():
                audio = path.parent / audio
            rows.append((audio, row["split"].lower(), [TOKEN_IDS[token] for token in tokens]))
    if not rows:
        raise ValueError("manifest is empty")
    return rows


def feature_statistics(rows):
    count = 0
    total = 0
    total_squared = 0
    for path, split, _ in rows:
        if split != "train":
            continue
        features = raw_features(read_wave(path)).astype(np.int64)
        count += features.size
        total += int(features.sum())
        total_squared += int((features * features).sum())
    if not count:
        raise ValueError("manifest has no training rows")
    mean = total / count
    variance = max(1.0, total_squared / count - mean * mean)
    offset_q8 = int(round(mean))
    scale_q15 = int(round((24.0 / math.sqrt(variance)) * 32768.0))
    if not (1 <= scale_q15 <= 2**31 - 1):
        raise ValueError("feature normalization scale is out of range")
    return offset_q8, scale_q15


class CommandDataset(Dataset):
    def __init__(self, rows, split, offset_q8, scale_q15):
        selected = [row for row in rows if row[1] == split]
        self.items = []
        for path, _, tokens in selected:
            features = normalize(raw_features(read_wave(path)), offset_q8,
                                 scale_q15)
            self.items.append((
                torch.from_numpy(features.astype(np.float32)),
                torch.tensor(tokens, dtype=torch.long),
            ))
        print(f"dataset_cached split={split} utterances={len(self.items)}")

    def __len__(self):
        return len(self.items)

    def __getitem__(self, index):
        return self.items[index]


def collate(batch):
    feature_lengths = torch.tensor([len(item[0]) for item in batch], dtype=torch.long)
    target_lengths = torch.tensor([len(item[1]) for item in batch], dtype=torch.long)
    maximum = int(feature_lengths.max())
    features = torch.zeros((len(batch), maximum, 20), dtype=torch.float32)
    targets = []
    for index, (item_features, item_targets) in enumerate(batch):
        features[index, :len(item_features)] = item_features
        targets.append(item_targets)
    return features, feature_lengths, torch.cat(targets), target_lengths


class TdnnCtc(nn.Module):
    def __init__(self, hidden1=64, hidden2=64):
        super().__init__()
        self.fc1 = nn.Linear(20 * CONTEXT_FRAMES, hidden1)
        self.fc2 = nn.Linear(hidden1, hidden2)
        self.fc3 = nn.Linear(hidden2, len(TOKENS))
        with torch.no_grad():
            self.fc3.bias.zero_()
            self.fc3.bias[0] = 2.0

    def forward(self, features):
        radius = CONTEXT_FRAMES // 2
        padded = F.pad(features.transpose(1, 2), (radius, radius), mode="replicate").transpose(1, 2)
        context = torch.cat([padded[:, offset:offset + features.shape[1], :]
                             for offset in range(CONTEXT_FRAMES)], dim=2)
        hidden = torch.clamp(F.relu(self.fc1(context)), 0, 127)
        hidden = torch.clamp(F.relu(self.fc2(hidden)), 0, 127)
        logits = torch.clamp(self.fc3(hidden), -128, 127)
        return logits[:, ::FRAME_STRIDE, :]


def greedy_decode(logits, length):
    previous = None
    output = []
    for token in logits[:length].argmax(dim=-1).tolist():
        if token and token != previous:
            output.append(token)
        previous = token
    return output


def evaluate(model, loader, device):
    model.eval()
    correct = total = 0
    with torch.no_grad():
        for features, lengths, targets, target_lengths in loader:
            logits = model(features.to(device)).cpu()
            target_offset = 0
            for index, target_length in enumerate(target_lengths.tolist()):
                expected = targets[target_offset:target_offset + target_length].tolist()
                target_offset += target_length
                output_length = (int(lengths[index]) + FRAME_STRIDE - 1) // FRAME_STRIDE
                correct += greedy_decode(logits[index], output_length) == expected
                total += 1
    return correct / total if total else 0.0


def quantize_layer(layer):
    weights = layer.weight.detach().cpu().numpy()
    maximum = float(np.max(np.abs(weights)))
    shift = 0 if maximum == 0 else max(0, min(30, int(math.floor(math.log2(127.0 / maximum)))))
    quantized_weights = np.clip(np.rint(weights * (2**shift)), -128, 127).astype(np.int8)
    quantized_bias = np.rint(layer.bias.detach().cpu().numpy() * (2**shift)).astype("<i4")
    return quantized_weights, quantized_bias, shift


def requantize(values, shift, relu):
    values = values.astype(np.int64)
    if shift:
        mask = (1 << shift) - 1
        values = np.where(values >= 0, values >> shift,
                          -(((-values) + mask) >> shift))
    if relu:
        values = np.maximum(values, 0)
    return np.clip(values, -128, 127).astype(np.int8)


def quantized_decode(features, layers):
    radius = CONTEXT_FRAMES // 2
    padded = np.pad(features, ((radius, radius), (0, 0)), mode="edge")
    context = np.concatenate([padded[offset:offset + len(features)]
                              for offset in range(CONTEXT_FRAMES)], axis=1).astype(np.int64)
    weight1, bias1, shift1 = layers[0]
    hidden1 = requantize(context @ weight1.astype(np.int64).T + bias1, shift1, True)
    weight2, bias2, shift2 = layers[1]
    hidden2 = requantize(hidden1.astype(np.int64) @ weight2.astype(np.int64).T + bias2,
                         shift2, True)
    weight3, bias3, shift3 = layers[2]
    logits = requantize(hidden2.astype(np.int64) @ weight3.astype(np.int64).T + bias3,
                        shift3, False)[::FRAME_STRIDE]
    previous = None
    output = []
    for token in logits.argmax(axis=1).tolist():
        if token and token != previous:
            output.append(token)
        previous = token
    return output


def evaluate_quantized(model, dataset):
    layers = [quantize_layer(model.fc1), quantize_layer(model.fc2),
              quantize_layer(model.fc3)]
    correct = 0
    for index in range(len(dataset)):
        features, target = dataset[index]
        correct += quantized_decode(features.numpy().astype(np.int8), layers) == target.tolist()
    return correct / len(dataset) if len(dataset) else 0.0


def export_model(model, output: Path, offset_q8: int, scale_q15: int):
    layers = [quantize_layer(model.fc1), quantize_layer(model.fc2), quantize_layer(model.fc3)]
    payload = b"".join(weight.tobytes(order="C") + bias.tobytes(order="C")
                       for weight, bias, _ in layers)
    header = bytearray(HEADER_BYTES)
    header[:4] = b"XQV1"
    values = [1, HEADER_BYTES, HEADER_BYTES + len(payload), zlib.crc32(payload) & 0xFFFFFFFF,
              16000, 20, CONTEXT_FRAMES, model.fc1.out_features, model.fc2.out_features,
              len(TOKENS), offset_q8 & 0xFFFFFFFF, scale_q15 & 0xFFFFFFFF,
              layers[0][2], layers[1][2], layers[2][2], FRAME_STRIDE]
    for index, value in enumerate(values):
        struct.pack_into("<I", header, 4 + index * 4, value)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_bytes(header + payload)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("manifest", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--epochs", type=int, default=30)
    parser.add_argument("--batch-size", type=int, default=32)
    parser.add_argument("--learning-rate", type=float, default=1e-3)
    parser.add_argument("--weight-decay", type=float, default=1e-5)
    parser.add_argument("--seed", type=int, default=1)
    parser.add_argument("--min-validation-accuracy", type=float, default=0.90)
    parser.add_argument("--min-test-accuracy", type=float, default=0.90)
    parser.add_argument("--hidden1", type=int, default=64)
    parser.add_argument("--hidden2", type=int, default=64)
    args = parser.parse_args()

    random.seed(args.seed)
    np.random.seed(args.seed)
    torch.manual_seed(args.seed)
    rows = load_manifest(args.manifest)
    offset_q8, scale_q15 = feature_statistics(rows)
    train = CommandDataset(rows, "train", offset_q8, scale_q15)
    validation = CommandDataset(rows, "validation", offset_q8, scale_q15)
    test = CommandDataset(rows, "test", offset_q8, scale_q15)
    if not train or not validation or not test:
        raise SystemExit("manifest requires train, validation, and test splits")
    if not (1 <= args.hidden1 <= 256 and 1 <= args.hidden2 <= 256):
        raise SystemExit("hidden dimensions must be in 1..256")
    train_loader = DataLoader(train, batch_size=args.batch_size, shuffle=True, collate_fn=collate)
    train_eval_loader = DataLoader(train, batch_size=args.batch_size, collate_fn=collate)
    validation_loader = DataLoader(validation, batch_size=args.batch_size, collate_fn=collate)
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    model = TdnnCtc(args.hidden1, args.hidden2).to(device)
    optimizer = torch.optim.Adam(model.parameters(), lr=args.learning_rate,
                                 weight_decay=args.weight_decay)
    milestones = sorted({max(1, args.epochs // 2), max(2, args.epochs * 3 // 4)})
    scheduler = torch.optim.lr_scheduler.MultiStepLR(
        optimizer, milestones=milestones, gamma=0.3
    )
    loss_function = nn.CTCLoss(blank=0, zero_infinity=True)
    best_accuracy = -1.0
    best_epoch = 0
    best_state = None

    for epoch in range(args.epochs):
        model.train()
        total_loss = 0.0
        for features, lengths, targets, target_lengths in train_loader:
            optimizer.zero_grad()
            logits = model(features.to(device))
            output_lengths = (lengths + FRAME_STRIDE - 1) // FRAME_STRIDE
            loss = loss_function(F.log_softmax(logits, dim=-1).transpose(0, 1),
                                 targets.to(device), output_lengths, target_lengths)
            loss.backward()
            optimizer.step()
            total_loss += float(loss.detach())
        accuracy = evaluate(model, validation_loader, device)
        train_accuracy = evaluate(model, train_eval_loader, device) \
            if (epoch + 1) % 5 == 0 or epoch + 1 == args.epochs else -1.0
        if accuracy > best_accuracy:
            best_accuracy = accuracy
            best_epoch = epoch + 1
            best_state = {
                name: value.detach().cpu().clone()
                for name, value in model.state_dict().items()
            }
        print(f"epoch={epoch + 1} loss={total_loss / len(train_loader):.6f} "
              f"train_exact={train_accuracy:.4f} validation_exact={accuracy:.4f} "
              f"lr={optimizer.param_groups[0]['lr']:.7f}")
        scheduler.step()

    if best_state is None:
        raise SystemExit("training produced no checkpoint")
    model.load_state_dict(best_state)
    model = model.cpu()
    accuracy = evaluate(model, validation_loader, torch.device("cpu"))
    quantized_accuracy = evaluate_quantized(model, validation)
    test_loader = DataLoader(test, batch_size=args.batch_size, collate_fn=collate)
    test_accuracy = evaluate(model, test_loader, torch.device("cpu"))
    quantized_test_accuracy = evaluate_quantized(model, test)
    if min(accuracy, quantized_accuracy) < args.min_validation_accuracy:
        raise SystemExit(f"validation accuracy float={accuracy:.4f} "
                         f"int8={quantized_accuracy:.4f} is below acceptance "
                         f"{args.min_validation_accuracy:.4f}")
    if min(test_accuracy, quantized_test_accuracy) < args.min_test_accuracy:
        raise SystemExit(f"test accuracy float={test_accuracy:.4f} "
                         f"int8={quantized_test_accuracy:.4f} is below acceptance "
                         f"{args.min_test_accuracy:.4f}")
    export_model(model, args.output, offset_q8, scale_q15)
    model_sha256 = hashlib.sha256(args.output.read_bytes()).hexdigest()
    manifest_sha256 = hashlib.sha256(args.manifest.read_bytes()).hexdigest()
    print(f"XQVOICE_MODEL_EXPORTED path={args.output} bytes={args.output.stat().st_size} "
          f"validation_exact={accuracy:.4f} int8_exact={quantized_accuracy:.4f} "
          f"test_exact={test_accuracy:.4f} int8_test_exact={quantized_test_accuracy:.4f} "
          f"best_epoch={best_epoch} "
          f"offset_q8={offset_q8} scale_q15={scale_q15} "
          f"model_sha256={model_sha256} manifest_sha256={manifest_sha256}")


if __name__ == "__main__":
    main()
