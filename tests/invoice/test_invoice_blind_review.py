"""Synthetic checks: quotas, masked packets and no label/holdout reads."""

import importlib.util
import json
import sys
import zipfile
from collections import Counter
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
SEED = "12" * 32


def load_api():
    path = ROOT / "ml/scripts/preparar_revisao_cega_invoice.py"
    assert path.exists(), "Preparador cego ainda não implementado"
    spec = importlib.util.spec_from_file_location("blind_test_api", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def api():
    return load_api()


def cohort():
    n = 10000
    frame = pd.DataFrame({"invoice_id": [f"private-invoice-{i:05}" for i in range(n)],
                          "invoice_amount": np.arange(n, 0, -1, dtype=float)})
    order = np.r_[np.arange(50, n), np.arange(50)]
    scores = np.empty(n)
    scores[order] = np.arange(n, 0, -1)
    return frame, scores


def test_exact_quotas_membership_and_no_implicit_expansion():
    api = load_api()
    frame, scores = cohort()
    members, pools = api.draw_sample(frame, scores, SEED)
    assert len(members) == 300
    assert len({(r['budget'], r['group'], r['invoice_id']) for r in members}) == 300
    assert set(Counter((r['budget'], r['group']) for r in members).values()) == {25}
    expected = {1: [50, 50, 50, 9850], 5: [450, 50, 50, 9450], 10: [950, 50, 50, 8950]}
    assert {b: [p['population'] for p in pools if p['budget'] == b] for b in expected} == expected
    for r in members:
        i = int(r['invoice_id'].split('-')[-1])
        k = r['budget'] * 100
        actual = 'common' if 50 <= i < k else 'if_only' if k <= i < k + 50 else 'value_only' if i < 50 else 'neither'
        assert r['group'] == actual
    assert len({r['invoice_id'] for r in members}) < 300


def test_reproducible_under_reordering_and_label_changes(api):
    frame, scores = cohort()
    expected = api.draw_sample(frame, scores, SEED)
    assert api.draw_sample(frame.iloc[::-1].assign(is_fraud=1, fraud_type='SECRET'), scores[::-1], SEED) == expected
    assert api.draw_sample(frame, scores, "34" * 32) != expected


@pytest.mark.parametrize('fault', ['too_small', 'duplicate', 'nan', 'length', 'seed'])
def test_bad_sampling_fails_without_adapting_quota(api, fault):
    frame, scores = cohort()
    seed = SEED
    if fault == 'too_small':
        frame, scores = frame.iloc[:100], scores[:100]
    elif fault == 'duplicate':
        frame.loc[1, 'invoice_id'] = frame.loc[0, 'invoice_id']
    elif fault == 'nan':
        scores[0] = np.nan
    elif fault == 'length':
        scores = scores[:4]
    else:
        seed = 'not-a-seed'
    with pytest.raises(ValueError):
        api.draw_sample(frame, scores, seed)


def context(frame):
    return frame.assign(supplier_id='private-supplier', department_id='private-department',
                        invoice_date=pd.Timestamp('2023-09-20'), currency='ZAR',
                        invoice_type='GOODS', payment_terms='NET30', submission_hour=10,
                        amount_vs_supplier_mean=1.5, amount_vs_department_mean=2.,
                        supplier_frequency=100., supplier_department_frequency=5.,
                        is_fraud='SECRET_LABEL', fraud_type='SECRET_TYPE',
                        image_path='SECRET_IMAGE', anomaly_score='SECRET_SCORE')


def test_packets_dedup_independent_aliases_orders_no_secrets(api):
    frame, scores = cohort()
    members, _ = api.draw_sample(frame, scores, SEED)
    packets, maps = api.make_packets(context(frame), members, SEED, 'Neutral guide')
    ids = {m['invoice_id'] for m in members}
    assert set(packets) == {'avaliador_01', 'avaliador_02'}
    sequences = []
    for reviewer, files in packets.items():
        assert set(files) == {'LEIA_PRIMEIRO.md', 'FICHAS.md', 'DECLARACAO.md'}
        text = '\n'.join(files.values())
        assert not any(secret in text for secret in ('SECRET_', 'private-', 'if_only', 'value_only', SEED, 'is_fraud', 'fraud_type'))
        assert {r['invoice_id'] for r in maps[reviewer]} == ids
        assert len(maps[reviewer]) == len(ids)
        assert files['FICHAS.md'].count('## Caso ') == len(ids)
        assert files['FICHAS.md'].count('- Relevância: \n') == len(ids)
        assert files['FICHAS.md'].count('- Motivo concreto: \n') == len(ids)
        sequences.append([r['invoice_id'] for r in maps[reviewer]])
    assert sequences[0] != sequences[1]
    assert not ({r['case_id'] for r in maps['avaliador_01']} & {r['case_id'] for r in maps['avaliador_02']})


def test_monetary_cents_preserved_in_reviewer_context(api):
    frame, _ = cohort()
    data = context(frame.iloc[:1]).copy()
    data.loc[data.index[0], 'invoice_amount'] = 216481.17
    members = [{'budget': 1, 'group': 'common', 'invoice_id': data['invoice_id'].iloc[0]}]
    packets, _ = api.make_packets(data, members, SEED, 'Neutral guide')
    for files in packets.values():
        assert '| Valor | 216481.17 |' in files['FICHAS.md']


@pytest.fixture
def source(api, tmp_path, monkeypatch):
    frame, scores = cohort()
    val = pd.DataFrame(1., index=range(len(frame)), columns=api.triage.FEATURES)
    val['invoice_amount'] = frame['invoice_amount']
    val.insert(0, 'split', 'val')
    val.insert(0, 'invoice_id', frame['invoice_id'])
    for folder in ('data/processed', 'data/raw', 'ml/models', 'ml/experiments'):
        (tmp_path / folder).mkdir(parents=True)
    val.assign(is_fraud='DO_NOT_READ', fraud_type='DO_NOT_READ').to_parquet(tmp_path / api.triage.PRESERVED_INPUTS[1], index=False)
    train = pd.DataFrame({'invoice_id': ['training-only'], 'split': ['train']})
    train.to_parquet(tmp_path / api.triage.PRESERVED_INPUTS[0], index=False)
    pd.concat([val[['invoice_id', 'split']], train,
               pd.DataFrame({'invoice_id': ['closed'], 'split': ['test']})]).to_parquet(tmp_path / 'data/raw/splits.parquet', index=False)
    raw = context(frame)[api.RAW_COLUMNS]
    pd.concat([raw.iloc[::-1], raw.iloc[:1].assign(invoice_id='closed', invoice_amount=np.inf)]).to_parquet(tmp_path / 'data/raw/invoices.parquet', index=False)
    for path in api.triage.PRESERVED_INPUTS[2:]:
        (tmp_path / path).write_text('synthetic placeholder', encoding='utf-8')
    ranks = {}
    for name, values in (('isolation_forest', scores), ('invoice_value', frame['invoice_amount'])):
        order = frame.assign(v=values).sort_values(['v', 'invoice_id'], ascending=[False, True])
        ranks[name] = {'budgets': [{'percent': p, 'k': p * 100,
                                   'selected_ids_sha256': api.triage._fingerprint(order.iloc[:p*100]['invoice_id'].tolist())} for p in (1,5,10)]}
    reference = {**ranks, 'split': 'val', 'test_used': False, 'budget_percentages': [1,5,10],
                 'validation_ids_sha256': api.triage._fingerprint(frame['invoice_id'].tolist()),
                 'input_hashes_sha256': {p: api.triage.sha256(tmp_path/p) for p in api.triage.PRESERVED_INPUTS},
                 'parameters': {}, 'legacy_offset': -.5}
    (tmp_path / api.COMPARISON).write_text(json.dumps(reference), encoding='utf-8')
    class ExistingModel:
        def score_samples(self, x):
            assert list(x.columns) == api.triage.FEATURES
            assert len(x) == 10000
            assert (tmp_path / api.OUTPUT / 'coordinator/freeze.json').exists()
            return -scores
    monkeypatch.setattr(api.triage, '_load_model', lambda *args: ExistingModel())
    return tmp_path


def test_run_projects_no_labels_no_test_freezes_before_scoring_and_exclusive(api, source, monkeypatch):
    original = pd.read_parquet
    def guarded(path, **kwargs):
        name = Path(path).name
        assert 'test' not in name.lower() and name != 'labels.parquet'
        assert 'columns' in kwargs
        assert not {'is_fraud', 'fraud_type', 'image_path'} & set(kwargs['columns'])
        if name == 'invoices.parquet':
            assert kwargs['filters'][0][:2] == ('invoice_id', 'in')
            assert 'closed' not in kwargs['filters'][0][2]
        elif name == 'splits.parquet':
            assert kwargs['filters'] == [('split', 'in', ['train', 'val'])]
        return original(path, **kwargs)
    monkeypatch.setattr(pd, 'read_parquet', guarded)
    result = api.run(source, seed=SEED)
    out = source / api.OUTPUT
    assert result['state'] == 'awaiting_two_independent_reviews'
    assert result['responses_frozen'] is False and result['labels_revealed'] is False
    assert result['memberships'] == 300 and 0 < result['unique_invoices'] < 300
    assert not (out / 'PREPARATION_INCOMPLETE').exists()
    for name in ('avaliador_01', 'avaliador_02'):
        with zipfile.ZipFile(out / f'{name}.zip') as z:
            assert set(z.namelist()) == {'LEIA_PRIMEIRO.md', 'FICHAS.md', 'DECLARACAO.md'}
            assert b'DO_NOT_READ' not in z.read('FICHAS.md')
    before = api.triage.sha256(out / 'coordinator/manifest.json')
    with pytest.raises(FileExistsError):
        api.run(source, seed=SEED)
    assert before == api.triage.sha256(out / 'coordinator/manifest.json')


@pytest.mark.parametrize('split', ['train', 'test', '../test'])
def test_reject_other_splits_before_io(api, tmp_path, split):
    with pytest.raises(ValueError):
        api.run(tmp_path, split=split)


def test_changed_selection_blocks_delivery(api, source):
    path = source / api.COMPARISON
    evidence = json.loads(path.read_text(encoding='utf-8'))
    evidence['isolation_forest']['budgets'][0]['selected_ids_sha256'] = '0' * 64
    path.write_text(json.dumps(evidence), encoding='utf-8')
    with pytest.raises(ValueError):
        api.run(source, seed=SEED)
    assert not (source / api.OUTPUT / 'avaliador_01.zip').exists()
    assert (source / api.OUTPUT / 'PREPARATION_INCOMPLETE').exists()
