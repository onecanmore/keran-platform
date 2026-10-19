import csv, hashlib, hmac, io, json, secrets
from datetime import timedelta
from functools import wraps
from django.conf import settings
from django.contrib.auth.models import User
from django.core.exceptions import ObjectDoesNotExist,ValidationError
from django.core.validators import validate_email
from django.http import JsonResponse,HttpResponse,FileResponse,Http404
from django.http.response import HttpResponseBase
from django.db import transaction,IntegrityError
from django.db.models import Q,F,Sum
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django.core import signing
from .models import *
from .services import *
from .reports import rows_for,sort_rows,report_totals

def endpoint(fn):
    @wraps(fn)
    def wrapped(request,*args,**kwargs):
        try:
            if request.method not in ['GET','POST']:return JsonResponse({'error':{'code':'method','message':'Method not allowed'}},status=405)
            request.data=json.loads(request.body or b'{}') if request.method=='POST' and request.content_type=='application/json' else request.POST.dict()
            if not isinstance(request.data,dict):fail('JSON body must be an object.')
            mutation_key=request.headers.get('Idempotency-Key','') if request.method=='POST' else ''
            if mutation_key and request.content_type=='application/json' and fn.__name__ not in ['webhook','sandbox_pay']:
                if len(mutation_key)>100:fail('Idempotency key too long.')
                # Scope includes actor and endpoint; the same key cannot mutate a second payload.
                scope=f'{request.user.pk}:{request.path}'
                digest=hashlib.sha256(request.body).hexdigest()
                with transaction.atomic():
                    prior=Mutation.objects.select_for_update().filter(scope=scope,key=mutation_key).first()
                    if prior:
                        if prior.digest!=digest:fail('Idempotency key payload mismatch.','conflict',409)
                        return JsonResponse({'data':prior.result})
                    result=fn(request,*args,**kwargs)
                    if not isinstance(result,HttpResponseBase):Mutation.objects.create(scope=scope,key=mutation_key,digest=digest,result=result)
            else:result=fn(request,*args,**kwargs)
            return result if isinstance(result,HttpResponseBase) else JsonResponse({'data':result},safe=False)
        except DomainError as e:
            if e.status==403 and request.user.is_authenticated:audit(request.user,'mutation_denied',request.path,e.code)
            return JsonResponse({'error':{'code':e.code,'message':e.message}},status=e.status)
        except (ObjectDoesNotExist,Http404):return JsonResponse({'error':{'code':'not_found','message':'Not found.'}},status=404)
        except (ValueError,TypeError,KeyError,ValidationError,IntegrityError) as e:return JsonResponse({'error':{'code':'invalid','message':'Invalid request. Check required fields and constraints.'}},status=400)
    return wrapped

def post(request):
    if request.method!='POST':fail('POST required.','method',405)
def member(request):
    if not request.user.is_authenticated:fail('Please sign in.','authentication',401)
def key(request):return text(request.headers.get('Idempotency-Key',request.data.get('idempotency_key','')),100)
def case_json(c,private=False):
    d={'id':str(c.pk),'status':c.status,'version':c.version,'state':c.state,'city':c.city,'zip':c.zip,'outside_region':c.outside_region,'contact_status':c.contact_status,'created_at':c.created_at.isoformat(),'needs':[{'id':str(n.pk),'name':n.name,'unit':n.unit,'requested':n.requested,'confirmed':n.confirmed,'allocated':n.allocated,'fulfilled':n.fulfilled,'gap':n.gap} for n in c.needs.all()]}
    if private:d.update(message=c.message,email=c.email,phone=c.phone,notes=[{'text':n.text,'created_at':n.created_at.isoformat()} for n in c.notes.all()])
    return d

@endpoint
def catalogue(request):
    qs=Product.objects.filter(status='published')
    if request.GET.get('q'):qs=qs.filter(Q(name__icontains=request.GET['q'])|Q(name_zh__icontains=request.GET['q']))
    for field in ['kind','category','source']:
        if request.GET.get(field):qs=qs.filter(**{field:request.GET[field]})
    if request.GET.get('max_price'):qs=qs.filter(price_cents__lte=int(request.GET['max_price']))
    data=[{'id':str(p.pk),'slug':p.slug,'name':p.name,'name_zh':p.name_zh,'kind':p.kind,'price_cents':p.price_cents,'is_demo':p.is_demo} for p in qs]
    return paginated(data,request)
def paginated(rows,request):
    page=max(1,int(request.GET.get('page',1)));size=min(100,max(1,int(request.GET.get('page_size',20))))
    return {'results':rows[(page-1)*size:page*size],'count':len(rows),'page':page,'page_size':size}

@endpoint
def cases(request,pk=None,action=None):
    if not request.user.is_authenticated and not pk and request.method=='POST':
        request.session['help_draft']=request.data
        return {'redirect':'/login/?next=/help/new/','notice':'Private draft saved in this session. Sign in to submit.'}
    member(request)
    if not pk:
        if request.method=='POST':
            c=submit_case(request.user,request.data,bool(request.data.get('draft')));request.session.pop('help_draft',None);return case_json(c)
        return paginated([case_json(c) for c in case_scope(request.user).order_by('-created_at')],request)
    c=case_scope(request.user).get(pk=pk)
    if request.method=='GET':
        d=case_json(c,True)
        if c.user_id==request.user.id:d['notes']=[{'text':n.text,'created_at':n.created_at.isoformat()} for n in c.notes.filter(member_visible=True)]
        return d
    post(request);data=request.data
    if action=='submit':
        if c.user_id!=request.user.id or c.status!='draft':fail('Not found.','not_found',404)
        if not data.get('contact_consent'):fail('Contact consent is required.')
        Consent.objects.filter(case=c,kind='contact').update(granted=True);c.status='received';c.save();audit(request.user,'case_draft_submit',c.pk);Outbox.objects.get_or_create(kind='case_received',reference=str(c.pk),defaults={'user':c.user,'recipient':c.email});return case_json(c)
    if action=='transition':return case_json(transition_case(request.user,c,data.get('status'),data.get('reason')))
    if action=='supplement':
        if c.user_id!=request.user.id:fail('Not found.','not_found',404)
        note=Note.objects.create(case=c,author=request.user,text=text(data.get('text',''),3000),member_visible=True)
        audit(request.user,'case_supplement',c.pk);return {'id':str(note.pk)}
    if action=='note':
        require(request.user,'caseworker','reviewer','admin')
        Note.objects.create(case=c,author=request.user,text=text(data.get('text',''),3000),member_visible=bool(data.get('member_visible')));audit(request.user,'case_note',c.pk);return {'ok':True}
    if action=='assign':
        require(request.user,'admin','reviewer');u=User.objects.get(pk=data['user_id'])
        if not u.groups.filter(name__in=['caseworker','reviewer','admin']).exists() and not u.is_superuser:fail('Select a caseworker or reviewer.')
        c.assignee=u;c.save();audit(request.user,'case_assign',c.pk);return case_json(c)
    if action=='household':
        require(request.user,'reviewer','admin')
        if not data.get('confirmed_consent'):fail('Manual consent and household confirmation are required.')
        reason=text(data.get('reason',''),500);target=Household.objects.get(pk=data['household_id']);old=str(c.household_id)
        c.household=target;c.save();target.verified=True;target.save();target.members.add(c.user)
        audit(request.user,'household_link',c.pk,reason,before=old,after=str(target.pk));return case_json(c)
    if action=='confirm':
        require(request.user,'reviewer','admin')
        if c.user_id==request.user.id:fail('Self approval prohibited.','conflict',403)
        n=c.needs.get(pk=data['need_id']);q=integer(data['quantity'],0,n.requested)
        if q<n.allocated:fail('Cannot reduce below allocated quantity.')
        n.confirmed=q;n.save();c.reconfirmed_at=timezone.now();c.save();audit(request.user,'need_confirm',n.pk,text(data.get('reason',''),500));return case_json(c)
    if action=='grant':return {'id':str(approve_grant(request.user,c,data).pk)}
    fail('Unknown action')

@endpoint
def verifications(request,pk=None):
    member(request)
    if not pk:
        if request.method=='GET':return paginated(list(Verification.objects.filter(user=request.user).values('id','status','organization','reason','expires_at')),request)
        post(request)
        if not request.data.get('consent'):fail('Contact consent is required.')
        v=Verification.objects.create(user=request.user,organization=text(request.data.get('organization',''),180,False),description=text(request.data.get('description',''),3000),consent=True)
        audit(request.user,'verification_submit',v.pk);return {'id':str(v.pk),'status':v.status}
    post(request);require(request.user,'reviewer','admin');v=Verification.objects.get(pk=pk)
    if v.user_id==request.user.id:fail('Cannot review own verification.','conflict',403)
    status=request.data.get('status')
    if status not in ['under_review','needs_info','approved','rejected','expired','revoked']:fail('Invalid verification status')
    v.reason=text(request.data.get('reason',''),500);v.status=status;v.reviewer=request.user
    if status=='approved':
        days=config('verification_days',None)
        if not isinstance(days,int) or days<=0:fail('Configure verification validity before approval.')
        v.expires_at=timezone.now()+timedelta(days=days)
    v.save();audit(request.user,'verification_'+status,v.pk,v.reason);return {'id':str(v.pk),'status':v.status}

@endpoint
def checkout(request,action):
    post(request);member(request)
    if action=='quote':return quote(request.user,request.data)
    if action=='create':
        order=create_order(request.user,request.data,key(request));return {'id':str(order.pk),'sandbox_url':f'/sandbox/commerce/{order.pk}/','payment_status':order.payment_status}
    fail('Unknown checkout action')

@endpoint
def orders(request,pk=None,action=None):
    member(request)
    if not pk:
        return paginated([{'id':str(o.pk),'total_cents':o.total_cents,'payment_status':o.payment_status,'fulfillment_status':o.fulfillment_status,'sandbox':o.sandbox} for o in order_scope(request.user).order_by('-created_at')],request)
    o=order_scope(request.user).get(pk=pk)
    if request.method=='GET':
        if o.user_id!=request.user.id:require(request.user,'admin','finance','warehouse')
        return {'id':str(o.pk),'payment_status':o.payment_status,'fulfillment_status':o.fulfillment_status,'quote':o.quote_snapshot,'suborders':[{'id':str(s.pk),'status':s.status,'items':[{'id':str(i.pk),'name':i.product.name,'quantity':i.quantity,'cash_cents':i.cash_cents,'aid_cents':i.aid_cents} for i in s.items.all()]} for s in o.suborders.all()]}
    post(request)
    if action=='cancel':
        if o.user_id!=request.user.id:require(request.user,'admin','finance')
        if o.payment_status!='pending':fail('Only unpaid orders can be cancelled.')
        release_order(o,'cancelled');return {'ok':True}
    if action=='pickup':
        sub=o.suborders.get(pk=request.data['suborder_id']);return {'token':pickup_issue(request.user,sub)}
    fail('Unknown order action')

@endpoint
def fulfillment(request,pk):
    post(request);member(request)
    sub=Suborder.objects.select_related('order','merchant').get(pk=pk)
    fulfill_suborder(request.user,sub,request.data.get('token'),request.data.get('tracking',''));return {'ok':True}

@endpoint
def stock(request,pk,action):
    post(request);require(request.user,'warehouse','admin')
    lot=Lot.objects.get(pk=pk);data=request.data
    if action=='adjust':
        l=adjust_stock(request.user,lot,data.get('delta',0),data.get('hold_delta',0),data.get('reason',''));return {'available':l.available}
    if action=='return':
        quantity=integer(data.get('quantity'),1,10000)
        l=adjust_stock(request.user,lot,quantity,quantity,data.get('reason',''),'return_hold');return {'available':l.available,'hold':l.hold}
    if action=='transfer':
        reason=text(data.get('reason',''),500)
        with transaction.atomic():
            lot=Lot.objects.select_for_update().get(pk=pk);q=integer(data.get('quantity'),1,lot.available)
            if lot.restricted:fail('Restricted-purpose donations cannot change purpose.')
            purpose=data.get('purpose')
            if purpose not in ['aid','sale'] or purpose==lot.purpose:fail('Select a different purpose.')
            target=Lot.objects.create(product=lot.product,warehouse=lot.warehouse,location=lot.location,owner=lot.owner,batch=lot.batch+'-transfer',purpose=purpose,on_hand=q,expires_at=lot.expires_at)
            lot.on_hand-=q;lot.save()
            for l,qty in [(lot,-q),(target,q)]:StockMovement.objects.create(lot=l,actor=request.user,kind='purpose_transfer',quantity=qty,reference=str(target.pk),reason=reason)
            audit(request.user,'purpose_transfer',lot.pk,reason);return {'id':str(target.pk)}
    fail('Unknown stock action')

@endpoint
def allocations(request,pk=None):
    post(request);data=request.data
    if pk:
        a=Allocation.objects.get(pk=pk)
        if data.get('action')=='release':
            require(request.user,'admin','reviewer');release_allocation(a,text(data.get('reason',''),500))
        else:fulfill_allocation(request.user,a)
        return {'ok':True}
    require(request.user,'reviewer','admin');a=allocate(request.user,Plan.objects.get(pk=data['plan_id']),Need.objects.get(pk=data['need_id']),data['lot_id'],integer(data['quantity'],1,10000));return {'id':str(a.pk)}

@endpoint
def appointments(request,pk=None):
    member(request)
    if pk:
        post(request);a=Appointment.objects.get(pk=pk)
        if a.user_id==request.user.id and request.data.get('status')=='cancelled':pass
        else:require(request.user,'admin','caseworker')
        transitions={'submitted':['contacting','cancelled'],'contacting':['quoted','cancelled'],'quoted':['scheduled','cancelled'],'scheduled':['completed','cancelled']}
        if request.data.get('status') not in transitions.get(a.status,[]):fail('Invalid appointment transition')
        a.status=request.data['status'];a.save();audit(request.user,'appointment_transition',a.pk);return {'status':a.status}
    if request.method=='GET':return paginated(list(Appointment.objects.filter(user=request.user).values('id','zip','preferred','status')),request)
    post(request);data=request.data
    if data.get('zip') not in config('water_zips',[]):fail('Installation coverage is not yet confirmed for this ZIP. Contact the team.','region')
    a=Appointment.objects.create(user=request.user,zip=data['zip'],address=text(data.get('address',''),500),phone=text(data.get('phone',''),40),preferred=text(data.get('preferred',''),180))
    audit(request.user,'appointment_submit',a.pk);return {'id':str(a.pk),'status':a.status,'notice':'Request only. No contract, payment or installation confirmation.'}

@endpoint
def campaigns(request,pk=None,action=None):
    if not pk:
        return paginated([{'id':str(c.pk),'slug':c.slug,'name':c.name,'summary':c.summary,'target_cents':c.target_cents,'status':c.status,'totals':campaign_totals(c),'sandbox':c.is_demo} for c in Campaign.objects.filter(status__in=['published','paused','closed','completed','cancelled'])],request)
    c=Campaign.objects.get(pk=pk)
    if action:
        post(request)
        if action=='submit':c=submit_campaign(request.user,c)
        else:c=campaign_action(request.user,c,action,request.data.get('reason',''))
        return {'id':str(c.pk),'status':c.status}
    if c.status not in ['published','paused','closed','completed','cancelled']:require(request.user,'admin','reviewer')
    return {'id':str(c.pk),'name':c.name,'totals':campaign_totals(c),'status':c.status}

@endpoint
def donate(request):
    post(request);validate_email(request.data.get('email',''))
    d,token=donation_checkout(request.user,request.data,key(request))
    if token:request.session.setdefault('donation_access',{})[str(d.pk)]={'token':token,'time':timezone.now().timestamp()};request.session.modified=True
    return {'id':str(d.pk),'status':d.status,'sandbox_url':f'/sandbox/public_donation/{d.pk}/','notice':'SANDBOX — no actual funds are collected.'}

def authorized_donation(request,pk):
    d=Donation.objects.get(pk=pk)
    if request.user.is_authenticated and (d.user_id==request.user.id or request.user.is_superuser or request.user.groups.filter(name__in=['finance','admin']).exists()):return d
    access=request.session.get('donation_access',{}).get(str(pk),{})
    token=access.get('token','') if isinstance(access,dict) else ''
    if token and timezone.now().timestamp()-access.get('time',0)<1800 and hmac.compare_digest(hashlib.sha256(token.encode()).hexdigest(),d.access_hash):return d
    signed=request.GET.get('token','')
    if signed:
        try:
            obj=signing.loads(signed,salt='donation-access',max_age=900)
            if obj['id']==str(d.pk) and hmac.compare_digest(obj['hash'],d.access_hash):return d
        except signing.BadSignature:pass
    raise Http404

@endpoint
def donation_status(request,pk):
    d=authorized_donation(request,pk)
    return {'id':str(d.pk),'status':d.status,'amount_cents':d.amount_cents,'refunded_cents':d.refunded_cents,'sandbox':d.sandbox,'needs_review':d.needs_review}

@endpoint
def donation_receipt(request,pk):
    d=authorized_donation(request,pk)
    receipt=Receipt.objects.get(donation=d)
    content='KERAN — SANDBOX CONFIRMATION\nNo funds collected. Not a tax receipt.\n'+json.dumps(receipt.snapshot,ensure_ascii=False,indent=2)+f'\nConfirmed refunds (test cents): {d.refunded_cents}\n'
    response=HttpResponse(content,content_type='text/plain; charset=utf-8');response['Content-Disposition']='attachment; filename="sandbox-confirmation.txt"';response['Cache-Control']='no-store';return response

@endpoint
def refunds(request):
    post(request);return {'id':str(request_refund(request.user,request.data).pk),'status':'approved','notice':'Awaiting signed payment-provider confirmation.'}

@csrf_exempt
@endpoint
def webhook(request):
    post(request)
    if not settings.WEBHOOK_SECRET:fail('Webhook is not configured.','unconfigured',503)
    signature=request.headers.get('X-Keran-Signature','');timestamp=request.headers.get('X-Keran-Timestamp','')
    try:
        if abs(timezone.now().timestamp()-int(timestamp))>300:fail('Expired signature','signature',403)
    except ValueError:fail('Invalid timestamp','signature',403)
    expected=hmac.new(settings.WEBHOOK_SECRET.encode(),timestamp.encode()+b'.'+request.body,hashlib.sha256).hexdigest()
    if not hmac.compare_digest(signature,expected):fail('Invalid signature.','signature',403)
    event=process_event(request.data);return {'id':str(event.pk),'processed':True}

@endpoint
def sandbox_pay(request,purpose,pk):
    post(request)
    if settings.PAYMENT_MODE!='sandbox':fail('Sandbox is disabled.','disabled',403)
    if purpose=='commerce':
        member(request);obj=Order.objects.get(pk=pk,user=request.user);amount=obj.cash_cents
    elif purpose=='public_donation':obj=authorized_donation(request,pk);amount=obj.amount_cents
    elif purpose=='refund':
        require(request.user,'finance','admin');obj=Refund.objects.get(pk=pk);amount=obj.amount_cents
    else:fail('Invalid purpose')
    event=process_event({'event_id':'sandbox_'+str(pk)+'_'+request.data.get('outcome','succeeded'),'purpose':purpose,'reference':str(pk),'kind':request.data.get('outcome','succeeded'),'amount_cents':amount})
    audit(request.user,'sandbox_event',event.pk)
    return {'processed':True,'sandbox':True,'notice':'Simulated event only. No funds moved.'}

@endpoint
def reports(request,kind,export=False):
    rows=rows_for(request.user,kind,request.GET)
    rows=sort_rows(rows,request.GET)
    if export:
        from openpyxl import Workbook
        wb=Workbook();ws=wb.active;ws.title='KERAN '+kind
        if rows:
            ws.append(list(rows[0]))
            for r in rows:
                ws.append([safe_cell(v) for v in r.values()])
        else:ws.append(['No matching data'])
        stream=io.BytesIO();wb.save(stream);stream.seek(0)
        audit(request.user,'report_export',kind,rows=len(rows))
        response=FileResponse(stream,content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet');response['Content-Disposition']=f'attachment; filename="keran-{kind}.xlsx"';return response
    sums=report_totals(rows,kind)
    result=paginated(rows,request);result['totals']=sums;result['timezone']='America/New_York';result['date_field']='created_at';return result

def safe_cell(v):
    if isinstance(v,str) and v.lstrip().startswith(('=','+','-','@')):return "'"+v
    return v

@endpoint
def upload(request):
    post(request);member(request)
    f=request.FILES.get('file')
    if not f or f.size>5*1024*1024:fail('Use a file smaller than 5 MB.')
    # Strict image-only policy; re-encode to remove scripts, metadata and polyglot payloads.
    from PIL import Image,UnidentifiedImageError
    from django.core.files.base import ContentFile
    try:
        img=Image.open(f)
        if img.format not in ['PNG','JPEG'] or img.width*img.height>20000000:fail('Only PNG/JPEG evidence is accepted.')
        img.load();img=img.convert('RGB');out=io.BytesIO();img.save(out,'JPEG')
    except (UnidentifiedImageError,OSError,Image.DecompressionBombError):fail('Invalid image. Active content and PDFs are not accepted in this build.')
    case=None;verification=None
    if request.POST.get('case_id'):case=Case.objects.get(pk=request.POST['case_id'],user=request.user)
    elif request.POST.get('verification_id'):verification=Verification.objects.get(pk=request.POST['verification_id'],user=request.user)
    else:fail('Associate the file with your case or verification.')
    days=config('retention_days',None)
    a=Attachment.objects.create(owner=request.user,case=case,verification=verification,original_name='evidence.jpg',mime='image/jpeg',scan_status='reencoded_safe',retain_until=timezone.now()+timedelta(days=days) if isinstance(days,int) and days>0 else None)
    a.file.save(str(a.pk)+'.jpg',ContentFile(out.getvalue()))
    audit(request.user,'attachment_upload',a.pk);return {'id':str(a.pk)}

@endpoint
def attachment_link(request,pk):
    member(request);a=Attachment.objects.get(pk=pk)
    allowed=a.owner_id==request.user.id or request.user.is_superuser or request.user.groups.filter(name__in=['reviewer','admin']).exists() or (a.case and a.case.assignee_id==request.user.id and request.user.groups.filter(name='caseworker').exists())
    if not allowed:raise Http404
    token=signing.dumps({'attachment':str(a.pk),'user':request.user.pk},salt='attachment')
    audit(request.user,'attachment_access',a.pk);return {'url':f'/private/{a.pk}/?token={token}'}

@endpoint
def attachment_download(request,pk):
    member(request)
    try:data=signing.loads(request.GET.get('token',''),salt='attachment',max_age=120)
    except signing.BadSignature:raise Http404
    if data!={'attachment':str(pk),'user':request.user.pk}:raise Http404
    a=Attachment.objects.get(pk=pk)
    # Recheck authorization after issuance, so role changes revoke outstanding links.
    if not (a.owner_id==request.user.id or request.user.is_superuser or request.user.groups.filter(name__in=['reviewer','admin']).exists() or (a.case and a.case.assignee_id==request.user.id and request.user.groups.filter(name='caseworker').exists())):raise Http404
    response=FileResponse(a.file.open('rb'),as_attachment=True,filename='evidence.jpg',content_type='image/jpeg');response['Cache-Control']='no-store';return response

@endpoint
def asset_action(request,pk):
    post(request);data=request.data
    require(request.user,'admin','reviewer') if data.get('action')=='reserve' else require(request.user,'warehouse','admin')
    with transaction.atomic():
        a=Asset.objects.select_for_update().get(pk=pk)
        if data.get('action')=='inspect':
            if a.status!='pending_inspection':fail('Asset already inspected.')
            a.inspection=text(data.get('reason',''),500);a.status='available' if data.get('passed') else 'quarantined'
        elif data.get('action')=='reserve':
            require(request.user,'reviewer','admin')
            if a.status!='available':fail('Asset must pass inspection before reservation.')
            grant=Grant.objects.get(pk=data['grant_id'],active=True,expires_at__gt=timezone.now(),kind='free')
            if not eligible(grant,a.product):fail('Grant does not authorize this asset.')
            if grant.quantity_used>=grant.quantity_limit:fail('Grant quantity limit reached.')
            if grant.user_id==request.user.id:fail('Cannot approve own asset.')
            a.recipient=grant.user;a.status='reserved';grant.quantity_used+=1;grant.save()
        elif data.get('action')=='deliver':
            if a.status!='reserved' or not data.get('recipient_confirmation'):fail('Reservation and recipient confirmation required.')
            a.receipt_confirmed=True;a.status='delivered'
        else:fail('Invalid asset action')
        a.save();audit(request.user,'asset_'+data['action'],a.pk,data.get('reason',''));return {'status':a.status}

@endpoint
def reconcile(request):
    post(request);require(request.user,'finance','admin');data=request.data
    kind=data.get('kind');amount=integer(data.get('amount_cents'),1);reason=text(data.get('reason',''),500);external=text(data.get('external_id',''),180)
    if FinanceEntry.objects.filter(external_id=external).exists():fail('Already reconciled.','conflict',409)
    if kind not in ['received','fee','settlement','reserve','reserve_release']:fail('Unsupported reconciliation kind.')
    campaign=Campaign.objects.get(pk=data['campaign_id']) if data.get('campaign_id') else None
    org=Organization.objects.get(pk=data['organization_id']) if data.get('organization_id') else None
    if campaign and kind=='received':fail('Public donations require verified payment events, not manual receipts.')
    if not campaign and not org:fail('Campaign or merchant is required.')
    if org and kind!='received':fail('Merchant reconciliation records confirmed donations only.')
    e=FinanceEntry.objects.create(bucket='public_donation' if campaign else 'corporate_donation',kind='reserve' if kind=='reserve_release' else kind,amount_cents=-amount if kind=='reserve_release' else amount,reference=data.get('reference',external),campaign=campaign,organization=org,actor=request.user,external_id=external,reason=reason)
    audit(request.user,'finance_reconcile',e.pk,reason);return {'id':str(e.pk)}

@endpoint
def expenses(request,pk=None):
    post(request);data=request.data
    require(request.user,'reviewer','admin') if data.get('action')=='publish' else require(request.user,'finance','admin')
    with transaction.atomic():
        if not pk:
            c=Campaign.objects.select_for_update().get(pk=data['campaign_id'])
            e=Expense.objects.create(campaign=c,category=text(data.get('category',''),100),payee=text(data.get('payee',''),180),amount_cents=integer(data.get('amount_cents'),1),reason=text(data.get('reason',''),1000));audit(request.user,'expense_create',e.pk);return {'id':str(e.pk)}
        e=Expense.objects.select_for_update().get(pk=pk);c=Campaign.objects.select_for_update().get(pk=e.campaign_id)
        action=data.get('action')
        if action=='approve' and e.status=='submitted':
            if campaign_totals(c)['spendable']<e.amount_cents:fail('Insufficient settled spendable funds.')
            e.status='approved';e.approved_by=request.user
            FinanceEntry.objects.create(campaign=c,bucket='public_donation',kind='expense_reserved',amount_cents=e.amount_cents,reference=str(e.pk))
        elif action=='pay' and e.status=='approved':
            external=text(data.get('external_id',''),180);e.status='paid'
            FinanceEntry.objects.create(campaign=c,bucket='public_donation',kind='expense_reserved',amount_cents=-e.amount_cents,reference=str(e.pk))
            FinanceEntry.objects.create(campaign=c,bucket='public_donation',kind='expense_paid',amount_cents=e.amount_cents,reference=str(e.pk),external_id=external)
        elif action=='publish' and e.status=='paid':e.public=True
        else:fail('Invalid expense transition')
        e.save();audit(request.user,'expense_'+action,e.pk,data.get('reason',''));return {'status':e.status}

@endpoint
def roles(request):
    post(request);require(request.user,'admin');data=request.data
    if not request.user.check_password(data.get('current_password','')):fail('Re-enter your password to authorize a role change.','confirmation',403)
    allowed={'admin','reviewer','caseworker','warehouse','finance','merchant'};names=data.get('roles',[])
    if not isinstance(names,list) or not set(names)<=allowed:fail('Invalid role')
    target=User.objects.get(pk=data['user_id'])
    if target.pk==request.user.pk:fail('Have another administrator change your own roles.','conflict',403)
    from django.contrib.auth.models import Group
    before=list(target.groups.values_list('name',flat=True));target.groups.set([Group.objects.get_or_create(name=n)[0] for n in names])
    audit(request.user,'role_change',target.pk,text(data.get('reason',''),500),before=before,after=names)
    return {'ok':True}

@endpoint
def task_action(request,pk):
    post(request);member(request);t=Task.objects.get(pk=pk)
    if t.assignee_id!=request.user.id:require(request.user,'admin')
    data=request.data
    if data.get('status') not in ['open','in_progress','done']:fail('Invalid task status.')
    t.status=data['status'];t.minutes=integer(data.get('minutes',t.minutes),0,100000)
    if data.get('approve_hours'):
        require(request.user,'admin','reviewer')
        if t.assignee_id==request.user.id:fail('Cannot approve own service hours.')
        t.hours_approved=True
    t.save();audit(request.user,'task_update',t.pk);return {'status':t.status}

@endpoint
def plan_action(request,pk):
    post(request);require(request.user,'reviewer','admin');p=Plan.objects.get(pk=pk);data=request.data
    if data.get('action')=='publish':
        if p.owner_id==request.user.id:fail('Another reviewer must approve this public summary.')
        if not p.public_summary:fail('An anonymous public summary is required.')
        p.public=True;p.public_approved_by=request.user;p.state='active'
    elif data.get('action')=='unpublish':p.public=False
    else:fail('Invalid plan action')
    p.save();audit(request.user,'plan_'+data['action'],p.pk,text(data.get('reason',''),500));return {'public':p.public}

@endpoint
def budget_create(request):
    post(request);require(request.user,'finance','admin');data=request.data
    b=Budget.objects.create(name=text(data.get('name',''),180),funded_cents=integer(data.get('funded_cents'),1))
    audit(request.user,'funded_budget_create',b.pk,text(data.get('reason',''),500));return {'id':str(b.pk)}

@endpoint
def grant_action(request,pk):
    post(request);require(request.user,'reviewer','admin');data=request.data
    with transaction.atomic():
        g=Grant.objects.select_for_update().get(pk=pk)
        if g.user_id==request.user.id:fail('Cannot revoke your own grant.')
        amount=integer(data.get('amount_cents',g.available),0,g.available);g.revoked_cents+=amount;g.active=False;g.save()
        AidLedger.objects.create(grant=g,kind='revoke',amount_cents=-amount,reference=str(g.pk))
        if g.budget_id:Budget.objects.filter(pk=g.budget_id).update(committed_cents=F('committed_cents')-amount)
        audit(request.user,'grant_revoke',g.pk,text(data.get('reason',''),500));return {'available':g.available}

@endpoint
def receipt_resend(request,pk):
    post(request);require(request.user,'finance','admin');d=Donation.objects.get(pk=pk,status='succeeded')
    n=Outbox.objects.get(kind='donation_receipt',reference=str(d.pk));n.status='sandbox_queued';n.save()
    audit(request.user,'receipt_resend',d.pk);return {'notice':'Queued in sandbox outbox. No real email sent.'}

@endpoint
def campaign_update(request,pk):
    post(request);require(request.user,'admin','reviewer');c=Campaign.objects.get(pk=pk);data=request.data
    u=CampaignUpdate.objects.create(campaign=c,title=text(data.get('title',''),180),text=text(data.get('text',''),5000),approved=False)
    audit(request.user,'campaign_update_draft',u.pk);return {'id':str(u.pk)}

@endpoint
def approve_update(request,pk):
    post(request);require(request.user,'admin','reviewer');u=CampaignUpdate.objects.get(pk=pk)
    if u.campaign.owner_id==request.user.id:fail('Another reviewer must approve public updates.')
    u.approved=True;u.save();audit(request.user,'campaign_update_approve',u.pk);return {'approved':True}

@endpoint
def stock_import(request):
    post(request);require(request.user,'warehouse','admin')
    f=request.FILES.get('file')
    if not f or f.size>1024*1024:fail('Use a CSV file of at most 1 MB.')
    raw=f.read();digest=hashlib.sha256(raw).hexdigest();scope='stock_csv:'+str(request.user.pk)
    try:rows=list(csv.DictReader(io.StringIO(raw.decode('utf-8-sig'))))
    except (UnicodeError,csv.Error):fail('Invalid UTF-8 CSV.')
    if len(rows)>1000:fail('Maximum 1,000 rows per import.')
    with transaction.atomic():
        previous=Mutation.objects.select_for_update().filter(scope=scope,key=digest).first()
        if previous:return {**previous.result,'duplicate':True}
        for row in rows:
            lot=Lot.objects.get(pk=row['lot_id'])
            adjust_stock(request.user,lot,int(row['delta']),int(row.get('hold_delta',0)),text(row.get('reason',''),500),'csv_import')
        audit(request.user,'stock_csv_import','lots',rows=len(rows))
        Mutation.objects.create(scope=scope,key=digest,digest=digest,result={'imported':len(rows)})
    return {'imported':len(rows)}

@endpoint
def public_image(request,kind,pk):
    from PIL import Image
    obj=Product.objects.get(pk=pk) if kind=='product' else Campaign.objects.get(pk=pk)
    if (isinstance(obj,Product) and obj.status!='published') or (isinstance(obj,Campaign) and obj.status not in ['published','paused','closed','completed','cancelled']):require(request.user,'admin','reviewer')
    file=obj.image if kind=='product' else obj.cover
    if not file:raise Http404
    with file.open('rb') as f:
        image=Image.open(f).convert('RGB');image.thumbnail((1600,1600));out=io.BytesIO();image.save(out,'JPEG',quality=88)
    response=HttpResponse(out.getvalue(),content_type='image/jpeg');response['X-Content-Type-Options']='nosniff';return response
