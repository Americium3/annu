"""Reproducible dev/test search. Never selects a winner from unlabelled queries.

python -m experiments.benchmark --help
"""
from __future__ import annotations
import argparse
from dataclasses import asdict, replace
import hashlib
import importlib.metadata
import platform
import os
import itertools
import json
from pathlib import Path
import time
import traceback

import numpy as np
import pandas as pd

from backend.evidence_support import claim_status
from .engine import ExperimentEngine, Settings, canonical_service, catalog
from .evaluation import evaluate
from .io import read_frame, load_tables, augment_facility_text, dump_json


class GuardedEngine(ExperimentEngine):
    def __init__(self, *args, guard=False, aggregation='max', **kwargs):
        self.guard, self.aggregation = guard, aggregation
        super().__init__(*args, **kwargs)

    def candidates(self, service):
        frame = super().candidates(service)
        if self.guard and not frame.empty:
            import re
            pattern = re.compile('|'.join(catalog()[canonical_service(service)]['patterns']), re.I)
            for i, row in frame.iterrows():
                if row['status'] == 'text_supported':
                    state = claim_status(row['text'], canonical_service(service), pattern)
                    if state not in {'support', 'unreviewed'}:
                        frame.at[i,'status'] = 'related' if state in {'indirect','uncertain'} else state
        return frame

    def score_service(self, service, method):
        frame = super().score_service(service, method)
        if self.aggregation == 'top2_mean' and not frame.empty:
            for _, group in frame[frame.status.eq('text_supported')].groupby('unique_id'):
                score = group.text_score.nlargest(2).mean()
                frame.loc[group.index,'text_score'] = score
        return frame


def validate_queries(queries):
    needed = {'query_id','service','latitude','longitude','split','group_id'}
    if not needed.issubset(queries):
        raise ValueError('Queries need '+','.join(sorted(needed)))
    if queries.query_id.astype(str).duplicated().any() or queries[list(needed)].isna().any().any():
        raise ValueError('Query IDs must be unique; required values cannot be null')
    if queries.group_id.astype(str).str.strip().eq('').any() or not set(queries.split).issubset({'dev','test'}):
        raise ValueError('Use nonempty group_id and dev/test split')
    if queries.groupby('group_id').split.nunique().gt(1).any():
        raise ValueError('A location/query group may not cross dev/test')
    if set(queries.split) != {'dev','test'}:
        raise ValueError('Both dev and untouched test queries are required')


def paired_interval(per_query, baseline, challenger, seed=42, draws=2000):
    """Paired cluster bootstrap; CI is descriptive for the supplied judged pool."""
    a = per_query[per_query.method.eq(baseline)].set_index('query_id')
    b = per_query[per_query.method.eq(challenger)].set_index('query_id')
    paired = a[['ndcg_at_k_pool','group_id']].join(b[['ndcg_at_k_pool']],rsuffix='_new').dropna()
    if paired.empty:
        return {'paired_queries':0,'delta':None,'ci95':None}
    paired['delta'] = paired.ndcg_at_k_pool_new-paired.ndcg_at_k_pool
    groups = [g.delta.to_numpy() for _,g in paired.groupby('group_id')]
    if len(groups)<2:
        return {'paired_queries':len(paired),'groups':len(groups),'delta':float(paired.delta.mean()),'ci95':None}
    rng = np.random.default_rng(seed)
    deltas=[float(np.concatenate([groups[i] for i in rng.integers(0,len(groups),len(groups))]).mean()) for _ in range(draws)]
    return {'paired_queries':len(paired),'groups':len(groups),'delta':float(paired.delta.mean()),
            'ci95':list(map(float,np.quantile(deltas,[.025,.975])))}


def benchmark(facilities, evidence, queries, qrels, out, methods=('rules','tfidf','bm25'),
              cross_models=('cross-encoder/ms-marco-MiniLM-L6-v2',), data_kind='real', seed=42):
    validate_queries(queries)
    out=Path(out)
    if out.exists() and any(out.iterdir()):
        raise ValueError('Use a new output directory')
    out.mkdir(parents=True,exist_ok=True)
    queries=queries.copy(); queries['query_id']=queries.query_id.astype(str)
    dev, test = queries[queries.split.eq('dev')],queries[queries.split.eq('test')]
    attempts=[]; summaries=[]; details=[]; configs={}; engines={}; shared_models={}
    empty_labels=pd.DataFrame(columns=['query_id','unique_id','relevance'])
    qrels=empty_labels if qrels is None else qrels.copy()
    # Fixed radius/candidate budget across all variants; tune only text/distance mixture.
    plans=[]
    for method in methods:
        checkpoints=cross_models if method=='cross_encoder' else ('none',)
        for checkpoint, guard, aggregation in itertools.product(checkpoints,[False,True],['max','top2_mean']):
            # No-text baseline plus three text weights and two decay scales.
            weights=[0.] if method=='rules' else [.25,.5,.75]
            for weight, decay in itertools.product(weights,[15.,60.]):
                plans.append(dict(method=method,model=checkpoint,guard=guard,aggregation=aggregation,
                                  text_weight=weight,distance_decay_km=decay))
    def run(config, subset, run_id):
        key=(config['guard'],config['aggregation'],config['model'])
        if key not in engines:
            settings=Settings(cross_model=config['model'] if config['model']!='none' else Settings().cross_model)
            engines[key]=GuardedEngine(facilities,evidence,settings,guard=config['guard'],aggregation=config['aggregation'])
            engines[key]._models=shared_models.setdefault(config['model'],{})
        engine=engines[key]
        engine.settings=replace(engine.settings,text_weight=config['text_weight'],evidence_weight=0.,
                                distance_weight=1-config['text_weight'],distance_decay_km=config['distance_decay_km'])
        started=time.perf_counter()
        for service in sorted(set(subset.service)):
            engine.score_service(service,config['method'])
        precompute=time.perf_counter()-started
        runs=[]
        for q in subset.to_dict('records'):
            r=engine.recommend(q['service'],float(q['latitude']),float(q['longitude']),config['method'])
            r['query_id']=str(q['query_id']);r['method']=run_id
            runs.append(r)
        per,summary=evaluate(runs,qrels,engine.settings.top_k)
        summary['precompute_seconds']=precompute
        per=per.merge(subset[['query_id','group_id','split']],on='query_id',validate='many_to_one')
        return per,summary,runs
    failed=set()
    for i,config in enumerate(plans):
        run_id=f'v{i:03d}';configs[run_id]=config;start=time.perf_counter()
        model_key=(config['method'],config['model'])
        if model_key in failed:
            attempts.append({'id':run_id,'config':config,'status':'skipped_after_model_failure'})
            dump_json(out/'attempts.json',attempts)
            continue
        try:
            per,summary,_=run(config,dev,run_id)
            # Only compare configurations on identical, completely judged dev queries.
            complete=bool(per.judged_result_fraction.fillna(1).eq(1).all() and per.judged_query.eq(1).all())
            summary['fully_judged_dev']=complete
            summaries.append(summary);details.append(per)
            attempt={'id':run_id,'config':config,'status':'success','seconds':time.perf_counter()-start}
        except Exception as exc:
            failed.add(model_key)
            attempt={'id':run_id,'config':config,'status':'failed','error':type(exc).__name__+': '+str(exc)}
        attempts.append(attempt)
        dump_json(out/'attempts.json',attempts)  # checkpoint after every attempted run
    summary=pd.concat(summaries,ignore_index=True) if summaries else pd.DataFrame()
    per_dev=pd.concat(details,ignore_index=True) if details else pd.DataFrame()
    summary.to_csv(out/'dev_summary.csv',index=False);per_dev.to_csv(out/'dev_per_query.csv',index=False)
    winner=None
    if not summary.empty:
        eligible=summary[summary.fully_judged_dev & summary.ndcg_at_k_pool.notna()]
        if not eligible.empty:
            winner=eligible.sort_values(['ndcg_at_k_pool','precision_at_k','method'],ascending=[False,False,True]).iloc[0]['method']
    report={'data_kind':data_kind,'winner':winner,'selection':'dev nDCG then P@3; fully judged dev only',
            'git_independent_data_hash':hashlib.sha256((facilities.to_json()+evidence.to_json()).encode()).hexdigest(),
            'query_hash':hashlib.sha256(queries.to_csv(index=False).encode()).hexdigest(),
            'qrels_hash':hashlib.sha256(qrels.to_csv(index=False).encode()).hexdigest(),'seed':seed,
            'warning':'Synthetic challenge results do not establish accuracy on real facilities.' if data_kind=='synthetic' else
                      'Correctness is relative to supplied independent qrels. No label generation from this model.',
            'latency_scope':'warm queries; precompute recorded separately; caches shared within a checkpoint',
            'configs':configs,'baseline':'v000','promotion':'No automatic production promotion; review held-out errors and labels.'}
    if winner is not None and 'v000' in set(summary.method):
        frozen=[('v000',configs['v000'])]
        if winner!='v000': frozen.append((winner,configs[winner]))
        test_parts=[]
        for name,cfg in frozen:
            per,sm,runs=run(cfg,test,name);test_parts.append(per)
            sm.to_csv(out/f'test_summary_{name}.csv',index=False)
            # Keep complete scored/rejected evidence for error review; private output only.
            dump_json(out/f'test_runs_{name}.json',runs)
        combined=pd.concat(test_parts,ignore_index=True)
        combined.to_csv(out/'test_per_query.csv',index=False)
        report['held_out_comparison']=paired_interval(combined,'v000',winner,seed)
        report['best_config']=configs[winner]
    report['runtime']={'python':platform.python_version(),'packages':{},
                       'threads':{k:os.environ.get(k) for k in ['OMP_NUM_THREADS','MKL_NUM_THREADS']}}
    for package in ['numpy','pandas','scikit-learn','torch','transformers','sentence-transformers']:
        try: report['runtime']['packages'][package]=importlib.metadata.version(package)
        except importlib.metadata.PackageNotFoundError: report['runtime']['packages'][package]=None
    report['source_hash']=hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    root=Path(__file__).resolve().parents[1]
    report['source_hashes']={str(p.relative_to(root)):hashlib.sha256(p.read_bytes()).hexdigest() for p in
        [Path(__file__).resolve(),root/'backend/evidence_support.py',root/'backend/cross_encoder.py',
         root/'experiments/engine.py',root/'experiments/evaluation.py',root/'pipeline/tag_dictionary.py']}
    report['model_revisions']={}
    try:
        from huggingface_hub import try_to_load_from_cache
        names=set(cross_models)|{Settings().bi_model}
        for name in names:
            cached=try_to_load_from_cache(name,'config.json')
            if isinstance(cached,str):
                parts=Path(cached).parts;idx=parts.index('snapshots')
                report['model_revisions'][name]=parts[idx+1]
    except (ImportError,ValueError): pass
    dump_json(out/'manifest.json',report)
    md=['# Benchmark result',f"Data kind: **{data_kind}**",report['warning'],
        f"Successful configurations: {len(summary)} / {len(plans)}",f"Dev-selected variant: {winner or 'none: labels missing/incomplete'}",
        'No production winner is asserted from synthetic tests or unjudged data.']
    if not summary.empty:
        md+=['','```',summary[['method','precision_at_k','ndcg_at_k_pool','answered']].to_string(index=False),'```']
    (out/'REPORT.md').write_text('\n\n'.join(md))
    return report


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--facilities');p.add_argument('--evidence');p.add_argument('--from-databricks',action='store_true')
    p.add_argument('--schema',default='workspace.cardinal_virtues');p.add_argument('--queries',required=True)
    p.add_argument('--qrels');p.add_argument('--out',required=True)
    p.add_argument('--methods',nargs='+',default=['rules','tfidf','bm25'],choices=['rules','tfidf','bm25','bi_encoder','cross_encoder'])
    p.add_argument('--cross-models',nargs='+',default=['cross-encoder/ms-marco-MiniLM-L6-v2'])
    p.add_argument('--data-kind',choices=['real','synthetic'],default='real')
    args=p.parse_args()
    if args.from_databricks: fac,ev=load_tables(args.schema)
    elif args.facilities and args.evidence: fac,ev=read_frame(args.facilities),read_frame(args.evidence)
    else:p.error('Supply local exports or --from-databricks')
    benchmark(fac,augment_facility_text(fac,ev),read_frame(args.queries),read_frame(args.qrels) if args.qrels else None,
              args.out,args.methods,args.cross_models,args.data_kind)

if __name__=='__main__': main()
