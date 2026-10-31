#!/usr/bin/env python3
"""Train/export the CPU single-token Mandarin Xiangqi classifier."""

import argparse
import hashlib
import random
import struct
import zlib
from pathlib import Path

import numpy as np
import torch
from torch import nn
from torch.utils.data import DataLoader, Dataset

from train_tdnn_ctc import (
    HEADER_BYTES,
    TOKENS,
    feature_statistics,
    load_manifest,
    normalize,
    quantize_layer,
    raw_features,
    read_wave,
    requantize,
)


INPUTS = 40
CLASSES = len(TOKENS)


def pooled_features(path: Path, offset_q8: int, scale_q15: int) -> np.ndarray:
    features = normalize(raw_features(read_wave(path)), offset_q8, scale_q15)
    sums = features.astype(np.int64).sum(axis=0)
    count = len(features)
    means = np.where(sums >= 0, sums // count, -((-sums) // count))
    maximums = features.max(axis=0).astype(np.int64)
    return np.concatenate((means, maximums)).astype(np.int8)


class TokenDataset(Dataset):
    def __init__(self, rows, split, offset_q8, scale_q15):
        self.items = []
        for path, row_split, tokens in rows:
            if row_split != split:
                continue
            if len(tokens) != 1 or tokens[0] == 0:
                raise ValueError(f"{path}: token classifier requires exactly one non-blank token")
            self.items.append((
                torch.from_numpy(
                    pooled_features(path, offset_q8, scale_q15).astype(np.float32)
                ),
                tokens[0],
            ))
        print(f"token_dataset_cached split={split} utterances={len(self.items)}")

    def __len__(self):
        return len(self.items)

    def __getitem__(self, index):
        return self.items[index]


class TokenMlp(nn.Module):
    def __init__(self, hidden1=64, hidden2=64):
        super().__init__()
        self.fc1 = nn.Linear(INPUTS, hidden1)
        self.fc2 = nn.Linear(hidden1, hidden2)
        self.fc3 = nn.Linear(hidden2, CLASSES)

    def forward(self, values):
        values = torch.clamp(torch.relu(self.fc1(values)), 0, 127)
        values = torch.clamp(torch.relu(self.fc2(values)), 0, 127)
        return torch.clamp(self.fc3(values), -128, 127)


def evaluate(model, loader, device):
    model.eval()
    correct = total = 0
    with torch.no_grad():
        for values, targets in loader:
            predictions = model(values.to(device)).argmax(dim=1).cpu()
            correct += int((predictions == targets).sum())
            total += len(targets)
    return correct / total if total else 0.0


def quantized_predict(values, layers):
    weight1, bias1, shift1 = layers[0]
    hidden1 = requantize(values.astype(np.int64) @ weight1.astype(np.int64).T + bias1,
                         shift1, True)
    weight2, bias2, shift2 = layers[1]
    hidden2 = requantize(hidden1.astype(np.int64) @ weight2.astype(np.int64).T + bias2,
                         shift2, True)
    weight3, bias3, shift3 = layers[2]
    logits = requantize(hidden2.astype(np.int64) @ weight3.astype(np.int64).T + bias3,
                        shift3, False)
    return int(logits.argmax())


def evaluate_quantized(model, dataset):
    layers = [quantize_layer(model.fc1), quantize_layer(model.fc2),
              quantize_layer(model.fc3)]
    correct = 0
    for values, target in dataset.items:
        correct += quantized_predict(values.numpy().astype(np.int8), layers) == target
    return correct / len(dataset) if len(dataset) else 0.0


def export_model(model, output: Path, offset_q8: int, scale_q15: int):
    layers = [quantize_layer(model.fc1), quantize_layer(model.fc2),
              quantize_layer(model.fc3)]
    payload = b"".join(weight.tobytes(order="C") + bias.tobytes(order="C")
                       for weight, bias, _ in layers)
    header = bytearray(HEADER_BYTES)
    header[:4] = b"XQT1"
    values = [
        1, HEADER_BYTES, HEADER_BYTES + len(payload),
        zlib.crc32(payload) & 0xFFFFFFFF, 16000, 20, 2,
        model.fc1.out_features, model.fc2.out_features, CLASSES,
        offset_q8 & 0xFFFFFFFF, scale_q15 & 0xFFFFFFFF,
        layers[0][2], layers[1][2], layers[2][2], 1,
    ]
    for index, value in enumerate(values):
        struct.pack_into("<I", header, 4 + index * 4, value)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_bytes(header + payload)


def dataset_sha256(manifest: Path, rows) -> str:
    digest = hashlib.sha256()
    digest.update(manifest.read_bytes())
    for path, split, tokens in sorted(rows, key=lambda item: str(item[0])):
        digest.update(split.encode("ascii"))
        digest.update(bytes(tokens))
        digest.update(path.read_bytes())
    return digest.hexdigest()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("manifest", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--epochs", type=int, default=80)
    parser.add_argument("--batch-size", type=int, default=32)
    parser.add_argument("--learning-rate", type=float, default=1e-3)
    parser.add_argument("--weight-decay", type=float, default=1e-5)
    parser.add_argument("--seed", type=int, default=1)
    parser.add_argument("--hidden1", type=int, default=64)
    parser.add_argument("--hidden2", type=int, default=64)
    parser.add_argument("--min-validation-accuracy", type=float, default=0.95)
    parser.add_argument("--min-test-accuracy", type=float, default=0.95)
    args = parser.parse_args()

    random.seed(args.seed)
    np.random.seed(args.seed)
    torch.manual_seed(args.seed)
    rows = load_manifest(args.manifest)
    offset_q8, scale_q15 = feature_statistics(rows)
    train = TokenDataset(rows, "train", offset_q8, scale_q15)
    validation = TokenDataset(rows, "validation", offset_q8, scale_q15)
    test = TokenDataset(rows, "test", offset_q8, scale_q15)
    if not train or not validation or not test:
        raise SystemExit("manifest requires train, validation, and test splits")
    if not (1 <= args.hidden1 <= 256 and 1 <= args.hidden2 <= 256):
        raise SystemExit("hidden dimensions must be in 1..256")
    train_loader = DataLoader(train, batch_size=args.batch_size, shuffle=True)
    validation_loader = DataLoader(validation, batch_size=args.batch_size)
    test_loader = DataLoader(test, batch_size=args.batch_size)
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    model = TokenMlp(args.hidden1, args.hidden2).to(device)
    optimizer = torch.optim.Adam(model.parameters(), lr=args.learning_rate,
                                 weight_decay=args.weight_decay)
    scheduler = torch.optim.lr_scheduler.MultiStepLR(
        optimizer, milestones=[args.epochs // 2, args.epochs * 3 // 4], gamma=0.3
    )
    loss_function = nn.CrossEntropyLoss()
    best_accuracy = -1.0
    best_epoch = 0
    best_state = None
    for epoch in range(args.epochs):
        model.train()
        total_loss = 0.0
        for values, targets in train_loader:
            optimizer.zero_grad()
            loss = loss_function(model(values.to(device)), targets.to(device))
            loss.backward()
            optimizer.step()
            total_loss += float(loss.detach())
        accuracy = evaluate(model, validation_loader, device)
        if accuracy > best_accuracy:
            best_accuracy = accuracy
            best_epoch = epoch + 1
            best_state = {
                name: value.detach().cpu().clone()
                for name, value in model.state_dict().items()
            }
        scheduler.step()
        print(f"epoch={epoch + 1} loss={total_loss / len(train_loader):.6f} "
              f"validation_exact={accuracy:.4f} lr={optimizer.param_groups[0]['lr']:.7f}")
    model.load_state_dict(best_state)
    model = model.cpu()
    validation_accuracy = evaluate(model, validation_loader, torch.device("cpu"))
    quantized_validation = evaluate_quantized(model, validation)
    test_accuracy = evaluate(model, test_loader, torch.device("cpu"))
    quantized_test = evaluate_quantized(model, test)
    if min(validation_accuracy, quantized_validation) < args.min_validation_accuracy:
        raise SystemExit(f"validation accuracy float={validation_accuracy:.4f} "
                         f"int8={quantized_validation:.4f} is below acceptance "
                         f"{args.min_validation_accuracy:.4f}")
    if min(test_accuracy, quantized_test) < args.min_test_accuracy:
        raise SystemExit(f"test accuracy float={test_accuracy:.4f} "
                         f"int8={quantized_test:.4f} is below acceptance "
                         f"{args.min_test_accuracy:.4f}")
    export_model(model, args.output, offset_q8, scale_q15)
    model_hash = hashlib.sha256(args.output.read_bytes()).hexdigest()
    data_hash = dataset_sha256(args.manifest, rows)
    print(f"XQVOICE_TOKEN_MODEL_EXPORTED path={args.output} "
          f"bytes={args.output.stat().st_size} best_epoch={best_epoch} "
          f"validation_exact={validation_accuracy:.4f} "
          f"int8_validation_exact={quantized_validation:.4f} "
          f"test_exact={test_accuracy:.4f} int8_test_exact={quantized_test:.4f} "
          f"model_sha256={model_hash} dataset_sha256={data_hash}")


if __name__ == "__main__":
    main()
