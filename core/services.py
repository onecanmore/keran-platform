"""All inventory, aid and money mutations go through transactional services."""
import hashlib, json, secrets
from datetime import timedelta
from django.db import transaction
from django.db.models import F, Q, Sum
from django.utils import timezone
from .models import *

class DomainError(Exception):
    def __init__(self, message, code='invalid', status=400): self.message,self.code,self.status=message,code,status

def fail(message,code='invalid',status=400): raise DomainError(message,code,status)
def require(user,*roles):
    if not user.is_authenticated: fail('Please sign in. / 請先登入。','authentication',401)
    if not user.is_superuser and not user.groups.filter(name__in=roles).exists():
        audit(user,'permission_denied','role',','.join(roles))
        fail('Permission denied. / 沒有操作權限。','forbidden',403)
def audit(user,action,target,reason='',**metadata):
    return Audit.objects.create(actor=user if user and user.is_authenticated else None,action=action,target=str(target),reason=str(reason)[:500],metadata=metadata)
def config(key,default=None):
    row=Setting.objects.filter(key=key).first()
    return row.value if row else default

def integer(value,minimum=0,maximum=100000000):
    if isinstance(value,bool) or not isinstance(value,int) or value<minimum or value>maximum: fail('Invalid integer amount / 數量或金額無效')
    return value

def text(value,maximum=3000,required=True):
    if not isinstance(value,str) or len(value)>maximum or (required and not value.strip()): fail('Missing or invalid text / 請完整填寫欄位')
    return value.strip()

def case_scope(user):
    if user.is_superuser or user.groups.filter(name__in=['admin','reviewer']).exists(): return Case.objects.all()
    if user.groups.filter(name='caseworker').exists(): return Case.objects.filter(Q(assignee=user)|Q(user=user))
    return Case.objects.filter(user=user)

def order_scope(user):
    if user.is_superuser or user.groups.filter(name__in=['admin','finance','warehouse']).exists(): return Order.objects.all()
    return Order.objects.filter(user=user)

def active_grants(user,kind=None):
    qs=Grant.objects.filter(user=user,active=True,expires_at__gt=timezone.now())
    return qs.filter(kind=kind) if kind else qs

def eligible(grant,product):
    return grant.products.filter(pk=product.pk).exists() or product.category in grant.categories

def volunteer_valid(user):
    return Verification.objects.filter(user=user,status='approved',expires_at__gt=timezone.now()).exists()

def product_publish(actor,p):
    require(actor,'admin','reviewer')
    if not p.safety_confirmed or not p.specifications or not p.policy or not p.image: fail('Safety, specifications, photo and policy must be confirmed before publication.')
    if p.kind=='physical' and (p.price_cents is None or not p.merchant or not p.fulfiller): fail('Seller, fulfiller and price are required.')
    requirements=config('product_requirements',{}).get(p.slug,['condition'])
    if not isinstance(p.specifications,dict) or any(not p.specifications.get(field) for field in requirements):fail('Required safety/use specifications are missing: '+', '.join(requirements))
    if p.donation_bps is not None and p.donation_bps>10000:fail('Donation percentage must be between 0 and 100%.')
    if p.merchant and p.merchant.agreement_status!='approved': fail('Merchant agreement is not approved.')
    p.status='published'; p.version+=1; p.save(); audit(actor,'product_publish',p.pk)

@transaction.atomic
def submit_case(user,data,draft=False):
    household=user.households.filter(verified=True).order_by('-updated_at').first() or user.households.first()
    if not household:
        household=Household.objects.create(label='Private household'); household.members.add(user)
    state=text(data.get('state',''),2).upper(); zip_code=text(data.get('zip',''),10)
    if len(zip_code)!=5 or not zip_code.isdigit(): fail('ZIP must contain five digits.')
    if not data.get('email') and not data.get('phone'): fail('Email or phone is required.')
    if not draft and not data.get('contact_consent'): fail('Contact consent is required to submit.')
    applicant=data.get('applicant_type','self')
    if applicant not in ['self','family','proxy','referral']: fail('Invalid applicant type')
    if applicant in ['proxy','referral'] and not data.get('referral_consent'): fail('Consent for referral / applying on behalf is required.')
    cats=data.get('categories',[])
    if not isinstance(cats,list) or not cats or len(cats)>7: fail('Select need categories.')
    case=Case.objects.create(user=user,household=household,state=state,city=text(data.get('city',''),100),zip=zip_code,categories=cats,
        status='draft' if draft else 'received',applicant_type=applicant,urgency=data.get('urgency','two_weeks'),recurrence=data.get('recurrence','once'),
        message=text(data.get('message',''),3000,False),method=data.get('method','unsure'),email=data.get('email',''),phone=text(data.get('phone',''),30,False),
        language=data.get('language','en'),contact_time=text(data.get('contact_time',''),120,False),outside_region=state not in config('service_states',['NY','NJ']))
    needs=data.get('needs',[])
    if not isinstance(needs,list) or not 1<=len(needs)<=20 or not all(isinstance(need,dict) for need in needs): fail('Provide 1–20 need items.')
    for n in needs:
        Need.objects.create(case=case,name=text(n.get('name',''),180),category=text(n.get('category',cats[0]),80),unit=text(n.get('unit','item'),30),requested=integer(n.get('quantity'),1,10000),people=integer(n.get('people',1),1,1000),use=text(n.get('use',''),1000,False),substitutes=bool(n.get('substitutes',True)))
    for kind in ['contact','referral','story']:
        Consent.objects.create(user=user,case=case,kind=kind,granted=bool(data.get(kind+'_consent',False)))
    audit(user,'case_create',case.pk)
    if not draft: Outbox.objects.create(user=user,recipient=case.email,kind='case_received',reference=str(case.pk))
    return case

CASE_TRANSITIONS={'draft':['received','withdrawn'],'received':['reviewing','needs_info','withdrawn'],'reviewing':['matching','needs_info','waitlisted','referred','declined','withdrawn'],'needs_info':['reviewing','withdrawn'],'matching':['arranged','waitlisted','needs_info','withdrawn'],'arranged':['completed','matching','withdrawn'],'waitlisted':['reviewing','matching','withdrawn'],'declined':['reviewing'],'referred':['reviewing'],'completed':['reviewing'],'withdrawn':['reviewing']}
def transition_case(actor,case,status,reason):
    if case.user_id==actor.id and status=='withdrawn': pass
    else:
        require(actor,'reviewer','admin')
        if case.user_id==actor.id: fail('A reviewer cannot approve or review their own case.','conflict',403)
    with transaction.atomic():
        case=Case.objects.select_for_update().get(pk=case.pk)
        if status not in CASE_TRANSITIONS.get(case.status,[]): fail('Invalid case transition.')
        reason=text(reason,500)
        if status=='completed' and case.needs.filter(fulfilled__lt=F('confirmed')).exists(): fail('Confirmed needs have not been fulfilled.')
        old=case.status; case.status=status; case.version+=1
        if not case.first_response and status=='reviewing': case.first_response=timezone.now()
        case.save(); audit(actor,'case_transition',case.pk,reason,before=old,after=status)
        Note.objects.create(case=case,author=actor,text=reason,member_visible=True)
        Outbox.objects.get_or_create(kind='case_'+status,reference=f'{case.pk}:{case.version}',defaults={'user':case.user,'recipient':case.email})
    return case

@transaction.atomic
def approve_grant(actor,case,data):
    require(actor,'reviewer','admin')
    if case.user_id==actor.id: fail('Cannot approve your own application.','conflict',403)
    kind=data.get('kind','credit'); amount=integer(data.get('amount_cents',0)); budget=None
    if kind not in ['credit','free','discount']: fail('Invalid grant type')
    if kind=='credit':
        if not amount: fail('Credit must be positive')
        budget=Budget.objects.select_for_update().get(pk=data.get('budget_id'))
        if budget.funded_cents-budget.committed_cents<amount: fail('Insufficient funded budget.','budget')
        budget.committed_cents+=amount; budget.save()
    from django.utils.dateparse import parse_datetime
    expires=parse_datetime(data.get('expires_at',''))
    if not expires or timezone.is_naive(expires) or expires<=timezone.now(): fail('A future timezone-aware expiry is required.')
    products=list(Product.objects.filter(pk__in=data.get('products',[])))
    categories=data.get('categories',[])
    if not products and not categories: fail('Aid must be restricted to products or categories.')
    if Grant.objects.filter(case__household=case.household,kind=kind,active=True,expires_at__gt=timezone.now()).exists() and not data.get('exception_reason'): fail('Household already has an active grant; a reasoned exception is required.')
    grant=Grant.objects.create(user=case.user,case=case,reviewer=actor,budget=budget,kind=kind,granted_cents=amount,expires_at=expires,reason=text(data.get('reason',''),500),source=text(data.get('source',''),180),categories=categories,quantity_limit=integer(data.get('quantity_limit',1),1,10000))
    grant.products.set(products); AidLedger.objects.create(grant=grant,kind='granted',amount_cents=amount,reference=str(case.pk)); audit(actor,'grant_approve',grant.pk,grant.reason)
    return grant

@transaction.atomic
def adjust_stock(actor,lot,delta,hold_delta,reason,kind='receipt'):
    require(actor,'warehouse','admin')
    reason=text(reason,500); lot=Lot.objects.select_for_update().get(pk=lot.pk)
    if not isinstance(delta,int) or not isinstance(hold_delta,int): fail('Invalid quantity')
    if lot.on_hand+delta<lot.reserved+lot.hold+hold_delta or lot.hold+hold_delta<0: fail('Stock adjustment would violate reserved/hold quantities.')
    lot.on_hand+=delta; lot.hold+=hold_delta; lot.save()
    StockMovement.objects.create(lot=lot,actor=actor,kind=kind,quantity=delta,reference=str(lot.pk),reason=reason)
    audit(actor,'stock_'+kind,lot.pk,reason,delta=delta,hold_delta=hold_delta)
    return lot

@transaction.atomic
def reserve_lot(lot_id,quantity,purpose,order=None):
    lot=Lot.objects.select_for_update().get(pk=lot_id)
    if lot.purpose!=purpose or (lot.expires_at and lot.expires_at<=timezone.now()): fail('Lot purpose/expiry is ineligible.','stock')
    changed=Lot.objects.filter(pk=lot.pk,on_hand__gte=F('reserved')+F('hold')+quantity).update(reserved=F('reserved')+quantity)
    if not changed: fail('Insufficient available inventory.','stock',409)
    r=Reservation.objects.create(lot=lot,quantity=quantity,order=order,expires_at=order.expires_at if order else timezone.now()+timedelta(days=config('aid_reservation_days',7)))
    StockMovement.objects.create(lot=lot,actor=order.user if order else None,kind='reserve',quantity=quantity,reference=str(r.pk),reason=purpose)
    return r

@transaction.atomic
def allocate(actor,plan,need,lot_id,quantity):
    require(actor,'reviewer','admin')
    if need.case.user_id==actor.id: fail('Self approval is prohibited.','conflict',403)
    need=Need.objects.select_for_update().get(pk=need.pk); integer(quantity,1,10000)
    if plan.state not in ['approved','active']:fail('Plan must be approved or active before resource allocation.')
    if not plan.needs.filter(pk=need.pk).exists(): fail('Need must be linked to this plan.')
    if quantity>need.gap: fail('Allocation exceeds confirmed gap.')
    lot=Lot.objects.get(pk=lot_id)
    if lot.product.unit!=need.unit: fail('Units do not match.')
    r=reserve_lot(lot.pk,quantity,'aid'); need.allocated+=quantity; need.save()
    a=Allocation.objects.create(plan=plan,need=need,reservation=r); audit(actor,'allocate',a.pk); return a

@transaction.atomic
def fulfill_allocation(actor,allocation):
    require(actor,'warehouse','admin')
    a=Allocation.objects.select_for_update().select_related('reservation','need').get(pk=allocation.pk)
    if a.fulfilled: return a
    r=a.reservation
    if r.status!='reserved' or (r.expires_at and r.expires_at<=timezone.now()):fail('Aid reservation expired or was released.')
    Lot.objects.filter(pk=r.lot_id).update(on_hand=F('on_hand')-r.quantity,reserved=F('reserved')-r.quantity)
    r.status='fulfilled'; r.save(); a.fulfilled=True; a.save()
    Need.objects.filter(pk=a.need_id).update(fulfilled=F('fulfilled')+r.quantity)
    StockMovement.objects.create(lot=r.lot,actor=actor,kind='aid_fulfill',quantity=-r.quantity,reference=str(a.pk),reason='Confirmed handover')
    audit(actor,'aid_fulfill',a.pk); return a

def quote(user,data):
    lines=data.get('items',[])
    if not isinstance(lines,list) or not 1<=len(lines)<=30 or not all(isinstance(line,dict) for line in lines): fail('Cart must contain 1–30 items.')
    zip_code=text(data.get('zip',''),10); method=data.get('method','pickup')
    shipping=config('shipping',{'zips':[],'pickup_cents':0,'delivery_cents':None})
    if method not in ['pickup','delivery']: fail('Unknown fulfillment method.')
    if method=='delivery' and (zip_code not in shipping['zips'] or shipping.get('delivery_cents') is None): fail('Delivery is not configured for this ZIP.','region')
    volunteer=volunteer_valid(user); result=[]; seen=set()
    grant=active_grants(user).filter(pk=data['grant_id']).first() if data.get('grant_id') else None
    if data.get('grant_id') and not grant: fail('Grant is unavailable or expired.','eligibility')
    remaining=grant.available if grant and grant.kind=='credit' else 0; free_used=0
    for line in sorted(lines,key=lambda l:str(l.get('product_id',''))):
        p=Product.objects.filter(pk=line.get('product_id'),status='published').first()
        if not p or p.kind!='physical' or p.price_cents is None: fail('Only published physical products may enter checkout.')
        if p.pk in seen: fail('Duplicate product line')
        seen.add(p.pk); quantity=integer(line.get('quantity'),1,100)
        prices=[p.price_cents]; rule='public'
        if volunteer and p.volunteer_price_cents is not None: prices.append(p.volunteer_price_cents)
        care=active_grants(user,'discount')
        if any(eligible(g,p) for g in care) and p.care_price_cents is not None: prices.append(p.care_price_cents)
        price=min(prices); rule='eligible_lowest' if price!=p.price_cents else 'public'
        aid=0
        if grant and eligible(grant,p):
            if grant.kind=='free':
                if grant.quantity_used+free_used+quantity>grant.quantity_limit: fail('Free-item quantity limit exceeded.')
                aid=price*quantity; free_used+=quantity
            elif grant.kind=='credit': aid=min(price*quantity,remaining); remaining-=aid
        lot=Lot.objects.filter(product=p,purpose='aid' if grant and grant.kind=='free' else 'sale').filter(Q(expires_at__isnull=True)|Q(expires_at__gt=timezone.now())).filter(on_hand__gte=F('reserved')+F('hold')+quantity).order_by('expires_at','created_at').first()
        if not lot: fail('Insufficient confirmed inventory.','stock',409)
        result.append({'product_id':str(p.pk),'lot_id':str(lot.pk),'name':p.name,'merchant_id':str(p.merchant_id) if p.merchant_id else None,'seller':p.merchant.name if p.merchant else 'Unconfigured','fulfiller':p.fulfiller,'quantity':quantity,'unit':p.unit,'unit_price_cents':price,'aid_cents':aid,'cash_cents':price*quantity-aid,'version':p.version,'rule':rule,'donation_bps':p.donation_bps,'donation_fixed_cents':p.donation_fixed_cents,'donation_rule_version':p.donation_rule_version})
    sellers={(l['merchant_id'],l['fulfiller']) for l in result}
    fee=(shipping.get(method+'_cents') or 0)*len(sellers)
    tax=config('sandbox_tax_bps',0)
    cash=sum(l['cash_cents'] for l in result); aid=sum(l['aid_cents'] for l in result)
    tax_cents=cash*tax//10000
    q={'items':result,'shipping_cents':fee,'tax_cents':tax_cents,'tax_label':'Sandbox test tax only; live tax is unconfigured','total_cents':cash+aid+fee+tax_cents,'cash_cents':cash+fee+tax_cents,'aid_cents':aid,'grant_id':str(grant.pk) if grant else None,'zip':zip_code,'method':method,'sandbox':True}
    q['fingerprint']=hashlib.sha256(json.dumps(q,sort_keys=True).encode()).hexdigest()
    return q

@transaction.atomic
def create_order(user,data,key):
    existing=Order.objects.filter(user=user,idempotency_key=key).first()
    if existing:return existing
    q=quote(user,data)
    if q['fingerprint']!=data.get('fingerprint'):fail('Prices or eligibility changed. Review and confirm a fresh quote.','requote',409)
    grant=Grant.objects.select_for_update().get(pk=q['grant_id']) if q['grant_id'] else None
    if grant and grant.kind=='credit':
        if grant.available<q['aid_cents']: fail('Insufficient aid balance.','credit',409)
        grant.reserved_cents+=q['aid_cents'];grant.save();AidLedger.objects.create(grant=grant,kind='reserve',amount_cents=-q['aid_cents'],reference=key)
    if grant and grant.kind=='free':
        quantity=sum(l['quantity'] for l in q['items'] if l['aid_cents'])
        if grant.quantity_used+quantity>grant.quantity_limit: fail('Free allocation limit reached.')
        grant.quantity_used+=quantity;grant.save()
    order=Order.objects.create(user=user,total_cents=q['total_cents'],cash_cents=q['cash_cents'],aid_cents=q['aid_cents'],shipping_cents=q['shipping_cents'],tax_cents=q['tax_cents'],quote_snapshot=q,grant=grant,expires_at=timezone.now()+timedelta(minutes=config('reservation_minutes',15)),zip=q['zip'],method=q['method'],address=text(data.get('address',''),500,False),idempotency_key=key)
    if order.method=='delivery' and not order.address: fail('Delivery address is required.')
    subs={}
    for l in q['items']:
        merchant_key=(l['merchant_id'],l['fulfiller'])
        if merchant_key not in subs:
            subs[merchant_key]=Suborder.objects.create(order=order,merchant_id=l['merchant_id'],fulfiller=l['fulfiller'],shipping_cents=q['shipping_cents']//len({(x['merchant_id'],x['fulfiller']) for x in q['items']}))
        reserve_lot(l['lot_id'],l['quantity'],'aid' if grant and grant.kind=='free' and l['aid_cents'] else 'sale',order)
        basis=l['cash_cents']; expected=(basis*(l['donation_bps'] or 0)//10000)+(l['donation_fixed_cents'] or 0)*l['quantity'] if basis else 0
        item=Item.objects.create(suborder=subs[merchant_key],product_id=l['product_id'],lot_id=l['lot_id'],quantity=l['quantity'],unit_price_cents=l['unit_price_cents'],cash_cents=l['cash_cents'],aid_cents=l['aid_cents'],donation_basis_cents=basis,donation_estimated_cents=expected,snapshot=l)
        if expected:FinanceEntry.objects.create(bucket='corporate_donation',kind='estimated',amount_cents=expected,reference=str(item.pk),organization_id=l['merchant_id'])
    audit(user,'order_create',order.pk)
    if order.cash_cents==0: settle_order(order,'zero_'+str(order.pk))
    return order

@transaction.atomic
def release_order(order,reason='expired'):
    order=Order.objects.select_for_update().get(pk=order.pk)
    if order.released or order.payment_status not in ['pending','cancelled','expired']:return order
    for r in Reservation.objects.select_for_update().filter(order=order,status='reserved'):
        Lot.objects.filter(pk=r.lot_id).update(reserved=F('reserved')-r.quantity);r.status='released';r.save()
        StockMovement.objects.create(lot=r.lot,actor=order.user,kind='release',quantity=-r.quantity,reference=str(r.pk),reason=reason)
    if order.grant_id:
        if order.grant.kind=='credit':
            Grant.objects.filter(pk=order.grant_id).update(reserved_cents=F('reserved_cents')-order.aid_cents)
            AidLedger.objects.create(grant=order.grant,kind='release',amount_cents=order.aid_cents,reference=str(order.pk))
        elif order.grant.kind=='free':
            qty=sum(l['quantity'] for l in order.quote_snapshot['items'] if l['aid_cents'])
            Grant.objects.filter(pk=order.grant_id).update(quantity_used=F('quantity_used')-qty)
    order.released=True;order.payment_status='cancelled' if reason=='cancelled' else 'expired';order.save();return order

@transaction.atomic
def settle_order(order,external_id):
    order=Order.objects.select_for_update().get(pk=order.pk)
    if order.payment_status in ['paid','manual_review']:return order
    if order.released or order.expires_at<=timezone.now():
        release_order(order)
        # Late payments are recorded, never silently fulfilled; finance must refund or reallocate.
        order.refresh_from_db();order.payment_status='manual_review';order.save()
        FinanceEntry.objects.create(bucket='commerce',kind='late_payment',amount_cents=order.cash_cents,reference=str(order.pk),external_id=external_id)
        return order
    order.payment_status='paid';order.save()
    if order.grant_id and order.grant.kind=='credit':
        Grant.objects.filter(pk=order.grant_id).update(reserved_cents=F('reserved_cents')-order.aid_cents,redeemed_cents=F('redeemed_cents')+order.aid_cents)
        AidLedger.objects.create(grant=order.grant,kind='redeem',amount_cents=-order.aid_cents,reference=str(order.pk))
    FinanceEntry.objects.create(bucket='commerce',kind='payment',amount_cents=order.cash_cents,reference=str(order.pk),external_id=external_id)
    Outbox.objects.get_or_create(kind='order_paid',reference=str(order.pk),defaults={'user':order.user,'recipient':order.user.email})
    return order

@transaction.atomic
def pickup_issue(actor,sub):
    if actor.id!=sub.order.user_id:require(actor,'warehouse','admin')
    if sub.order.payment_status!='paid' or sub.order.method!='pickup' or sub.status=='fulfilled': fail('Pickup is unavailable.')
    token=secrets.token_urlsafe(32)
    Pickup.objects.update_or_create(suborder=sub,defaults={'token_hash':hashlib.sha256(token.encode()).hexdigest(),'revoked':False,'used_at':None})
    return token

@transaction.atomic
def fulfill_suborder(actor,sub,token=None,tracking=''):
    require(actor,'warehouse','merchant','admin')
    if not actor.is_superuser and actor.groups.filter(name='merchant').exists() and not actor.groups.filter(name__in=['warehouse','admin']).exists() and (not sub.merchant or sub.merchant.user_id!=actor.id):fail('Not found.','not_found',404)
    sub=Suborder.objects.select_for_update().select_related('order').get(pk=sub.pk)
    if sub.status=='fulfilled':fail('Already fulfilled.','already_used',409)
    if sub.order.payment_status!='paid':fail('Payment is not confirmed.')
    if sub.order.method=='pickup':
        pickup=Pickup.objects.select_for_update().filter(suborder=sub,token_hash=hashlib.sha256((token or '').encode()).hexdigest(),used_at__isnull=True,revoked=False).first()
        if not pickup:fail('Invalid or used pickup code.','token',409)
        pickup.used_at=timezone.now();pickup.save()
    elif not tracking:fail('Delivery confirmation / tracking is required.')
    for item in sub.items.all():
        r=Reservation.objects.select_for_update().get(order=sub.order,lot=item.lot,status='reserved')
        Lot.objects.filter(pk=item.lot_id).update(on_hand=F('on_hand')-r.quantity,reserved=F('reserved')-r.quantity)
        r.status='fulfilled';r.save();StockMovement.objects.create(lot=item.lot,actor=actor,kind='fulfill',quantity=-r.quantity,reference=str(sub.pk),reason='Pickup / shipment confirmation')
    sub.status='fulfilled';sub.tracking=tracking;sub.save()
    if not sub.order.suborders.exclude(status='fulfilled').exists():sub.order.fulfillment_status='fulfilled';sub.order.save()
    audit(actor,'fulfill',sub.pk);return sub

@transaction.atomic
def submit_campaign(actor,c):
    require(actor,'admin')
    if c.status not in ['draft','paused']: fail('Campaign cannot be submitted in this state.')
    if not c.policy or not c.budget or not c.consent_basis or not c.execution:fail('Policies, budget, consent basis and execution plan are required.')
    c.status='submitted_for_review';c.save();audit(actor,'campaign_submit',c.pk);return c

@transaction.atomic
def campaign_action(actor,c,action,reason=''):
    require(actor,'admin','reviewer')
    c=Campaign.objects.select_for_update().get(pk=c.pk)
    if action=='approve':
        if c.owner_id==actor.id:fail('A second reviewer must approve publication.','conflict',403)
        if c.status!='submitted_for_review':fail('Submit for review first.')
        if not c.policy or not c.budget or c.target_cents<=0:fail('Required policies/budget are incomplete.')
        c.approver=actor;c.version+=1;c.status='approved'
        PolicyVersion.objects.create(campaign=c,number=c.version,approved_by=actor,snapshot={'policy':c.policy,'target_cents':c.target_cents,'starts_at':c.starts_at.isoformat(),'ends_at':c.ends_at.isoformat(),'allow_overfund':c.allow_overfund,'budget':c.budget})
    elif action=='publish':
        if c.status!='approved' or not c.approver:fail('Approved policy required.')
        c.status='scheduled' if c.starts_at>timezone.now() else 'published'
    elif action in ['pause','close','cancel','complete']:
        reason=text(reason,500)
        targets={'pause':'paused','close':'closed','cancel':'cancelled','complete':'completed'}
        if action=='complete' and c.status not in ['closed','paused']:fail('Close campaign first.')
        c.status=targets[action]
        if action=='cancel':
            for d in c.donations.filter(status='succeeded'):
                d.needs_review=True;d.save();Outbox.objects.get_or_create(kind='campaign_cancelled',reference=str(d.pk),defaults={'recipient':d.email,'user':d.user})
    else:fail('Invalid campaign action')
    c.save();audit(actor,'campaign_'+action,c.pk,reason);return c

def campaign_totals(c):
    qs=c.donations.filter(status='succeeded')
    sums=qs.aggregate(gross=Sum('amount_cents'),refunds=Sum('refunded_cents'),chargebacks=Sum('chargeback_cents'),disputes=Sum('disputed_cents'))
    sums={k:v or 0 for k,v in sums.items()}
    sums['confirmed']=sums['gross']-sums['refunds']-sums['chargebacks'];sums['count']=qs.count()
    sums['percent']=round(sums['confirmed']*100/c.target_cents,1)
    sums['bar']=min(100,sums['percent'])
    entries=FinanceEntry.objects.filter(campaign=c)
    for name in ['fee','settlement','expense_paid','expense_reserved','reserve']:
        sums[name]=entries.filter(kind=name).aggregate(n=Sum('amount_cents'))['n'] or 0
    sums['pending_refunds']=Refund.objects.filter(donation__campaign=c,status='approved').aggregate(n=Sum('amount_cents'))['n'] or 0
    sums['spendable']=sums['settlement']-sums['expense_paid']-sums['expense_reserved']-sums['reserve']-sums['disputes']-sums['refunds']-sums['chargebacks']-sums['pending_refunds']
    return sums

@transaction.atomic
def donation_checkout(user,data,key):
    existing=Donation.objects.filter(idempotency_key=key).first()
    if existing:
        if not user.is_authenticated or existing.user_id!=user.id:fail('Idempotency key already used.','conflict',409)
        return existing,None
    c=Campaign.objects.select_for_update().get(pk=data.get('campaign_id'))
    now=timezone.now()
    if c.status!='published' or c.starts_at>now or c.ends_at<=now:fail('This project is not accepting donations.','closed',409)
    if not c.allow_overfund and campaign_totals(c)['confirmed']>=c.target_cents:fail('Goal reached; new checkouts are paused.','goal',409)
    amount=integer(data.get('amount_cents'),c.minimum_cents,c.maximum_cents)
    policy=c.policies.order_by('-number').first()
    if not policy:fail('No approved policy.')
    if policy.snapshot['target_cents']!=c.target_cents or policy.snapshot['policy']!=c.policy:fail('Material changes require review.')
    if data.get('policy_version')!=policy.number or not data.get('policy_consent'):fail('Read and accept the current campaign policy.')
    token=secrets.token_urlsafe(32)
    d=Donation.objects.create(campaign=c,user=user if user.is_authenticated else None,amount_cents=amount,email=text(data.get('email',''),254),receipt_name=text(data.get('receipt_name',''),180),message=text(data.get('message',''),1000,False),anonymous=data.get('anonymous',True),marketing=bool(data.get('marketing',False)),policy_snapshot=policy.snapshot,expires_at=now+timedelta(minutes=30),access_hash=hashlib.sha256(token.encode()).hexdigest(),idempotency_key=key)
    audit(user,'donation_checkout',d.pk)
    return d,token

@transaction.atomic
def succeed_donation(d,event_id):
    d=Donation.objects.select_for_update().select_related('campaign').get(pk=d.pk)
    if d.status=='succeeded':return d
    d.status='succeeded';d.needs_review=d.expires_at<timezone.now() or d.campaign.status not in ['published','scheduled'] or d.campaign.ends_at<=timezone.now();d.save()
    FinanceEntry.objects.create(bucket='public_donation',kind='payment',amount_cents=d.amount_cents,reference=str(d.pk),campaign=d.campaign,external_id=event_id)
    Receipt.objects.get_or_create(donation=d,defaults={'snapshot':{'id':str(d.pk),'campaign':d.campaign.name,'amount_cents':d.amount_cents,'date':timezone.now().isoformat(),'sandbox':True,'notice':'SANDBOX confirmation — no funds collected; no tax deductibility claim.'}})
    Outbox.objects.get_or_create(kind='donation_receipt',reference=str(d.pk),defaults={'recipient':d.email,'user':d.user})
    return d

@transaction.atomic
def request_refund(actor,data):
    require(actor,'finance','admin'); reason=text(data.get('reason',''),500)
    amount=integer(data.get('amount_cents',0)); aid=integer(data.get('aid_cents',0))
    if amount+aid==0: fail('Refund must be positive.')
    external=text(data.get('idempotency_key',''),180)
    existing=Refund.objects.filter(external_id=external).first()
    if existing:return existing
    donation=None;order=None;item=None;shipping=0;tax=0
    if data.get('donation_id'):
        donation=Donation.objects.select_for_update().get(pk=data['donation_id'])
        pending=Refund.objects.filter(donation=donation,status='approved').aggregate(n=Sum('amount_cents'))['n'] or 0
        if donation.status!='succeeded' or amount>donation.amount_cents-donation.refunded_cents-donation.chargeback_cents-donation.disputed_cents-pending or aid:fail('Invalid donation refund amount.')
    elif data.get('order_id') and not data.get('item_id'):
        order=Order.objects.select_for_update().get(pk=data['order_id'])
        shipping=integer(data.get('shipping_cents',0));tax=integer(data.get('tax_cents',0))
        prior=Refund.objects.filter(order=order,item__isnull=True,status__in=['approved','succeeded']).aggregate(s=Sum('shipping_cents'),t=Sum('tax_cents'))
        if order.payment_status not in ['paid','manual_review'] or aid or amount!=shipping+tax or shipping>order.shipping_cents-(prior['s'] or 0) or tax>order.tax_cents-(prior['t'] or 0):fail('Charge refund exceeds shipping/tax originally paid.')
    else:
        item=Item.objects.select_for_update().select_related('suborder__order').get(pk=data.get('item_id'));order=item.suborder.order
        pending=Refund.objects.filter(item=item,status='approved').aggregate(c=Sum('amount_cents'),a=Sum('aid_cents'))
        if order.payment_status not in ['paid','manual_review'] or amount>item.cash_cents-item.refunded_cash_cents-(pending['c'] or 0) or aid>item.aid_cents-item.refunded_aid_cents-(pending['a'] or 0):fail('Refund exceeds original source balances.')
        # Mixed-source refunds must restore each source proportionately.
        total=item.cash_cents+item.aid_cents
        expected=(amount+aid)*item.aid_cents//total if total else 0
        if order.payment_status=='manual_review':
            if aid:fail('Late payment has no redeemed aid to refund.')
        elif abs(aid-expected)>1: fail('Refund must return cash and aid proportionately to original sources.')
    r=Refund.objects.create(order=order,item=item,donation=donation,amount_cents=amount,aid_cents=aid,reason=reason,approver=actor,external_id=external,shipping_cents=shipping,tax_cents=tax)
    audit(actor,'refund_approve',r.pk,reason);return r

@transaction.atomic
def confirm_refund(r,success):
    r=Refund.objects.select_for_update().get(pk=r.pk)
    if r.status!='approved':return r
    r.status='succeeded' if success else 'failed';r.save()
    if not success:return r
    if r.donation_id:
        d=Donation.objects.select_for_update().get(pk=r.donation_id);d.refunded_cents+=r.amount_cents;d.save()
        FinanceEntry.objects.create(bucket='public_donation',kind='refund',amount_cents=-r.amount_cents,reference=str(r.pk),campaign=d.campaign)
        Outbox.objects.get_or_create(kind='donation_correction',reference=str(r.pk),defaults={'recipient':d.email,'user':d.user})
    elif not r.item_id:
        FinanceEntry.objects.create(bucket='commerce',kind='refund',amount_cents=-r.amount_cents,reference=str(r.pk))
        r.order.refund_status='partial';r.order.save()
    else:
        item=Item.objects.select_for_update().get(pk=r.item_id); old=item.donation_estimated_cents
        item.refunded_cash_cents+=r.amount_cents;item.refunded_aid_cents+=r.aid_cents
        basis=item.cash_cents-item.refunded_cash_cents
        # Proportionate fixed-per-unit commitment, without altering the original price/rule snapshot.
        item.donation_estimated_cents=(basis*(item.snapshot.get('donation_bps') or 0)//10000)+(item.snapshot.get('donation_fixed_cents') or 0)*item.quantity*basis//max(1,item.cash_cents) if basis else 0
        item.save();delta=item.donation_estimated_cents-old
        if delta:FinanceEntry.objects.create(bucket='corporate_donation',kind='adjusted',amount_cents=delta,reference=str(item.pk),organization=item.suborder.merchant)
        order=r.order;order.refund_status='partial';order.save()
        if r.aid_cents and order.grant and order.grant.kind=='credit':
            Grant.objects.filter(pk=order.grant_id).update(redeemed_cents=F('redeemed_cents')-r.aid_cents)
            AidLedger.objects.create(grant=order.grant,kind='refund',amount_cents=r.aid_cents,reference=str(r.pk))
        FinanceEntry.objects.create(bucket='commerce',kind='refund',amount_cents=-r.amount_cents,reference=str(r.pk))
    if r.order_id:
        total=Refund.objects.filter(order=r.order,status='succeeded').aggregate(c=Sum('amount_cents'),a=Sum('aid_cents'))
        if (total['c'] or 0)+(total['a'] or 0)>=r.order.total_cents:r.order.refund_status='full';r.order.save()
    return r

@transaction.atomic
def process_event(payload):
    event_id=text(payload.get('event_id',''),180); purpose=payload.get('purpose'); kind=payload.get('kind')
    digest=hashlib.sha256(json.dumps(payload,sort_keys=True).encode()).hexdigest()
    old=PaymentEvent.objects.filter(event_id=event_id).first()
    if old:
        if old.payload_digest!=digest:fail('Event ID payload mismatch.','conflict',409)
        return old
    ref=payload.get('reference')
    if purpose=='commerce' and kind=='succeeded':
        order=Order.objects.get(pk=ref)
        if payload.get('amount_cents')!=order.cash_cents:fail('Amount mismatch.')
        settle_order(order,event_id)
    elif purpose=='public_donation' and kind=='succeeded':
        d=Donation.objects.get(pk=ref)
        if payload.get('amount_cents')!=d.amount_cents:fail('Amount mismatch.')
        succeed_donation(d,event_id)
    elif purpose=='refund' and kind in ['succeeded','failed']:
        r=Refund.objects.get(pk=ref)
        if payload.get('amount_cents')!=r.amount_cents:fail('Amount mismatch.')
        confirm_refund(r,kind=='succeeded')
    elif purpose in ['commerce','public_donation'] and kind in ['failed','cancelled']:
        if purpose=='commerce':
            obj=Order.objects.get(pk=ref)
            if obj.payment_status=='pending':release_order(obj,'cancelled')
        else:
            obj=Donation.objects.select_for_update().get(pk=ref)
            if obj.status=='pending':obj.status=kind;obj.save()
    elif purpose=='public_donation' and kind in ['dispute_open','dispute_lost','dispute_won','dispute_restored']:
        d=Donation.objects.get(pk=ref,status='succeeded')
        dispute_event(d,text(payload.get('dispute_id',''),180),integer(payload.get('amount_cents'),1),kind.split('_',1)[1])
    else:fail('Unsupported payment event.')
    return PaymentEvent.objects.create(event_id=event_id,purpose=purpose,reference=ref,kind=kind,payload_digest=digest)

@transaction.atomic
def dispute_event(donation,external_id,amount,status):
    """Apply only verified provider events. Open disputes freeze spendable funds, not confirmed gross."""
    d=Donation.objects.select_for_update().get(pk=donation.pk)
    dispute=Dispute.objects.select_for_update().filter(external_id=external_id).first()
    if not dispute:
        if status!='open':fail('Dispute must open before resolution.')
        integer(amount,1,d.amount_cents-d.refunded_cents-d.chargeback_cents-d.disputed_cents)
        dispute=Dispute.objects.create(donation=d,external_id=external_id,amount_cents=amount,status='open');d.disputed_cents+=amount
    else:
        if dispute.donation_id!=d.pk or dispute.amount_cents!=amount:fail('Dispute reference/amount mismatch.')
        if dispute.status==status:return dispute
        if dispute.status=='open' and status in ['lost','won']:
            d.disputed_cents-=amount
            if status=='lost':d.chargeback_cents+=amount
        elif dispute.status=='lost' and status=='restored':d.chargeback_cents-=amount
        else:fail('Invalid dispute transition.')
        dispute.status=status;dispute.save()
    d.save();FinanceEntry.objects.create(bucket='public_donation',kind='dispute_'+status,amount_cents=-amount if status=='lost' else amount if status=='restored' else 0,reference=str(dispute.pk),campaign=d.campaign,external_id=external_id)
    return dispute


@transaction.atomic
def release_allocation(allocation,reason):
    a=Allocation.objects.select_for_update().select_related('reservation').get(pk=allocation.pk)
    r=Reservation.objects.select_for_update().get(pk=a.reservation_id)
    if r.status!='reserved' or a.fulfilled:return a
    Lot.objects.filter(pk=r.lot_id).update(reserved=F('reserved')-r.quantity)
    Need.objects.filter(pk=a.need_id).update(allocated=F('allocated')-r.quantity)
    r.status='released';r.save()
    StockMovement.objects.create(lot=r.lot,actor=None,kind='aid_release',quantity=-r.quantity,reference=str(a.pk),reason=reason)
    audit(None,'aid_release',a.pk,reason)
    Outbox.objects.get_or_create(kind='aid_reservation_released',reference=str(a.pk),defaults={'user':a.need.case.user,'recipient':a.need.case.email})
    return a
