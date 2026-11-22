"""Serial OFFLINE ablation of the real web-serving recommender, never an API endpoint.

Mutates config only inside scoped contexts; run in a separate notebook/process from API.
Use independently labelled, grouped dev/test queries. No automatic deployment.
"""
from __future__ import annotations
import argparse
import hashlib
import importlib.metadata
import platform
import json
from pathlib import Path
import sys
import time
from unittest.mock import patch

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import config
from cross_encoder import CrossEncoderScorer
from data_store import get_snapshot
from recommender import Recommender
from experiments.benchmark import validate_queries, paired_interval
from experiments.evaluation import evaluate
from experiments.io import read_frame, dump_json


# Text weight of the previous cross-encoder serving policy (4:3 text:proof). The live default
# (config.RERANK_WEIGHTS) has since moved to 0.25, so the baseline pins the old value explicitly.
PREVIOUS_TEXT_WEIGHT = 4 / 7


def plans():
    """Baseline is the previous serving policy (cross-encoder, no guard, 4:3 weights), not experimental-engine rules."""
    baseline = dict(method='cross_encoder', model=config.CROSS_ENCODER_MODEL, guard='off',
                    text_weight=PREVIOUS_TEXT_WEIGHT, travel_multiplier=1.)
    variants = [('baseline', baseline)]
    for guard in ['off', 'explicit', 'strict']:
        for method in ['rules', 'cross_encoder']:
            weights = [0.] if method == 'rules' else [.25, PREVIOUS_TEXT_WEIGHT, .75]
            for w in weights:
                for scale in [.5, 1., 2.]:
                    cfg = dict(method=method, model=config.CROSS_ENCODER_MODEL, guard=guard,
                               text_weight=w, travel_multiplier=scale)
                    if cfg != baseline:
                        variants.append((f's{len(variants):03d}', cfg))
    return variants


def benchmark_serving(snapshot, queries, qrels, out, variants=None, scorer=None, data_kind='real'):
    validate_queries(queries)
    out = Path(out)
    if out.exists() and any(out.iterdir()):
        raise ValueError('Use a new private output directory')
    out.mkdir(parents=True, exist_ok=True)
    queries = queries.copy(); queries['query_id'] = queries.query_id.astype(str)
    dev = queries[queries.split.eq('dev')]; test = queries[queries.split.eq('test')]
    variants = plans() if variants is None else variants
    if not variants or variants[0][0] != 'baseline' or len({v[0] for v in variants}) != len(variants):
        raise ValueError('Variants need a unique baseline as the first entry')
    base_travel = dict(config.TRAVEL_KM_BY_TAG); base_default = config.TRAVEL_KM_DEFAULT
    recs = {}; scorers = {}; attempts = []; summaries = []; parts = []
    labels = qrels if qrels is not None else pd.DataFrame(columns=['query_id','unique_id','relevance'])

    def run(name, cfg, subset):
        if cfg['method'] not in recs:
            recs[cfg['method']] = Recommender(snapshot, ranking_method=cfg['method'])
        rec = recs[cfg['method']]
        if cfg['method'] == 'cross_encoder':
            if cfg['model'] not in scorers:
                scorers[cfg['model']] = scorer or CrossEncoderScorer(cfg['model'])
                scorers[cfg['model']].warmup()  # startup/model load excluded from query timing
            rec.scorer = scorers[cfg['model']]
        scale = cfg['travel_multiplier']
        settings = dict(CLAIM_GUARD_POLICY=cfg['guard'],
                        RERANK_WEIGHTS={'text':cfg['text_weight'],'proof':1-cfg['text_weight']},
                        TRAVEL_KM_DEFAULT=base_default*scale,
                        TRAVEL_KM_BY_TAG={k:v*scale for k,v in base_travel.items()})
        runs=[]; raw=[]
        with patch.multiple(config, **settings):
            for q in subset.to_dict('records'):
                response = rec.recommend(q['service'], '',
                    {'latitude':float(q['latitude']), 'longitude':float(q['longitude'])})
                raw.append({'query_id':q['query_id'], 'response':response})
                runs.append(dict(query_id=q['query_id'], method=name,
                    service_id=response['queryContext']['service']['canonicalId'],
                    results=[dict(unique_id=r['id'], distance_km=r['distanceKm']) for r in response['results']],
                    candidate_ids=[], latency_ms=response['metadata']['executionTimeMs']))
        per, summary = evaluate(runs, labels, 3)
        # API exposes count, not all candidate IDs. Never misreport top-8 recall as retrieval recall.
        per['candidate_recall_pool'] = np.nan
        per['candidate_count'] = [r['response']['metadata']['totalCandidates'] for r in raw]
        summary['candidate_recall_pool'] = np.nan; summary['candidate_recall_pool_n'] = 0
        per = per.merge(subset[['query_id','group_id','split']], on='query_id', validate='many_to_one')
        summary['fully_judged_dev'] = bool(per.judged_query.eq(1).all() and per.judged_result_fraction.fillna(1).eq(1).all())
        return per, summary, raw

    for name, cfg in variants:
        started=time.perf_counter()
        try:
            per, sm, _ = run(name,cfg,dev)
            parts.append(per); summaries.append(sm)
            attempts.append(dict(id=name, config=cfg, status='success', seconds=time.perf_counter()-started))
        except Exception as exc:
            attempts.append(dict(id=name, config=cfg, status='failed', error=f'{type(exc).__name__}: {exc}'))
        dump_json(out/'attempts.json',attempts)
    summary = pd.concat(summaries,ignore_index=True) if summaries else pd.DataFrame()
    per = pd.concat(parts,ignore_index=True) if parts else pd.DataFrame()
    summary.to_csv(out/'dev_summary.csv',index=False); per.to_csv(out/'dev_per_query.csv',index=False)
    winner=None
    if not summary.empty:
        judged = summary[summary.fully_judged_dev & summary.ndcg_at_k_pool.notna()]
        if not judged.empty:
            winner=judged.sort_values(['ndcg_at_k_pool','precision_at_k','method'],ascending=[False,False,True]).iloc[0]['method']
    configs=dict(variants)
    manifest=dict(data_kind=data_kind, engine='actual backend.recommender.Recommender',
        baseline='baseline', winner=winner, configs=configs,
        selection='Fully judged dev only: nDCG@3, then P@3, then stable ID. Test only after selection.',
        limitations=['No automatic production promotion.', 'No candidate recall: API exposes only total count.',
                     'Travel scale changes both distance decay AND adaptive candidate radius.',
                     'Warmup excluded; pair cache shared, cold misses included. Latency is descriptive only.',
                     'Synthetic cases are regression diagnostics, not real-data accuracy.'],
        data_hash=hashlib.sha256(''.join(df.to_json() for df in [snapshot.tags,snapshot.index,snapshot.facilities,snapshot.pins]).encode()).hexdigest(),
        query_hash=hashlib.sha256(queries.to_csv(index=False).encode()).hexdigest(),
        qrels_hash=hashlib.sha256(labels.to_csv(index=False).encode()).hexdigest(),
        source_hash=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        source_hashes={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in
                       [Path(__file__),Path(__file__).with_name('recommender.py'),Path(__file__).with_name('config.py'),
                        Path(__file__).with_name('evidence_support.py')]},
        runtime={'python':platform.python_version(),'packages':{}})
    for package in ['numpy','pandas','torch','transformers','sentence-transformers']:
        try: manifest['runtime']['packages'][package]=importlib.metadata.version(package)
        except importlib.metadata.PackageNotFoundError: manifest['runtime']['packages'][package]=None
    if winner is not None and 'baseline' in set(summary.method):
        test_parts=[]
        for name in dict.fromkeys(['baseline',winner]):
            pq,sm,raw=run(name,configs[name],test);test_parts.append(pq)
            sm.to_csv(out/f'test_summary_{name}.csv',index=False)
            dump_json(out/f'test_responses_{name}.json',raw)
        combined=pd.concat(test_parts,ignore_index=True)
        combined.to_csv(out/'test_per_query.csv',index=False)
        manifest['held_out_comparison']=paired_interval(combined,'baseline',winner)
    dump_json(out/'manifest.json',manifest)
    return manifest


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--queries',required=True);parser.add_argument('--qrels',required=True)
    parser.add_argument('--out',required=True)
    parser.add_argument('--synthetic-challenge',action='store_true',help='Generated regression fixtures, not real data')
    args=parser.parse_args()
    if args.synthetic_challenge:
        from experiments.challenge.serving import snapshot
        snap=snapshot()
    else:
        snap=get_snapshot()
    benchmark_serving(snap,read_frame(args.queries),read_frame(args.qrels),args.out,
                      data_kind='synthetic' if args.synthetic_challenge else 'real')

if __name__=='__main__':main()
