"""Audit real text EXCERPTS already in the repo; buckets are NOT independent labels.

The saved report says it derives from model_evidence_items. It supplies no facility IDs,
locations, full evidence or clinical verification. Never call retention an accuracy metric.
"""
import argparse
import hashlib
import json
from pathlib import Path
import pandas as pd
from backend.evidence_support import claim_status
from .engine import catalog
from .io import dump_json

SERVICES={'kidney-dialysis','mri','nicu','c-section','cardiac-surgery','burns'}

def audit(source,out,neural=False):
    source=Path(source);out=Path(out)
    if out.exists() and any(out.iterdir()):raise ValueError('Use a NEW output directory')
    out.mkdir(parents=True,exist_ok=True)
    saved=json.loads(source.read_text());rows=[]
    scorer=None
    if neural:
        from backend.cross_encoder import CrossEncoderScorer
        scorer=CrossEncoderScorer()
    for tag in saved['tags']:
        service=tag['id']
        if service not in SERVICES:continue
        spec=catalog()[service]
        query=' '.join(dict.fromkeys([spec['label'],*spec['synonyms']]))
        examples=[(bucket,e) for bucket,items in tag['examples'].items() for e in items]
        scores=scorer.score(query,[e['text'] for _,e in examples]) if scorer else [None]*len(examples)
        for (bucket,e),score in zip(examples,scores):
            old=claim_status(e['text'],service,recognize_referral_centers=False)
            new=claim_status(e['text'],service)
            rows.append(dict(service=service,source_bucket=bucket,text=e['text'],
                upstream_model_probability=e['probability'],old_guard_status=old,new_guard_status=new,
                strict_kept_before=old in {'support','unreviewed'},strict_kept_after=new in {'support','unreviewed'},
                explicit_kept_after=new not in {'negative','planned_or_historical','conflict'},
                cross_encoder_relevance=score))
    df=pd.DataFrame(rows);df.to_csv(out/'excerpt_audit.csv',index=False)
    df.groupby(['service','source_bucket']).agg(examples=('text','size'),
        strict_kept_before=('strict_kept_before','sum'),strict_kept_after=('strict_kept_after','sum'),
        explicit_kept_after=('explicit_kept_after','sum')).to_csv(out/'retention_counts.csv')
    dump_json(out/'manifest.json',dict(kind='repository-derived real text excerpts; NOT facility evaluation',
        rows=len(df),source=str(source),source_metadata=saved['meta'],
        source_hash=hashlib.sha256(source.read_bytes()).hexdigest(),
        audit_code_hash=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        guard_source_hash=hashlib.sha256(Path(__file__).resolve().parents[1].joinpath('backend/evidence_support.py').read_bytes()).hexdigest(),
        neural=bool(scorer),scorer=scorer.info() if scorer else None,
        limitations=['Source buckets/probabilities are previous model outputs, not ground truth.',
            'Only displayed examples; selected sample, not representative.',
            'Missing facility identity, coordinates, full source and independent service labels.',
            'Before/after isolates referral-center wording; retention is not accuracy.']))
    return df

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--source',default='data/tags/tfidf_tag_report.json');p.add_argument('--out',required=True)
    p.add_argument('--neural',action='store_true');args=p.parse_args()
    print(audit(args.source,args.out,args.neural).groupby('source_bucket')[['strict_kept_before','strict_kept_after']].sum().to_string())
