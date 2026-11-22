"""Synthetic independently specified linguistic stress cases, NOT patient ground truth."""
from pathlib import Path
import json
import pandas as pd

CASES = [
 ('direct','We provide {s} treatment at this hospital.',3),
 ('unit','A dedicated {s} unit is available at our hospital.',3),
 ('referral','Patients are referred elsewhere for {s}.',0),
 ('awareness','A {s} awareness camp was held at our hospital.',0),
 ('planned','A new {s} unit is planned for next year.',0),
 ('negative','{s} is not available at this hospital.',0),
 ('historical','This hospital formerly offered {s}.',0),
 ('counselling','Patients receive counselling about {s}.',0),
 ('unrelated_negation','No parking is available. Our hospital provides {s}.',3),
 ('training','Our director trained in {s} at another institution.',0),
 ('equipment','Equipment relevant to {s} is listed.',1),
 ('split','Our hospital provides {s}; {s} has been suspended.',0),
]
SERVICES=[('dialysis','Dialysis'),('mri','MRI'),('nicu','NICU'),('cardiac-surgery','cardiac surgery'),('burns','burn care')]

def build(out):
 out=Path(out);out.mkdir(parents=True,exist_ok=True)
 fac=[];ev=[];queries=[];qrels=[]
 for split,lat in [('dev',20.),('test',25.)]:
  for service,label in SERVICES:
   qid=f'{split}-{service}';queries.append(dict(query_id=qid,service=service,latitude=lat,longitude=80.,split=split,group_id=f'{split}-{service}'))
   for i,(kind,template,grade) in enumerate(CASES):
    uid=f'{split}-{service}-{kind}'
    fac.append(dict(unique_id=uid,name=uid,best_lat=lat+(i+1)*.001,best_lon=80.,location_tier='point_verified'))
    ev.append(dict(unique_id=uid,field='equipment' if kind=='equipment' else 'procedure',item_idx=0,text=template.format(s=label)))
    qrels.append(dict(query_id=qid,unique_id=uid,relevance=grade))
 for name,data in [('facilities',fac),('evidence',ev),('queries',queries),('qrels',qrels)]:
  pd.DataFrame(data).to_csv(out/f'{name}.csv',index=False)
 (out/'PROVENANCE.json').write_text(json.dumps({'kind':'synthetic','warning':'Dev/test share linguistic templates; a regression challenge, not generalization evidence. Do not tune production weights using these results.'},indent=2))

if __name__=='__main__':build(Path(__file__).parent)
