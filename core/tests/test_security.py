import json,time
from django.test import TestCase,override_settings
from django.contrib.auth.models import User,Group
from django.utils import timezone
from datetime import timedelta
from core.models import *
from core.services import *
from core.mfa import generate_secret,code_for,cipher,verify
from .test_acceptance import FAST,fixtures

@override_settings(**FAST)
class SecurityAndJobs(TestCase):
    @classmethod
    def setUpTestData(cls):fixtures(cls)
    def test_totp_encrypted_seed_and_replay_rejection(self):
        secret=generate_secret();encrypted=cipher().encrypt(secret.encode()).decode();self.assertNotIn(secret,encrypted)
        StaffMFA.objects.create(user=self.admin,encrypted_secret=encrypted)
        code=code_for(secret,int(time.time())//30);self.assertTrue(verify(self.admin,code));self.assertFalse(verify(self.admin,code))
    @override_settings(REQUIRE_STAFF_MFA=True)
    def test_production_staff_mfa_gate(self):
        self.client.force_login(self.admin);self.assertRedirects(self.client.get('/admin/'),'/account/security/',fetch_redirect_response=False)
        self.assertEqual(self.client.get('/api/reports/cases/').status_code,403)
        session=self.client.session;session['staff_mfa_verified']=True;session.save();self.assertEqual(self.client.get('/admin/').status_code,200)
    def test_json_array_rejected_without_server_error(self):
        self.client.force_login(self.member);r=self.client.post('/api/checkout/quote/','[]',content_type='application/json');self.assertEqual(r.status_code,400)
    def test_login_rate_limit(self):
        for _ in range(8):self.client.post('/login/',{'username':'unknown','password':'wrong'})
        self.assertEqual(self.client.post('/login/',{'username':'unknown','password':'wrong'}).status_code,429)
    def test_anonymous_draft_saved_server_side_and_login_required_to_submit(self):
        data={'state':'NY','city':'New York','zip':'10001','needs':[{'name':'Test item','quantity':1,'unit':'item'}],'categories':['home'],'email':'test@example.invalid'}
        r=self.client.post('/api/help-requests/',json.dumps(data),content_type='application/json');self.assertEqual(r.status_code,200);self.assertIn('redirect',r.json()['data']);self.assertFalse(Case.objects.exists());self.assertEqual(self.client.session['help_draft']['zip'],'10001')
    def test_expired_aid_reservation_releases_once(self):
        h=Household.objects.create();h.members.add(self.member);c=Case.objects.create(user=self.member,household=h,state='NY',city='NY',zip='10001',status='matching');n=Need.objects.create(case=c,name='Food',unit='item',requested=2,confirmed=2);p=Plan.objects.create(name='Plan',state='approved');p.needs.add(n)
        a=allocate(self.reviewer,p,n,self.aidlot.pk,1);Reservation.objects.filter(pk=a.reservation_id).update(expires_at=timezone.now()-timedelta(minutes=1))
        from django.core.management import call_command
        call_command('run_jobs',verbosity=0);call_command('run_jobs',verbosity=0)
        self.aidlot.refresh_from_db();n.refresh_from_db();self.assertEqual(self.aidlot.reserved,0);self.assertEqual(n.allocated,0);self.assertEqual(StockMovement.objects.filter(kind='aid_release').count(),1)
    def test_stale_waitlist_is_not_active_gap(self):
        h=Household.objects.create();c=Case.objects.create(user=self.member,household=h,state='NY',city='NY',zip='10001',status='waitlisted');n=Need.objects.create(case=c,name='Need',unit='item',requested=2,confirmed=2)
        self.assertEqual(n.gap,0);c.reconfirmed_at=timezone.now();c.save();n.refresh_from_db();self.assertEqual(n.gap,2)
    def test_role_changes_require_password_and_reason(self):
        self.client.force_login(self.admin)
        data={'user_id':self.other.pk,'roles':['finance'],'reason':'Grant necessary finance duties'}
        self.assertEqual(self.client.post('/api/staff/roles/',json.dumps(data),content_type='application/json').status_code,403)
        data['current_password']='test-only-password-not-deployed'
        self.assertEqual(self.client.post('/api/staff/roles/',json.dumps(data),content_type='application/json').status_code,200)
        self.assertTrue(self.other.groups.filter(name='finance').exists())
    def test_security_headers_and_private_cache(self):
        self.client.force_login(self.member);response=self.client.get('/account/')
        self.assertEqual(response.headers['Cache-Control'],'no-store');self.assertIn("script-src 'self'",response.headers['Content-Security-Policy']);self.assertEqual(response.headers['X-Frame-Options'],'DENY')
    def test_refunds_and_chargebacks_reduce_spendable_funds(self):
        from .test_acceptance import Acceptance
        obj=Acceptance();obj.member=self.member;obj.campaign=self.campaign
        d=obj.donation();succeed_donation(d,'settled-payment')
        FinanceEntry.objects.create(campaign=self.campaign,bucket='public_donation',kind='settlement',amount_cents=950,reference='bank')
        r=request_refund(self.finance,{'donation_id':str(d.pk),'amount_cents':200,'reason':'Requested refund','idempotency_key':'pending-refund'})
        self.assertEqual(campaign_totals(self.campaign)['spendable'],750)
        confirm_refund(r,True);self.assertEqual(campaign_totals(self.campaign)['spendable'],750)
        dispute_event(d,'disputed',100,'open');self.assertEqual(campaign_totals(self.campaign)['spendable'],650)
        dispute_event(d,'disputed',100,'lost');self.assertEqual(campaign_totals(self.campaign)['spendable'],650)
    def test_nonempty_order_work_table_renders_for_warehouse_without_aid_identity(self):
        from .test_acceptance import Acceptance
        helper=Acceptance();helper.member=self.member;helper.product=self.product
        order=helper.order()
        self.client.force_login(self.warehouse)
        response=self.client.get('/admin/orders/');self.assertEqual(response.status_code,200);self.assertContains(response,'Test food')
        row=self.client.get('/api/reports/orders/').json()['data']['results'][0]
        self.assertNotIn('aid_cents',row);self.assertNotIn('cash_cents',row)
    def test_shipping_refund_is_separate_and_cannot_exceed_original(self):
        from .test_acceptance import Acceptance
        helper=Acceptance();helper.member=self.member;helper.product=self.product
        o=helper.order(method='delivery',address='Fictional delivery address');settle_order(o,'test-shipping-payment')
        r=request_refund(self.finance,{'order_id':str(o.pk),'shipping_cents':500,'tax_cents':0,'amount_cents':500,'reason':'Delivery charge refund','idempotency_key':'shipping'})
        confirm_refund(r,True)
        self.assertEqual(FinanceEntry.objects.get(reference=str(r.pk),bucket='commerce').amount_cents,-500)
        with self.assertRaises(DomainError):request_refund(self.finance,{'order_id':str(o.pk),'shipping_cents':1,'amount_cents':1,'reason':'Too much','idempotency_key':'shipping-too-much'})
    def test_household_link_requires_consent_and_affects_new_requests(self):
        from .test_acceptance import Acceptance
        helper=Acceptance();helper.member=self.member
        c=helper.case();target=Household.objects.create(label='Confirmed household');target.members.add(self.other)
        self.client.force_login(self.reviewer);path=f'/api/help-requests/{c.pk}/household/'
        data={'household_id':str(target.pk),'reason':'Manually confirmed household membership'}
        self.assertEqual(self.client.post(path,json.dumps(data),content_type='application/json').status_code,400)
        data['confirmed_consent']=True;self.assertEqual(self.client.post(path,json.dumps(data),content_type='application/json').status_code,200)
        self.assertEqual(helper.case().household_id,target.pk)
    def test_required_product_safety_fields_block_publication(self):
        from PIL import Image
        from django.core.files.base import ContentFile
        import io
        p=Product.objects.create(name='Unconfirmed heated mat',slug='heated-mat-test',merchant=self.org,fulfiller='Team',price_cents=1000,safety_confirmed=True,policy='Policy',specifications={'condition':'new'})
        Setting.objects.create(key='product_requirements',value={'heated-mat-test':['condition','intended_use','electrical_safety']})
        buf=io.BytesIO();Image.new('RGB',(10,10),'white').save(buf,'PNG');p.image.save('safety-test.png',ContentFile(buf.getvalue()))
        with self.assertRaises(DomainError):product_publish(self.reviewer,p)
        p.refresh_from_db();self.assertEqual(p.status,'draft')
        p.specifications.update(intended_use='Human',electrical_safety='Inspected with documented result');p.save();product_publish(self.reviewer,p);self.assertEqual(p.status,'published')
    def test_duplicate_csv_import_does_not_double_stock(self):
        from django.core.files.uploadedfile import SimpleUploadedFile
        self.client.force_login(self.warehouse)
        data=f'lot_id,delta,hold_delta,reason\n{self.lot.pk},2,0,Counted receipt\n'.encode()
        for _ in range(2):
            response=self.client.post('/api/stock/import/',{'file':SimpleUploadedFile('receipt.csv',data,content_type='text/csv')});self.assertEqual(response.status_code,200)
        self.lot.refresh_from_db();self.assertEqual(self.lot.on_hand,12);self.assertEqual(StockMovement.objects.filter(kind='csv_import').count(),1)
    def test_malformed_cart_line_is_400(self):
        self.client.force_login(self.member)
        response=self.client.post('/api/checkout/quote/',json.dumps({'items':[1],'zip':'10001','method':'pickup'}),content_type='application/json');self.assertEqual(response.status_code,400)
