"""Demonstrate topic relevance vs. an actual provision claim using the real checkpoint.

This is a linguistic diagnostic, NOT a real-facility accuracy measurement.
"""
import argparse
from backend.cross_encoder import CrossEncoderScorer
from .io import dump_json


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--model',default='cross-encoder/ms-marco-MiniLM-L6-v2')
    p.add_argument('--out',required=True)
    args=p.parse_args()
    texts=['Our hospital provides haemodialysis treatment.',
           'Patients are referred elsewhere for dialysis.']
    model=CrossEncoderScorer(args.model)
    scores=model.score('Dialysis',texts)
    result=dict(kind='synthetic linguistic diagnostic',query='Dialysis',model=model.info(),
        pairs=[dict(text=t,score=s) for t,s in zip(texts,scores)],
        warning='Relevance scores are not probabilities of current service availability.')
    dump_json(args.out,result)

if __name__=='__main__':main()
