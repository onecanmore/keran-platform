from datetime import timedelta
from django.core.management.base import BaseCommand,CommandError
from django.contrib.auth.models import Group,User
from django.conf import settings
from django.utils import timezone
from core.models import *
from core.services import campaign_action,submit_campaign
class Command(BaseCommand):
    help='Create non-public, unconfirmed product drafts. --demo only in an isolated demo DATA_DIR.'
    def add_arguments(self,p):p.add_argument('--demo',action='store_true')
    def handle(self,*args,**opts):
        for name in ['admin','reviewer','caseworker','warehouse','finance','merchant']:Group.objects.get_or_create(name=name)
        defaults={'brand':{'name':'KERAN COMMONS','name_zh':'KERAN 共益生活'},'service_states':['NY','NJ'],'shipping':{'zips':[],'pickup_cents':0,'delivery_cents':None},'water_zips':[],'product_requirements':{'local-pear-juice':['packaging','shelf_life','storage','supplier','labeling'],'korean-water-purifier':['brand','authorization','contract','installation','aftercare'],'korean-red-ginseng':['classification','labeling','supplier'],'omg-capsules':['english_name','packaging','labeling','supplier'],'heated-mat':['intended_use','electrical_safety','condition'],'pet-cabinet':['dimensions','condition','assembly','delivery'],'mobility-scooter':['model','inspection','battery','handover'],'glasses-pouch':['name_and_use','quantity','dimensions','condition']},'verification_days':None,'retention_days':None,'reservation_minutes':15,'sandbox_tax_bps':0,'policies':{'status':'draft','legal_review_required':True},'fundraising_legal':{'verified':False,'legal_name':'','tax_deductibility_confirmed':False,'allowed_regions':[]}}
        for k,v in defaults.items():Setting.objects.get_or_create(key=k,defaults={'value':v})
        items=[('local-pear-juice','Local pear juice','本地梨汁','physical','food','Specifications, shelf life, storage, price and delivery pending.'),('korean-water-purifier','Korean water purifier','韓國淨水器','service_booking','water','Brand, authorization, contract, installation and aftercare pending.'),('korean-red-ginseng','Korean red ginseng','韓國紅參','physical','food','Classification, labeling and supplier pending.'),('omg-capsules','OMG capsules','OMG 膠囊','physical','food','English name, packaging and purpose pending. Do not assume Omega-3.'),('heated-mat','Heatable mat','可加熱毛墊子','physical','home','Human or pet use, electrical safety and condition pending.'),('pet-cabinet','Pet cabinet','豪華寵物櫃子','physical','home','Dimensions, condition, assembly and delivery pending.'),('mobility-scooter','Four-wheel mobility scooter','四輪電動代步車','application_only','mobility','5 units reported; pending count, model, inspection, battery and handover checks. Available stock: 0.'),('glasses-pouch','Portable glasses pouch','便攜眼鏡袋','physical','home','Name, use, dimensions, quantity and condition pending.')]
        for slug,name,zh,kind,cat,desc in items:
            Product.objects.get_or_create(slug=slug,defaults={'name':name,'name_zh':zh,'kind':kind,'category':cat,'description':desc,'status':'draft','source':'donated_inventory' if slug in ['mobility-scooter','heated-mat','pet-cabinet'] else 'merchant_supply'})
        scooter=Product.objects.get(slug='mobility-scooter')
        for n in range(1,6):Asset.objects.get_or_create(serial=f'PENDING-COUNT-{n:03}',defaults={'product':scooter})
        if opts['demo']:
            if 'demo' not in str(settings.DATA_DIR).lower():raise CommandError('--demo requires a separate DATA_DIR containing "demo".')
            self.demo()
        self.stdout.write('Draft seed complete. No real goods or agreements have been published.')
    def demo(self):
        import json,secrets,os
        path=settings.DATA_DIR/'review-accounts.json'
        creds=json.loads(path.read_text()) if path.exists() else {}
        users={}
        for role in ['admin','reviewer','caseworker','warehouse','finance','merchant','member']:
            username='review_'+role
            user,created=User.objects.get_or_create(username=username,defaults={'email':username+'@example.invalid'})
            if created:
                password=secrets.token_urlsafe(22);user.set_password(password);user.save();creds[role]={'username':username,'password':password}
            if not created and role not in creds:raise CommandError('A review username already exists without a seed-owned credential record; refusing to claim it.')
            if role!='member':user.groups.add(Group.objects.get(name=role))
            users[role]=user
        fd=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_TRUNC,0o600)
        with os.fdopen(fd,'w') as f:json.dump(creds,f,indent=2)
        org,_=Organization.objects.get_or_create(name='Sandbox Community Supply',defaults={'user':users['merchant'],'agreement_status':'approved','terms':'Fictional test organization; no real agreement.'})
        names=[('demo-pantry','Test pantry essentials','測試・日常食品','food',1800,1500),('demo-home','Test home care set','測試・家居關懷組','home',2400,2000),('demo-warmth','Test comfort bundle','測試・暖心生活組','warmth',3200,2800),('demo-everyday','Test everyday tote','測試・日常提袋','home',1200,1000)]
        for slug,name,zh,cat,price,vol in names:
            p,_=Product.objects.get_or_create(slug=slug,defaults={'name':name,'name_zh':zh,'category':cat,'status':'published','price_cents':price,'volunteer_price_cents':vol,'care_price_cents':vol-100,'description':'SANDBOX ONLY. Fictional item for testing, not an offer to sell. Product image is a neutral placeholder.','description_zh':'僅供測試，虛構商品，並非銷售要約。圖片為中性佔位圖。','merchant':org,'fulfiller':'Sandbox team','unit':'item','is_demo':True,'specifications':{'test':True},'policy':'Test only. No actual purchase or shipment.','donation_bps':500,'donation_rule_version':1})
            Lot.objects.get_or_create(product=p,batch='TEST-SALE',defaults={'purpose':'sale','on_hand':20})
            Lot.objects.get_or_create(product=p,batch='TEST-AID',defaults={'purpose':'aid','on_hand':5,'restricted':True})
        demo_initialized=Setting.objects.filter(key='demo',value=True).exists()
        for k,v in {'shipping':{'zips':['10001','07302'],'pickup_cents':0,'delivery_cents':500},'water_zips':['10001','07302'],'verification_days':180,'retention_days':30,'demo':True}.items():
            if not demo_initialized:Setting.objects.update_or_create(key=k,defaults={'value':v})
        Budget.objects.get_or_create(name='Sandbox funded budget',defaults={'funded_cents':100000})
        c,created=Campaign.objects.get_or_create(slug='demo-community-care',defaults={'is_demo':True,'name':'A little care for everyday life','name_zh':'讓關懷走進日常','summary':'A sandbox project to review the complete contribution and accountability workflow. No real funds collected.','summary_zh':'用於審閱捐款及用途追蹤流程的測試項目，不收取真實款項。','body':'This fictional project exercises reviewed publication, policy consent, single contributions, test confirmations, refunds and transparent reporting.','target_cents':100000,'starts_at':timezone.now()-timedelta(days=1),'ends_at':timezone.now()+timedelta(days=60),'owner':users['admin'],'budget':[{'name':'Fictional household essentials','amount_cents':100000}],'beneficiaries':'Estimated test households only; no real beneficiaries.','execution':'Test fulfillment by the sandbox team.','consent_basis':'No beneficiary stories or identifiable data are published.','policy':'SANDBOX ONLY. Flexible fundraising: success is collected immediately. If below goal, reduce the fictional scope; if overfunded, hold excess for this same purpose pending review. Cancellation: refund original source. Remaining funds: refund or obtain separate consent; no unrelated transfer. Refund requests require finance approval. No tax deductibility is claimed.','suggested':[1000,2500,5000]})
        if not c.is_demo:c.is_demo=True;c.save()
        if created:
            submit_campaign(users['admin'],c);campaign_action(users['reviewer'],c,'approve');c.refresh_from_db();campaign_action(users['admin'],c,'publish')
        self.stdout.write('Isolated sandbox fixtures created. Review account credentials are stored privately in DATA_DIR/review-accounts.json (0600).')
