"""Rebuild fixed-setting comparison tables/figure from recorded CSVs, not new model runs."""
from pathlib import Path
import json
import pandas as pd

ROOT=Path(__file__).parent

def comparison():
    m=json.loads((ROOT/'manifest.json').read_text());df=pd.read_csv(ROOT/'dev_summary.csv')
    rows=[]
    for name,cfg in m['configs'].items():
        if cfg['aggregation']!='max' or cfg['distance_decay_km']!=15 or cfg['text_weight']!=(0 if cfg['method']=='rules' else .5):continue
        r=df[df.method.eq(name)].iloc[0]
        rows.append(dict(variant=name,method=cfg['method'],model=cfg['model'],guard=cfg['guard'],
                         precision_at_3=r.precision_at_k,ndcg_at_3=r.ndcg_at_k_pool))
    result=pd.DataFrame(rows);result.to_csv(ROOT/'fixed_comparison.csv',index=False)
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    plt.rcParams['svg.fonttype']='none'
    fig,ax=plt.subplots(figsize=(9,4.5))
    plain=result[~result.guard]; guarded=result[result.guard]
    x=list(range(len(plain)))
    ax.bar([i-.18 for i in x],plain.precision_at_3,width=.36,label='Existing experimental gate')
    ax.bar([i+.18 for i in x],guarded.precision_at_3,width=.36,label='Stricter linguistic guard')
    ax.set_xticks(x,['Rules','TF-IDF','BM25','Bi-encoder','CE MiniLM','CE TinyBERT'])
    ax.set_ylim(0,1.08);ax.set_ylabel('P@3 on 5 synthetic dev queries')
    ax.set_title('Synthetic regression challenge — not real-facility accuracy')
    ax.legend(loc='lower right');fig.tight_layout();fig.savefig(ROOT/'comparison.svg');plt.close(fig)
    svg=ROOT/'comparison.svg'
    svg.write_text('\n'.join(line.rstrip() for line in svg.read_text().splitlines())+'\n')
    m=json.loads((ROOT/'serving'/'manifest.json').read_text());df=pd.read_csv(ROOT/'serving'/'dev_summary.csv')
    rows=[]
    for name,cfg in m['configs'].items():
        target=0 if cfg['method']=='rules' else 4/7
        if cfg['text_weight']!=target or cfg['travel_multiplier']!=1:continue
        r=df[df.method.eq(name)].iloc[0]
        rows.append(dict(variant=name,method=cfg['method'],guard=cfg['guard'],precision_at_3=r.precision_at_k,ndcg_at_3=r.ndcg_at_k_pool))
    pd.DataFrame(rows).to_csv(ROOT/'serving'/'fixed_comparison.csv',index=False)
    print(result.to_string(index=False));print(pd.DataFrame(rows).to_string(index=False))

if __name__=='__main__':comparison()
