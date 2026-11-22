"""Adapt GENERATED challenge records to the actual backend contract, not real hospitals.

Deliberately labels all matched claims formal/usable, simulating erroneous upstream
extraction. Tests whether a serving guard can stop such claims before reranking.
"""
from pathlib import Path
import json
import pandas as pd
from experiments.engine import canonical_service,catalog


def snapshot():
    from data_store import Snapshot  # caller adds backend/ to sys.path, as the web process does
    root=Path(__file__).parent
    fac=pd.read_csv(root/'facilities.csv');ev=pd.read_csv(root/'evidence.csv')
    queries=pd.read_csv(root/'queries.csv')
    records=[];index=[];tags=[]
    services={canonical_service(s) for s in queries.service}
    for service in sorted(services):
        spec=catalog()[service]
        tags.append(dict(tag_id=service,label=spec['label'],kind='service',group_name='Synthetic challenge',
                         synonyms=spec['synonyms'],facility_count=24))
    service_by_id={row.unique_id:canonical_service(row.service) for row in
        pd.read_csv(root/'qrels.csv').merge(queries[['query_id','service']],on='query_id').itertuples()}
    for r in fac.to_dict('records'):
        uid=r['unique_id'];e=ev[ev.unique_id.eq(uid)].iloc[0];equipment=e.field=='equipment'
        records.append(dict(unique_id=uid,name=r['name'],loc_lat=r['best_lat'],loc_lon=r['best_lon'],
            latitude=r['best_lat'],longitude=r['best_lon'],location_tier='point_verified',location_check='SYNTHETIC',
            city_raw='Synthetic',address_city='Synthetic',district='Synthetic',state='Synthetic',pincode='',
            facility_category='hospital',operator_category='unknown',contact_phone=None,contact_website=None,
            source_urls=[],n_source_urls=0,n_beds=None,n_doctors=None,year_est=None,
            n_explicit_elsewhere=0,same_name_city_records=1,capability_maybe_truncated=False,
            procedure_maybe_truncated=False,recency_of_page_update=''))
        index.append(dict(unique_id=uid,tag_id=service_by_id[uid],eligibility='formal',reason_codes=[],
            evidence_tier=3 if equipment else 1,n_explicit_usable=0 if equipment else 1,n_explicit_elsewhere=0,
            n_time_bound=0,n_equipment_usable=int(equipment),n_explicit_fields=int(not equipment),n_cited=0,
            only_equipment=equipment,lists_emergency_24x7=False,
            evidence=[dict(field=e.field,pos=0,text=e.text,evidence_status='usable')]))
    pins=pd.DataFrame([dict(pincode='000000',lat=20.,lon=80.,is_precise=True,states=['Synthetic'],districts=['Synthetic'])])
    return Snapshot(pd.DataFrame(tags),pd.DataFrame(index),pd.DataFrame(records),pins,'synthetic','GENERATED CHALLENGE')
