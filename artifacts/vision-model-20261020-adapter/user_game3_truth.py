"""Versioned scoring-only label ruling; never edit training deliveries."""
import copy
import hashlib
import json
from pathlib import Path

POLICY = 'user-original-game3-20261020'
HERE = Path(__file__).resolve().parent
FEN = dict(zip(('red_shuai', 'red_shi', 'red_xiang', 'red_ma', 'red_ju',
                'red_pao', 'red_bing', 'black_jiang', 'black_shi', 'black_xiang',
                'black_ma', 'black_ju', 'black_pao', 'black_zu'), 'KABNRCPkabnrcp'))


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def save(path, value):
    with path.open('x', encoding='utf-8') as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2, allow_nan=False)
        stream.write('\n')


def placement(protocol, geometry, pieces):
    import numpy as np
    centers = np.array([[p['cx'], p['cy']] for p in pieces], dtype=float)
    grid, residual, okay = protocol.assign_grid(geometry, centers)
    cells, dropped = {}, []
    for piece, (col, row), good, distance in zip(pieces, grid, okay, residual):
        if good:
            cells.setdefault((int(col), int(row)), piece['label'])
        else:
            dropped.append(dict(label=piece['label'], grid=[int(col), int(row)],
                                residual=round(float(distance), 4)))
    black = [r for (c, r), label in cells.items() if label.startswith('black')]
    red = [r for (c, r), label in cells.items() if label.startswith('red')]
    top_black = bool(np.mean(black) < np.mean(red)) if black and red else True
    ranks = []
    for row in (range(10) if top_black else range(9, -1, -1)):
        text, empty = '', 0
        for col in range(9):
            label = cells.get((col, row))
            if label is None:
                empty += 1
            else:
                text += (str(empty) if empty else '') + FEN[label]
                empty = 0
        ranks.append(text + (str(empty) if empty else ''))
    return dict(fen_board='/'.join(ranks), n_pieces=len(cells),
                n_dropped_off_grid=len(dropped), dropped=dropped,
                top_is_black=top_black), cells


def prepare(protocol, dataset, board_dir, output):
    original = json.loads((HERE / 'dataset_corrections.json').read_text(encoding='utf-8'))
    truth = json.loads((HERE / 'fen_gt.json').read_text(encoding='utf-8'))
    assert len(original['corrections']) == 81 and len(truth) == 1042
    withdrawn = [c for c in original['corrections'] if c['game'] == 3 and c['type']=='class_fixed']
    retained = [c for c in original['corrections'] if c not in withdrawn]
    assert len(withdrawn) == 77 and len(retained) == 4
    assert all(908 <= int(c['frame'][3:]) <= 1042 for c in withdrawn)
    corrected = protocol.load_corrections(HERE / 'dataset_corrections.json')
    retained_by_frame = {}
    for correction in retained:
        retained_by_frame.setdefault(correction['frame'], []).append(correction)
    assert [c['frame'] for c in retained if c['game']==3] == ['IMG00920']
    revised, retained_truth, audit = copy.deepcopy(truth), copy.deepcopy(truth), []
    for index in range(908, 1043):
        stem = f'IMG{index:05d}'
        geometry = protocol.geometry_from_corners(protocol.board_quad(board_dir, index), confidence=1.0)
        raw = protocol.load_gt_piece_labels(dataset / 'out', index)
        previous, previous_cells = placement(protocol, geometry,
            protocol.apply_grid_corrections(corrected, stem, geometry, copy.deepcopy(raw)))
        # Bind regeneration to the frozen historical FEN before changing policy.
        assert previous == truth[stem], ('historical truth mismatch', stem)
        fresh, cells = placement(protocol, geometry, raw)
        retained_frame, _ = placement(protocol, geometry,
            protocol.apply_grid_corrections(retained_by_frame, stem, geometry, copy.deepcopy(raw)))
        if index == 908:
            assert cells[(8, 3)] == 'red_bing', 'user ruling must match original label'
        revised[stem] = fresh
        retained_truth[stem] = retained_frame
        audit.append(dict(frame=stem, original_label_sha256=digest(dataset/'out'/(stem+'.json')),
                          board_label_sha256=digest(board_dir/(stem+'.json')),
                          historical_fen=previous['fen_board'], original_label_fen=fresh['fen_board'],
                          changed=previous['fen_board'] != fresh['fen_board'],
                          changed_cells=sum(previous_cells.get(k)!=cells.get(k) for k in set(previous_cells)|set(cells)),
                          retained_missing_fen=retained_frame['fen_board']))
    changed = [entry['frame'] for entry in audit if entry['changed']]
    assert set(changed) == {c['frame'] for c in withdrawn} | {'IMG00920'}
    assert sum(entry['changed_cells'] for entry in audit)==78
    assert sum(retained_truth[k]['fen_board']!=truth[k]['fen_board'] for k in truth)==77
    assert all(revised[key] == value for key, value in truth.items() if int(key[3:]) < 908)
    output.mkdir(parents=True, exist_ok=False)
    save(output/'dataset_corrections.json', dict(schema_version=1, label_policy=POLICY,
        authority='User: (8,3) is a pawn; withdraw all 77 game-3 corrections; score original labels',
        scoring_note='Primary score uses raw game-3 labels with no overlays; missing-piece entry is not withdrawn and is reported separately',
        corrections=[], retained_nonwithdrawn_corrections=retained, withdrawn_corrections=withdrawn))
    save(output/'retained_corrections.json', dict(schema_version=1, corrections=retained))
    save(output/'fen_gt.json', revised)
    save(output/'fen_gt_retained_missing.json', retained_truth)
    save(output/'game3_truth_audit.json', audit)
    manifest = dict(schema_version=1, label_policy=POLICY, authority='explicit user ruling 2026-10-20',
        source_corrections_sha256=digest(HERE/'dataset_corrections.json'),
        source_fen_sha256=digest(HERE/'fen_gt.json'), withdrawn_game3_corrections=77,
        retained_nonwithdrawn_corrections=4, retained_game3_missing_piece_corrections=1,
        applied_test_game_corrections=0, supplemental_score_applies_retained_missing_piece=True,
        fen_records=1042, regenerated_game3_records=135, changed_game3_fens=len(changed),
        changed_game3_cells=78,
        original_training_files_modified=False, independent_test=False,
        files={name: digest(output/name) for name in ('dataset_corrections.json', 'retained_corrections.json',
            'fen_gt.json', 'fen_gt_retained_missing.json', 'game3_truth_audit.json')})
    save(output/'manifest.json', manifest)
    corrections = protocol.load_corrections(output/'dataset_corrections.json')
    assert all(f'IMG{index:05d}' not in corrections for index in range(908, 1043))
    return corrections, revised, manifest
