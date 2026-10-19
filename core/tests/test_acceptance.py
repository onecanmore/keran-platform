import hashlib,hmac,io,json,secrets
from datetime import datetime,timedelta,timezone as dtz
from concurrent.futures import ThreadPoolExecutor
from django.test import TestCase,TransactionTestCase,override_settings,Client
from django.contrib.auth.models import User,Group
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import close_old_connections,connections
from django.utils import timezone
from PIL import Image
from core.models import *
from core.services import *
from core.reports import rows_for,date_bounds
from core.api import safe_cell

FAST={'PASSWORD_HASHERS':['django.contrib.auth.hashers.MD5PasswordHasher']}

def user(name,role=None):
    u=User.objects.create_user(name,email=name+'@example.invalid',password='test-only-password-not-deployed')
    if role:u.groups.add(Group.objects.get_or_create(name=role)[0])
    return u

def fixtures(obj):
    obj.member=user('member');obj.other=user('other');obj.admin=user('admin','admin');obj.reviewer=user('reviewer','reviewer');obj.worker=user('worker','caseworker');obj.warehouse=user('warehouse','warehouse');obj.finance=user('finance','finance');obj.merchant=user('merchant','merchant')
    obj.org=Organization.objects.create(name='Test seller',user=obj.merchant,agreement_status='approved')
    obj.product=Product.objects.create(name='Test food',slug='test-food',name_zh='測試食品',status='published',kind='physical',category='food',price_cents=1000,volunteer_price_cents=800,care_price_cents=700,merchant=obj.org,fulfiller='Test warehouse',unit='item',donation_bps=1000,is_demo=True)
    obj.lot=Lot.objects.create(product=obj.product,batch='sale',purpose='sale',on_hand=10)
    obj.aidlot=Lot.objects.create(product=obj.product,batch='aid',purpose='aid',on_hand=10,restricted=True)
    for key,value in {'shipping':{'zips':['10001'],'pickup_cents':0,'delivery_cents':500},'water_zips':['10001'],'verification_days':180,'service_states':['NY','NJ'],'sandbox_tax_bps':0}.items():Setting.objects.create(key=key,value=value)
    obj.budget=Budget.objects.create(name='Funded',funded_cents=100000)
    obj.campaign=Campaign.objects.create(name='Test campaign',slug='test-campaign',summary='Test only',target_cents=10000,starts_at=timezone.now()-timedelta(days=1),ends_at=timezone.now()+timedelta(days=1),owner=obj.admin,budget=[{'name':'Test goods','amount_cents':10000}],beneficiaries='Test households',execution='Test execution',consent_basis='No identifiable story',policy='Flexible funding. Below goal reduce scope; overfund hold for same purpose; cancel/refund original source; remaining funds refund. Test only.',suggested=[1000],is_demo=True)
    submit_campaign(obj.admin,obj.campaign);campaign_action(obj.reviewer,obj.campaign,'approve');obj.campaign.refresh_from_db();campaign_action(obj.admin,obj.campaign,'publish');obj.campaign.refresh_from_db()

@override_settings(**FAST)
class Acceptance(TestCase):
    @classmethod
    def setUpTestData(cls):fixtures(cls)
    def api(self,path,data=None,actor=None,key=None):
        if actor:self.client.force_login(actor)
        kw={'HTTP_IDEMPOTENCY_KEY':key} if key else {}
        return self.client.post(path,json.dumps(data or {}),content_type='application/json',**kw)
    def request_data(self,**kw):
        data={'state':'NY','city':'New York','zip':'10001','categories':['food','home'],'needs':[{'name':'Groceries','quantity':2,'unit':'item','people':2,'use':'Meals','substitutes':True}],'email':'test@example.invalid','contact_consent':True,'message':'Private message','story_consent':False}
        data.update(kw);return data
    def case(self,**kw):return submit_case(self.member,self.request_data(**kw))
    def order_data(self,**kw):
        data={'items':[{'product_id':str(self.product.pk),'quantity':1}],'zip':'10001','method':'pickup'};data.update(kw);return data
    def order(self,**kw):
        data=self.order_data(**kw);data['fingerprint']=quote(self.member,data)['fingerprint'];return create_order(self.member,data,secrets.token_hex(16))
    def credit(self,case=None,kind='credit',amount=500,**kw):
        c=case or self.case();data={'kind':kind,'budget_id':str(self.budget.pk),'amount_cents':amount,'categories':['food'],'expires_at':(timezone.now()+timedelta(days=5)).isoformat(),'reason':'Reviewed need','source':'Funded test budget','quantity_limit':1};data.update(kw);return approve_grant(self.reviewer,c,data)
    def donation(self,amount=1000,**kw):
        data={'campaign_id':str(self.campaign.pk),'amount_cents':amount,'email':'donor@example.invalid','receipt_name':'Test donor','policy_version':self.campaign.version,'policy_consent':True};data.update(kw);return donation_checkout(self.member,data,secrets.token_hex(16))[0]
    def event(self,purpose,obj,amount,event='test-event',kind='succeeded'):
        return process_event({'event_id':event,'purpose':purpose,'reference':str(obj.pk),'kind':kind,'amount_cents':amount})

    def test_A01_public_routes_and_language(self):
        for path in ['/','/shop/','/help/','/fundraising/','/impact/','/services/water/','/partners/','/privacy/','/terms/','/returns/','/accessibility/']:
            response=self.client.get(path);self.assertEqual(response.status_code,200,path)
        self.client.post('/language/',{'language':'zh','next':'/'})
        self.assertContains(self.client.get('/'),'讓付出被珍惜')
        self.assertContains(self.client.get('/'),'lang="zh-Hant"')
    def test_A02_browser_cannot_choose_price(self):
        q=quote(self.member,self.order_data(price_cents=1,volunteer=True));self.assertEqual(q['cash_cents'],1000)
    def test_A03_volunteer_and_care_coexist_lowest_price(self):
        Verification.objects.create(user=self.member,description='Service',status='approved',expires_at=timezone.now()+timedelta(days=2))
        self.credit(kind='discount',amount=0)
        self.assertEqual(quote(self.member,self.order_data())['cash_cents'],700)
        self.assertTrue(volunteer_valid(self.member))
    def test_A04_expired_verification_requires_requote(self):
        v=Verification.objects.create(user=self.member,description='Service',status='approved',expires_at=timezone.now()+timedelta(days=2))
        data=self.order_data();data['fingerprint']=quote(self.member,data)['fingerprint']
        v.expires_at=timezone.now()-timedelta(seconds=1);v.save()
        with self.assertRaisesMessage(DomainError,'Prices or eligibility changed'):create_order(self.member,data,'expiry')
        self.assertEqual(Order.objects.count(),0)
    def test_A05_open_multiple_needs_persist_and_track(self):
        d=self.request_data();d['needs'].append({'name':'Digital setup','quantity':1,'unit':'session','category':'digital'})
        r=self.api('/api/help-requests/',d,self.member);self.assertEqual(r.status_code,200)
        c=Case.objects.get(pk=r.json()['data']['id']);self.assertEqual(c.needs.count(),2);self.assertEqual(c.message,'Private message');self.assertEqual(c.contact_status,'manual_pending')
    def test_A06_guessed_case_and_attachment_are_hidden(self):
        c=self.case();self.client.force_login(self.other)
        r=self.client.get(f'/api/help-requests/{c.pk}/');self.assertEqual(r.status_code,404);self.assertNotIn('Private message',r.content.decode())
        self.assertEqual(self.client.get(f'/account/cases/{c.pk}/').status_code,404)
    def test_A07_caseworker_cannot_approve_and_is_audited(self):
        c=self.case();c.assignee=self.worker;c.save()
        r=self.api(f'/api/help-requests/{c.pk}/transition/',{'status':'reviewing','reason':'Review'},self.worker)
        self.assertEqual(r.status_code,403);c.refresh_from_db();self.assertEqual(c.status,'received');self.assertTrue(Audit.objects.filter(action='mutation_denied').exists())
    def test_A08_outside_needs_recorded_delivery_blocked(self):
        self.assertTrue(self.case(state='CA',zip='90001').outside_region)
        with self.assertRaises(DomainError):quote(self.member,self.order_data(method='delivery',zip='90001'))
    def test_A09_credit_is_funded_scoped_and_bounded(self):
        g=self.credit(amount=500);q=quote(self.member,self.order_data(grant_id=str(g.pk)))
        self.assertEqual(q['aid_cents'],500);self.assertEqual(q['cash_cents'],500)
        with self.assertRaises(DomainError):self.credit(case=self.case(),amount=100001,exception_reason='Test')
        self.assertEqual(Grant.objects.count(),1)
    def test_A10_last_item_second_order_rejected(self):
        self.lot.on_hand=1;self.lot.save();self.order()
        with self.assertRaises(DomainError):self.order()
        self.lot.refresh_from_db();self.assertEqual(self.lot.reserved,1);self.assertEqual(self.lot.available,0)
    def test_A11_release_stock_and_credit_once(self):
        g=self.credit();o=self.order(grant_id=str(g.pk));release_order(o);release_order(o)
        self.lot.refresh_from_db();g.refresh_from_db();self.assertEqual(self.lot.reserved,0);self.assertEqual(g.available,500)
        self.assertEqual(AidLedger.objects.filter(grant=g,kind='release').count(),1)
    def test_A12_payment_event_replay_is_idempotent(self):
        o=self.order();self.event('commerce',o,o.cash_cents);self.event('commerce',o,o.cash_cents)
        self.assertEqual(PaymentEvent.objects.count(),1);self.assertEqual(FinanceEntry.objects.filter(bucket='commerce',kind='payment').count(),1)
    def test_A13_mixed_source_refund_original_sources_and_corporate_adjustment(self):
        g=self.credit();o=self.order(grant_id=str(g.pk));self.event('commerce',o,500)
        i=Item.objects.get(suborder__order=o);self.assertEqual(i.donation_estimated_cents,50)
        r=request_refund(self.finance,{'item_id':str(i.pk),'amount_cents':250,'aid_cents':250,'reason':'Partial refund','idempotency_key':'r1'})
        self.event('refund',r,250,event='refund-event');g.refresh_from_db();i.refresh_from_db()
        self.assertEqual(g.available,250);self.assertEqual(i.refunded_cash_cents,250);self.assertEqual(i.donation_estimated_cents,25)
        self.assertEqual(FinanceEntry.objects.get(bucket='corporate_donation',kind='adjusted').amount_cents,-25)
    def test_A14_split_by_seller_fulfiller(self):
        org=Organization.objects.create(name='Seller 2',agreement_status='approved')
        p=Product.objects.create(name='Second item',slug='second',kind='physical',status='published',merchant=org,fulfiller='Other warehouse',price_cents=2000)
        Lot.objects.create(product=p,batch='2',purpose='sale',on_hand=2)
        o=self.order(items=[{'product_id':str(self.product.pk),'quantity':1},{'product_id':str(p.pk),'quantity':1}]);self.assertEqual(o.suborders.count(),2);self.assertEqual(sum(i.cash_cents for i in Item.objects.filter(suborder__order=o)),o.cash_cents)
    def test_A15_pickup_single_use(self):
        o=self.order();self.event('commerce',o,1000);o.refresh_from_db();s=o.suborders.get();token=pickup_issue(self.member,s)
        fulfill_suborder(self.warehouse,s,token)
        with self.assertRaises(DomainError):fulfill_suborder(self.warehouse,s,token)
        self.lot.refresh_from_db();self.assertEqual(self.lot.on_hand,9);self.assertEqual(self.lot.reserved,0)
    def test_A16_water_booking_has_no_payment_contract(self):
        r=self.api('/api/appointments/',{'zip':'10001','address':'Test address','phone':'555-0100','preferred':'Afternoon'},self.member)
        self.assertEqual(r.status_code,200);self.assertEqual(Appointment.objects.get().status,'submitted');self.assertFalse(Order.objects.exists());self.assertFalse(FinanceEntry.objects.filter(bucket='commerce').exists())
    def test_A17_assets_require_inspection_and_receipt(self):
        a=Asset.objects.create(product=self.product,serial='ASSET-1');g=self.credit(kind='free',amount=0)
        r=self.api(f'/api/assets/{a.pk}/',{'action':'reserve','grant_id':str(g.pk)},self.reviewer);self.assertEqual(r.status_code,400)
        r=self.api(f'/api/assets/{a.pk}/',{'action':'inspect','passed':True,'reason':'Safety checks passed'},self.warehouse);self.assertEqual(r.status_code,200)
        self.assertEqual(self.api(f'/api/assets/{a.pk}/',{'action':'reserve','grant_id':str(g.pk)},self.reviewer).status_code,200)
        self.assertEqual(self.api(f'/api/assets/{a.pk}/',{'action':'deliver','recipient_confirmation':False},self.warehouse).status_code,400)
        self.assertEqual(self.api(f'/api/assets/{a.pk}/',{'action':'deliver','recipient_confirmation':True},self.warehouse).status_code,200)
        a.refresh_from_db();self.assertEqual(a.status,'delivered');self.assertTrue(a.receipt_confirmed)
    def test_A18_purpose_pools_and_restrictions(self):
        with self.assertRaises(DomainError):reserve_lot(self.aidlot.pk,1,'sale')
        r=self.api(f'/api/stock/{self.aidlot.pk}/transfer/',{'quantity':1,'purpose':'sale','reason':'Not allowed'},self.warehouse);self.assertEqual(r.status_code,400)
        self.aidlot.refresh_from_db();self.assertEqual(self.aidlot.available,10)
    def test_A19_partial_aid_counts_only_on_delivery(self):
        c=self.case();n=c.needs.get();n.confirmed=2;n.save();p=Plan.objects.create(name='Test plan',state='active');p.needs.add(n)
        a=allocate(self.reviewer,p,n,self.aidlot.pk,1);n.refresh_from_db();self.assertEqual((n.gap,n.allocated,n.fulfilled),(1,1,0))
        fulfill_allocation(self.warehouse,a);fulfill_allocation(self.warehouse,a);n.refresh_from_db();self.assertEqual((n.gap,n.allocated,n.fulfilled),(1,1,1))
    def test_A20_detail_export_same_filter_and_totals(self):
        self.case();self.case(state='NJ',city='Jersey City',zip='07302');self.client.force_login(self.reviewer)
        data=self.client.get('/api/reports/cases/?state=NY').json()['data'];self.assertEqual(data['count'],1)
        response=self.client.get('/api/reports/cases/export/?state=NY')
        from openpyxl import load_workbook
        rows=list(load_workbook(io.BytesIO(b''.join(response.streaming_content))).active.values)
        self.assertEqual(len(rows)-1,data['count']);self.assertEqual(rows[1][0],data['results'][0]['id'])
    def test_A21_household_dedup_does_not_guess_other_users(self):
        a=self.case();b=self.case();c=submit_case(self.other,self.request_data());self.assertEqual(a.household_id,b.household_id);self.assertNotEqual(a.household_id,c.household_id)
    def test_A22_referral_and_estimates_are_not_outcomes_or_cash_received(self):
        c=self.case();transition_case(self.reviewer,c,'reviewing','Review');c.refresh_from_db();transition_case(self.reviewer,c,'referred','Referred')
        self.order();self.assertFalse(Allocation.objects.filter(fulfilled=True).exists());self.assertFalse(FinanceEntry.objects.filter(kind='received').exists());self.assertContains(self.client.get('/impact/'),'No verified outcomes')
    def test_A23_roles_are_scoped_at_api(self):
        self.case();self.order();d=self.donation()
        for actor in [self.merchant,self.warehouse,self.worker]:
            self.client.force_login(actor);self.assertEqual(self.client.get('/api/reports/donations/').status_code,403)
        self.client.force_login(self.merchant);self.assertEqual(self.client.get('/api/reports/cases/').status_code,403)
        self.assertEqual(self.client.get('/api/reports/orders/').json()['data']['count'],1)
        other_org=Organization.objects.create(name='Unrelated');self.org.user=None;self.org.save()
        self.assertEqual(self.client.get('/api/reports/orders/').json()['data']['count'],0)
    def test_A24_story_consent_is_optional_and_private(self):
        c=self.case();self.assertFalse(Consent.objects.get(case=c,kind='story').granted)
        self.assertNotContains(self.client.get('/community-needs/'),'Private message')
    @override_settings(WEBHOOK_SECRET='')
    def test_A25_unconfigured_external_operations_fail_closed(self):
        r=self.api('/api/payment/webhook/',{'event_id':'fake'});self.assertEqual(r.status_code,503)
        self.assertEqual(self.client.get('/fundraising/').status_code,200)
        self.assertFalse(Outbox.objects.filter(status='sent').exists())
    def test_A26_empty_and_filtered_views_do_not_fake_data(self):
        self.assertContains(self.client.get('/shop/?q=missing'),'No confirmed items found')
        self.assertContains(self.client.get('/impact/'),'No verified outcomes')
    def test_A27_shared_supply_cannot_double_allocate(self):
        self.aidlot.on_hand=1;self.aidlot.save();c=self.case();n=c.needs.get();n.confirmed=2;n.save()
        p1=Plan.objects.create(name='One',state='active');p2=Plan.objects.create(name='Two',state='active');p1.needs.add(n);p2.needs.add(n)
        allocate(self.reviewer,p1,n,self.aidlot.pk,1)
        with self.assertRaises(DomainError):allocate(self.reviewer,p2,n,self.aidlot.pk,1)
        self.assertEqual(Allocation.objects.count(),1)
    def test_A28_serialization_preserves_relationships(self):
        # Online physical backup/restore additionally exercised by scripts/verify_restore.py.
        from django.core import serializers
        c=self.case();o=self.order();data=serializers.serialize('json',[c,*c.needs.all(),o,*o.suborders.all(),*Item.objects.filter(suborder__order=o)])
        restored=list(serializers.deserialize('json',data));self.assertEqual(len(restored),5);self.assertEqual(restored[1].object.case_id,c.pk)
    def test_A29_malicious_upload_rejected_and_excel_escaped(self):
        c=self.case();self.client.force_login(self.member)
        f=SimpleUploadedFile('attack.svg',b'<svg onload="alert(1)"></svg>',content_type='image/svg+xml')
        r=self.client.post('/api/attachments/',{'file':f,'case_id':str(c.pk)});self.assertEqual(r.status_code,400);self.assertFalse(Attachment.objects.exists())
        for value in ['=1+1','+cmd','@SUM(1)',' -2+3']:
            self.assertTrue(safe_cell(value).startswith("'"))
    def test_A30_new_york_day_bounds_handle_dst(self):
        start,end=date_bounds('2026-03-08');self.assertEqual((end.astimezone(dtz.utc)-start.astimezone(dtz.utc)).total_seconds(),23*3600)
        start,end=date_bounds('2026-11-01');self.assertEqual((end.astimezone(dtz.utc)-start.astimezone(dtz.utc)).total_seconds(),25*3600)
        self.case();self.client.force_login(self.reviewer);day=timezone.localdate().isoformat();self.assertEqual(self.client.get(f'/api/reports/cases/?from={day}&to={day}').json()['data']['count'],1)
    def test_A31_admin_creates_product_without_code_change(self):
        self.client.force_login(self.admin);buf=io.BytesIO();Image.new('RGB',(20,20),'green').save(buf,'PNG')
        data={'name':'New goods','name_zh':'新商品','slug':'new-goods','description':'Test','kind':'physical','source':'merchant_supply','category':'home','merchant':str(self.org.pk),'fulfiller':'Team','specifications':'{"condition":"new"}','unit':'item','price_cents':1200,'policy':'Review draft','safety_confirmed':True,'image':SimpleUploadedFile('test.png',buf.getvalue(),content_type='image/png')}
        response=self.client.post('/admin/catalog/?new=1',data);self.assertEqual(response.status_code,302)
        p=Product.objects.get(slug='new-goods');self.assertEqual(p.status,'draft');product_publish(self.reviewer,p);p.refresh_from_db();self.assertEqual(p.status,'published')
    def test_A32_campaign_review_publish_and_checkout(self):
        self.assertEqual(self.campaign.status,'published');d=self.donation();self.assertEqual(d.status,'pending');self.assertContains(self.client.get('/fundraising/test-campaign/'),'Test campaign')
    def test_A33_unapproved_or_paused_cannot_checkout(self):
        for status in ['draft','submitted_for_review','approved','paused','closed']:
            self.campaign.status=status;self.campaign.save()
            with self.assertRaises(DomainError):self.donation()
        self.assertEqual(Donation.objects.count(),0)
    def test_A34_tamper_and_redirect_cannot_mark_success(self):
        d=self.donation()
        with self.assertRaises(DomainError):self.event('public_donation',d,1)
        self.client.force_login(self.member);self.client.get('/donations/result/?success=true');d.refresh_from_db();self.assertEqual(d.status,'pending');self.assertEqual(campaign_totals(self.campaign)['confirmed'],0)
    def test_A35_repeated_donation_event_one_receipt_and_entry(self):
        d=self.donation();self.event('public_donation',d,1000);self.event('public_donation',d,1000)
        self.assertEqual(Receipt.objects.count(),1);self.assertEqual(Outbox.objects.filter(kind='donation_receipt').count(),1);self.assertEqual(campaign_totals(self.campaign)['confirmed'],1000)
    def test_A36_failed_refund_does_not_reduce_confirmed(self):
        d=self.donation();self.event('public_donation',d,1000)
        r=request_refund(self.finance,{'donation_id':str(d.pk),'amount_cents':300,'reason':'Partial','idempotency_key':'refund'})
        self.assertEqual(campaign_totals(self.campaign)['confirmed'],1000);confirm_refund(r,False);self.assertEqual(campaign_totals(self.campaign)['confirmed'],1000)
        r2=request_refund(self.finance,{'donation_id':str(d.pk),'amount_cents':300,'reason':'Retry','idempotency_key':'refund2'});confirm_refund(r2,True);confirm_refund(r2,True)
        self.assertEqual(campaign_totals(self.campaign)['confirmed'],700)
    def test_A37_overfund_and_late_success_not_lost(self):
        a=self.donation(6000);b=self.donation(6000);self.event('public_donation',a,6000,'a');self.campaign.status='closed';self.campaign.save();self.event('public_donation',b,6000,'b');b.refresh_from_db()
        totals=campaign_totals(self.campaign);self.assertEqual(totals['percent'],120);self.assertEqual(totals['bar'],100);self.assertTrue(b.needs_review)
        with self.assertRaises(DomainError):self.donation()
    def test_A38_donor_privacy(self):
        d=self.donation(receipt_name='Private Person',message='Private donor message');self.event('public_donation',d,1000)
        self.client.force_login(self.other);self.assertEqual(self.client.get(f'/api/donations/{d.pk}/').status_code,404)
        page=self.client.get('/fundraising/test-campaign/');self.assertNotContains(page,'Private Person');self.assertNotContains(page,'Private donor message')
    def test_A39_cancel_creates_review_and_notification(self):
        d=self.donation();self.event('public_donation',d,1000);campaign_action(self.admin,self.campaign,'cancel','Cannot execute test plan');d.refresh_from_db()
        self.assertTrue(d.needs_review);self.assertEqual(Outbox.objects.filter(kind='campaign_cancelled').count(),1);self.assertEqual(campaign_totals(self.campaign)['confirmed'],1000)
    def test_A40_sources_remain_separate(self):
        o=self.order();self.event('commerce',o,1000,'order-event');d=self.donation();self.event('public_donation',d,1000,'donation-event')
        self.assertEqual(FinanceEntry.objects.filter(bucket='commerce',kind='payment').aggregate(n=Sum('amount_cents'))['n'],1000)
        self.assertEqual(FinanceEntry.objects.get(bucket='corporate_donation',kind='estimated').amount_cents,100)
        self.assertEqual(campaign_totals(self.campaign)['confirmed'],1000)
    def test_A41_reconciliation_expenses_disputes_consistency(self):
        d=self.donation();self.event('public_donation',d,1000)
        self.api('/api/finance/reconcile/',{'campaign_id':str(self.campaign.pk),'kind':'fee','amount_cents':50,'external_id':'fee1','reason':'Provider fee'},self.finance)
        self.api('/api/finance/reconcile/',{'campaign_id':str(self.campaign.pk),'kind':'settlement','amount_cents':950,'external_id':'bank1','reason':'Bank proof'},self.finance)
        e=Expense.objects.create(campaign=self.campaign,category='goods',payee='Vendor',amount_cents=200,reason='Evidence')
        self.assertEqual(self.api(f'/api/campaign-expenses/{e.pk}/',{'action':'approve'},self.finance).status_code,200)
        self.assertEqual(self.api(f'/api/campaign-expenses/{e.pk}/',{'action':'pay','external_id':'paid1'},self.finance).status_code,200)
        dispute_event(d,'dispute1',100,'open');t=campaign_totals(self.campaign);self.assertEqual(t['spendable'],650);self.assertEqual(t['confirmed'],1000)
        dispute_event(d,'dispute1',100,'lost');self.assertEqual(campaign_totals(self.campaign)['confirmed'],900)
        dispute_event(d,'dispute1',100,'restored');self.assertEqual(campaign_totals(self.campaign)['confirmed'],1000)
    def test_A42_no_live_payments_or_fake_bank_settlement(self):
        d=self.donation();self.assertTrue(d.sandbox);self.event('public_donation',d,1000)
        totals=campaign_totals(self.campaign);self.assertEqual(totals['settlement'],0);self.assertEqual(totals['spendable'],0)
        self.assertContains(self.client.get('/fundraising/'),'No real donations')

    def test_signed_webhook_and_expiry(self):
        with override_settings(WEBHOOK_SECRET='test-signing-key'):
            o=self.order();payload={'event_id':'signed','purpose':'commerce','kind':'succeeded','reference':str(o.pk),'amount_cents':o.cash_cents};body=json.dumps(payload).encode();timestamp=str(int(timezone.now().timestamp()))
            sig=hmac.new(b'test-signing-key',timestamp.encode()+b'.'+body,hashlib.sha256).hexdigest()
            r=self.client.post('/api/payment/webhook/',body,content_type='application/json',HTTP_X_KERAN_TIMESTAMP=timestamp,HTTP_X_KERAN_SIGNATURE=sig);self.assertEqual(r.status_code,200)
            self.assertEqual(self.client.post('/api/payment/webhook/',body,content_type='application/json',HTTP_X_KERAN_TIMESTAMP=timestamp,HTTP_X_KERAN_SIGNATURE='bad').status_code,403)
    def test_idempotent_stock_mutation(self):
        data={'delta':2,'hold_delta':0,'reason':'Received test goods'};path=f'/api/stock/{self.lot.pk}/adjust/'
        self.assertEqual(self.api(path,data,self.warehouse,'same-key').status_code,200);self.assertEqual(self.api(path,data,self.warehouse,'same-key').status_code,200)
        self.lot.refresh_from_db();self.assertEqual(self.lot.on_hand,12)
        data['delta']=3;self.assertEqual(self.api(path,data,self.warehouse,'same-key').status_code,409)
    def test_self_review_and_unfunded_approval_denied(self):
        c=submit_case(self.reviewer,self.request_data())
        with self.assertRaises(DomainError):transition_case(self.reviewer,c,'reviewing','My own case')
        with self.assertRaises(DomainError):self.credit(case=c)
    def test_private_attachment_access_and_csrf(self):
        c=self.case();self.client.force_login(self.member);buf=io.BytesIO();Image.new('RGB',(10,10),'white').save(buf,'PNG')
        response=self.client.post('/api/attachments/',{'case_id':str(c.pk),'file':SimpleUploadedFile('proof.png',buf.getvalue(),content_type='image/png')});self.assertEqual(response.status_code,200)
        pk=response.json()['data']['id'];url=self.client.get(f'/api/attachments/{pk}/').json()['data']['url'];self.assertEqual(self.client.get(url).status_code,200)
        self.client.force_login(self.warehouse);self.assertEqual(self.client.get(f'/api/attachments/{pk}/').status_code,404);self.assertEqual(self.client.get(url).status_code,404)
        csrf_client=Client(enforce_csrf_checks=True);csrf_client.force_login(self.member);self.assertEqual(csrf_client.post('/api/help-requests/',json.dumps(self.request_data()),content_type='application/json').status_code,403)
    def test_admin_and_member_routes_render(self):
        self.client.force_login(self.admin)
        for route in ['','catalog/','inventory/','fundraising/','partners/','plans/','tasks/','cases/','orders/','donations/','finance/','settings/','audit/','appointments/','verifications/','catalog/?new=1','fundraising/?new=1']:
            self.assertEqual(self.client.get('/admin/'+route).status_code,200,route)
        self.client.force_login(self.member)
        for route in ['','orders/','cases/','grants/','verifications/','appointments/','donations/']:
            self.assertEqual(self.client.get('/account/'+route).status_code,200,route)
