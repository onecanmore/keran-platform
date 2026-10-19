#!/usr/bin/env python
"""Actual simultaneous transactions against an isolated file database (never preview data)."""
import os,tempfile,sys,json,threading
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
root=Path(__file__).resolve().parent.parent;sys.path.insert(0,str(root))
with tempfile.TemporaryDirectory(prefix='keran-concurrency-') as tmp:
    os.environ['DATA_DIR']=tmp;os.environ['DJANGO_SETTINGS_MODULE']='config.settings'
    import django;django.setup()
    from django.core.management import call_command
    from django.db import close_old_connections
    from django.contrib.auth.models import User
    from core.models import Product,Lot,Setting,Order
    from core.services import quote,create_order,DomainError
    call_command('migrate',verbosity=0)
    p=Product.objects.create(name='Last item concurrency fixture',slug='last-item',status='published',price_cents=1000,fulfiller='Test',kind='physical')
    lot=Lot.objects.create(product=p,batch='one',purpose='sale',on_hand=1)
    Setting.objects.create(key='shipping',value={'zips':[],'pickup_cents':0,'delivery_cents':None})
    users=[User.objects.create(username='buyer-'+str(i)) for i in range(2)]
    data={'items':[{'product_id':str(p.pk),'quantity':1}],'zip':'10001','method':'pickup'}
    data['fingerprint']=quote(users[0],data)['fingerprint']
    barrier=threading.Barrier(2)
    def buy(i):
        close_old_connections();barrier.wait()
        try:
            o=create_order(User.objects.get(pk=users[i].pk),dict(data),'concurrency-'+str(i));result={'buyer':i,'result':'reserved','order':str(o.pk)}
        except DomainError as e:result={'buyer':i,'result':'rejected','code':e.code}
        finally:close_old_connections()
        return result
    with ThreadPoolExecutor(max_workers=2) as pool:results=list(pool.map(buy,range(2)))
    lot.refresh_from_db()
    assert sum(r['result']=='reserved' for r in results)==1,results
    assert sum(r['result']=='rejected' for r in results)==1,results
    assert lot.reserved==1 and lot.available==0 and Order.objects.count()==1
    result={'passed':True,'results':results,'on_hand':lot.on_hand,'reserved':lot.reserved,'available':lot.available,'database':'isolated SQLite file, two simultaneous connections'}
    from django.utils import timezone
    from datetime import timedelta
    from core.models import Campaign,Donation,Receipt,FinanceEntry
    from core.services import submit_campaign,campaign_action,donation_checkout,process_event,campaign_totals
    editor=User.objects.create(username='campaign-editor',is_superuser=True)
    reviewer=User.objects.create(username='campaign-reviewer',is_superuser=True)
    campaign=Campaign.objects.create(name='Parallel fundraising fixture',slug='parallel-campaign',summary='Test',target_cents=10000,starts_at=timezone.now()-timedelta(days=1),ends_at=timezone.now()+timedelta(days=1),owner=editor,budget=[{'name':'Test','amount_cents':10000}],beneficiaries='Test',execution='Test',consent_basis='No stories',policy='Test flexible, overfund, cancellation, refund and remaining-funds policy')
    submit_campaign(editor,campaign);campaign_action(reviewer,campaign,'approve');campaign.refresh_from_db();campaign_action(editor,campaign,'publish');campaign.refresh_from_db()
    donations=[]
    for i in range(2):
        d,_=donation_checkout(users[i],{'campaign_id':str(campaign.pk),'amount_cents':6000,'email':'test@example.invalid','receipt_name':'Test','policy_consent':True,'policy_version':campaign.version},'donation-'+str(i));donations.append(d)
    barrier=threading.Barrier(2)
    def pay(i):
        close_old_connections();barrier.wait()
        try:process_event({'event_id':'parallel-'+str(i),'purpose':'public_donation','reference':str(donations[i].pk),'kind':'succeeded','amount_cents':6000})
        finally:close_old_connections()
        return 'confirmed'
    with ThreadPoolExecutor(max_workers=2) as pool:payment_results=list(pool.map(pay,range(2)))
    totals=campaign_totals(campaign)
    assert totals['confirmed']==12000 and totals['percent']==120 and totals['bar']==100
    assert Receipt.objects.count()==2 and FinanceEntry.objects.filter(bucket='public_donation',kind='payment').count()==2
    result['simultaneous_donations']={'results':payment_results,'confirmed_cents':totals['confirmed'],'actual_percent':totals['percent'],'visual_percent':totals['bar'],'receipts':Receipt.objects.count()}
    (root/'artifacts').mkdir(exist_ok=True);(root/'artifacts/concurrency.json').write_text(json.dumps(result,indent=2))
    print(json.dumps(result,indent=2))
