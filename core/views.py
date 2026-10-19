import hashlib
from datetime import timedelta
from django.contrib import messages
from django.contrib.auth import login
from django.contrib.auth.views import LoginView
from django.contrib.auth.models import User
from django.core.paginator import Paginator
from django.core.exceptions import PermissionDenied
from django.shortcuts import render,redirect,get_object_or_404
from django.http import Http404,HttpResponse
from django.utils import timezone
from django.views.decorators.http import require_POST
from .models import *
from .services import *
from .forms import *
from . import api
from .reports import rows_for,sort_rows,report_totals

def public(request,page='home',slug=None):
    ctx={'page':page}
    if page=='home':
        ctx['products']=Product.objects.filter(status='published')[:4]
        ctx['campaigns']=Campaign.objects.filter(status='published')[:2]
    if page in ['shop','care-items','volunteer-benefits']:
        qs=Product.objects.filter(status='published')
        if page=='care-items':qs=qs.filter(kind='application_only')
        if request.GET.get('q'):qs=qs.filter(Q(name__icontains=request.GET['q'])|Q(name_zh__icontains=request.GET['q']))
        for f in ['kind','category','source']:
            if request.GET.get(f):qs=qs.filter(**{f:request.GET[f]})
        if request.GET.get('max_price'):
            try:qs=qs.filter(price_cents__lte=int(request.GET['max_price']))
            except ValueError:qs=qs.none()
        ctx['products']=Paginator(qs.order_by('name'),12).get_page(request.GET.get('page'))
    if page=='product':ctx['product']=get_object_or_404(Product,slug=slug,status='published')
    if page=='fundraising':ctx['campaigns']=Campaign.objects.filter(status__in=['published','paused','closed','completed','cancelled'])
    if page in ['campaign','donate']:
        c=get_object_or_404(Campaign,slug=slug,status__in=['published','paused','closed','completed','cancelled']);ctx.update(campaign=c,totals=campaign_totals(c),policy=c.policies.order_by('-number').first(),updates=c.updates.filter(approved=True),expenses=Expense.objects.filter(campaign=c,public=True,status='paid'))
    if page=='community-needs':ctx['plans']=Plan.objects.filter(public=True,public_approved_by__isnull=False)
    if page=='partners':ctx['partners']=Organization.objects.filter(public=True,agreement_status='approved')
    if page=='impact':
        done=Allocation.objects.filter(fulfilled=True)
        ctx['delivered']=done.count();ctx['households']=done.values('need__case__household_id').distinct().count();ctx['services']=Appointment.objects.filter(status='completed').count()
    response=render(request,'core/'+page.replace('-','_')+'.html',ctx)
    return response

@require_POST
def language(request):
    request.session['language']='zh' if request.POST.get('language')=='zh' else 'en'
    target=request.POST.get('next','/')
    return redirect(target if target.startswith('/') and not target.startswith('//') else '/')

class SafeLoginView(LoginView):
    template_name='registration/login.html'
    def post(self,request,*args,**kwargs):
        from .models import LoginAttempt
        ip=request.META.get('REMOTE_ADDR','unknown')
        key=hashlib.sha256((ip+':'+request.POST.get('username','').lower()).encode()).hexdigest()
        row,_=LoginAttempt.objects.get_or_create(key=key)
        if row.window_start<timezone.now()-timedelta(minutes=15):row.attempts=0;row.window_start=timezone.now()
        if row.attempts>=8:return render(request,self.template_name,{'form':self.get_form(),'rate_limited':True},status=429)
        row.attempts+=1;row.save()
        request.session.pop('staff_mfa_verified',None)
        response=super().post(request,*args,**kwargs)
        if request.user.is_authenticated:row.delete()
        return response

def register(request):
    form=RegistrationForm(request.POST or None)
    if request.method=='POST' and form.is_valid():
        user=form.save();login(request,user);audit(user,'register',user.pk);return redirect('/account/')
    return render(request,'registration/register.html',{'form':form})

def member_page(request,page='overview',pk=None):
    if not request.user.is_authenticated:return redirect('/login/?next='+request.path)
    if page=='security':return security(request)
    ctx={'page':page}
    if page=='case':
        c=get_object_or_404(Case,user=request.user,pk=pk);ctx.update(case=c,notes=c.notes.filter(member_visible=True),attachments=Attachment.objects.filter(case=c))
    else:
        ctx.update(cases=Case.objects.filter(user=request.user).order_by('-created_at'),orders=Order.objects.filter(user=request.user).order_by('-created_at'),grants=Grant.objects.filter(user=request.user),verifications=Verification.objects.filter(user=request.user),appointments=Appointment.objects.filter(user=request.user),donations=Donation.objects.filter(user=request.user).select_related('campaign'),notifications=Outbox.objects.filter(user=request.user).order_by('-created_at')[:10])
    return render(request,'core/account.html',ctx)

def workflow(request,page):
    if not request.user.is_authenticated and page!='help_form':return redirect('/login/?next='+request.path)
    return render(request,'core/'+page+'.html',{'page':page,'help_draft':request.session.get('help_draft',{})})

def cart(request):
    cart=request.session.get('cart',{})
    products=Product.objects.filter(id__in=cart.keys(),status='published',kind='physical')
    return render(request,'core/cart.html',{'products':[(p,cart[str(p.pk)]) for p in products],'checkout':request.path.startswith('/checkout'),'grants':active_grants(request.user) if request.user.is_authenticated else []})

@require_POST
def cart_add(request,pk):
    p=get_object_or_404(Product,pk=pk,status='published',kind='physical')
    data=request.session.get('cart',{});value=request.POST.get('quantity','1')
    try:q=max(0,min(100,int(value)))
    except ValueError:q=1
    if request.POST.get('replace'):data[str(pk)]=q
    else:data[str(pk)]=min(100,data.get(str(pk),0)+q)
    if not data[str(pk)]:data.pop(str(pk))
    request.session['cart']=data;messages.success(request,'Cart updated. / 購物車已更新。');return redirect('/cart/')

def sandbox(request,purpose,pk):
    if purpose=='commerce':
        if not request.user.is_authenticated:return redirect('/login/')
        obj=get_object_or_404(Order,pk=pk,user=request.user);amount=obj.cash_cents
    elif purpose=='public_donation':
        try:obj=api.authorized_donation(request,pk)
        except Donation.DoesNotExist:raise Http404
        amount=obj.amount_cents
    elif purpose=='refund':
        try:require(request.user,'finance','admin')
        except DomainError:raise PermissionDenied
        obj=get_object_or_404(Refund,pk=pk);amount=obj.amount_cents
    else:raise Http404
    return render(request,'core/sandbox.html',{'object':obj,'amount':amount,'purpose':purpose})

WORK_FORMS={'catalog':ProductForm,'fundraising':CampaignForm,'partners':OrganizationForm,'plans':PlanForm,'tasks':TaskForm,'inventory':LotForm}

def work(request,section='overview',pk=None):
    if not request.user.is_authenticated:return redirect('/login/?next='+request.path)
    try:
        require(request.user,'admin','reviewer','caseworker','warehouse','finance','merchant')
        return work_authorized(request,section,pk)
    except DomainError as e:return render(request,'core/error.html',{'message':e.message},status=e.status)

def work_authorized(request,section,pk):
    ctx={'section':section}
    if section=='finance':
        require(request.user,'finance','admin')
        ctx.update(refunds=Refund.objects.order_by('-created_at')[:30],expenses=Expense.objects.select_related('campaign').all(),finance_campaigns=Campaign.objects.all(),budgets=Budget.objects.all())
    if section=='inventory':
        require(request.user,'warehouse','admin','reviewer')
        ctx['assets']=Asset.objects.select_related('product').all()
    if section=='overview':
        groups=set(request.user.groups.values_list('name',flat=True));admin=request.user.is_superuser or 'admin' in groups
        cards=[]
        if admin or groups&{'reviewer','caseworker'}:cards.extend([('cases/?status=open','Open requests / 待處理案件',case_scope(request.user).exclude(status__in=['draft','completed','withdrawn','declined']).count()),('verifications/?status=submitted','Verifications / 認證申請',Verification.objects.filter(status='submitted').count())])
        if admin or 'warehouse' in groups:cards.append(('inventory/','Inventory lots / 庫存批次',Lot.objects.count()))
        if admin or 'finance' in groups:cards.append(('donations/','Donation payments / 捐款交易',Donation.objects.count()))
        cards.append(('tasks/?status=open&assignee_id='+str(request.user.pk),'My tasks / 我的任務',Task.objects.filter(assignee=request.user,status='open').count()));ctx['cards']=cards
        ctx['tasks']=Task.objects.filter(assignee=request.user).order_by('due_at')[:10]
        overdue=Task.objects.filter(assignee=request.user,due_at__lt=timezone.now()).exclude(status='done').count()
        cards.append(('tasks/?overdue=1&assignee_id='+str(request.user.pk),'Overdue / 逾期待辦',overdue))
        if admin or groups&{'reviewer','caseworker'}:
            from django.db.models import Count
            open_cases=case_scope(request.user).exclude(status__in=['draft','completed','withdrawn','declined'])
            ctx['distribution']=open_cases.values('state').annotate(count=Count('id')).order_by('state')
            gaps={}
            for need in Need.objects.filter(case__in=open_cases).select_related('case'):
                if need.gap:gaps[(need.category,need.unit)]=gaps.get((need.category,need.unit),0)+need.gap
            ctx['gaps']=[{'category':cat,'unit':unit,'quantity':n} for (cat,unit),n in gaps.items()]
    elif section=='case':
        require(request.user,'admin','reviewer','caseworker');c=get_object_or_404(case_scope(request.user),pk=pk)
        ctx.update(case=c,notes=c.notes.all(),users=User.objects.filter(Q(groups__name__in=['caseworker','reviewer','admin'])|Q(is_superuser=True)).distinct(),budgets=Budget.objects.all(),attachments=Attachment.objects.filter(case=c))
    elif section=='verifications':
        require(request.user,'admin','reviewer');ctx['verifications']=Verification.objects.select_related('user').all()
        if request.GET.get('status'):ctx['verifications']=ctx['verifications'].filter(status=request.GET['status'])
    elif section=='appointments':
        require(request.user,'admin','caseworker');ctx['appointments']=Appointment.objects.all()
    elif section in ['catalog','fundraising','partners','plans','tasks','inventory'] and (request.GET.get('edit') or pk or request.GET.get('new')):
        require(request.user,'admin')
        form_class=WORK_FORMS[section];model=form_class._meta.model;obj=get_object_or_404(model,pk=pk) if pk else None
        if obj and isinstance(obj,Campaign) and obj.status not in ['draft','paused']:raise DomainError('Pause the campaign before a material edit. A fresh review will be required.')
        form=form_class(request.POST or None,request.FILES or None,instance=obj)
        if request.lang=='zh':
            from .forms import LABELS_ZH
            for name,field in form.fields.items():field.label=LABELS_ZH.get(name,field.label)
        if request.method=='POST' and form.is_valid():
            obj=form.save(commit=False)
            if isinstance(obj,Campaign):obj.owner=request.user;obj.status='draft';obj.approver=None;obj.version+=1
            if isinstance(obj,Product):obj.status='draft';obj.version+=1
            if isinstance(obj,Plan):obj.state='approved'
            obj.save();form.save_m2m();audit(request.user,section+'_save',obj.pk);messages.success(request,'Saved as draft. / 已儲存草稿。');return redirect('/admin/'+section+'/')
        ctx.update(form=form,editing=True)
    elif section=='catalog':
        require(request.user,'admin','reviewer');ctx['products']=Product.objects.select_related('merchant').all()
    elif section=='fundraising':
        require(request.user,'admin','reviewer');ctx['campaigns']=Campaign.objects.all()
    elif section=='partners':
        require(request.user,'admin');ctx['partners']=Organization.objects.all();ctx['inquiries']=PartnerInquiry.objects.all()
    elif section=='plans':
        require(request.user,'admin','reviewer');ctx.update(plans=Plan.objects.all(),needs=Need.objects.filter(confirmed__gt=F('allocated')),lots=Lot.objects.filter(purpose='aid'),allocations=Allocation.objects.all())
    elif section=='settings':
        require(request.user,'admin')
        if request.method=='POST':
            import json
            allowed={'brand','service_states','shipping','water_zips','verification_days','retention_days','reservation_minutes','policies','fundraising_legal','product_requirements','aid_reservation_days'}
            k=request.POST.get('key')
            if k not in allowed:raise DomainError('Setting key is not editable here.')
            try:v=json.loads(request.POST.get('value',''))
            except ValueError:raise DomainError('Value must be valid JSON.')
            Setting.objects.update_or_create(key=k,defaults={'value':v});audit(request.user,'setting_update',k);messages.success(request,'Configuration saved. / 設定已儲存。')
        ctx['settings']=list(Setting.objects.all())
        import json
        for setting in ctx['settings']: setting.value_json=json.dumps(setting.value,ensure_ascii=False,indent=2)
        ctx['staff_users']=User.objects.filter(is_active=True);ctx['groups']=['admin','reviewer','caseworker','warehouse','finance','merchant']
    elif section=='audit':
        require(request.user,'admin');ctx['audit']=Audit.objects.select_related('actor').order_by('-created_at')[:200]
    else:
        kind={'fulfillment':'orders','reports':'cases','finance':'finance','donations':'donations','inventory':'inventory','cases':'cases','tasks':'tasks'}.get(section,section)
        rows=sort_rows(rows_for(request.user,kind,request.GET),request.GET)
        import json
        ctx['report_totals']=json.dumps(report_totals(rows,kind),ensure_ascii=False,indent=2)
        page=Paginator(rows,20).get_page(request.GET.get('page'));ctx.update(rows=page,columns=list(rows[0]) if rows else [],kind=kind,total_rows=len(rows))
    return render(request,'core/work.html',ctx)

@require_POST
def publish_product(request,pk):
    try:
        post_product=get_object_or_404(Product,pk=pk)
        action=request.POST.get('action','publish')
        if action=='publish':product_publish(request.user,post_product)
        else:
            require(request.user,'admin','reviewer')
            if action not in ['pending','paused','archived']:fail('Invalid product status')
            post_product.status=action;post_product.save();audit(request.user,'product_'+action,pk)
        messages.success(request,'Updated / 已更新')
    except DomainError as e:messages.error(request,e.message)
    return redirect('/admin/catalog/')

@require_POST
def partner_apply(request):
    from django.core.validators import validate_email
    try:
        validate_email(request.POST.get('email',''))
        PartnerInquiry.objects.create(organization=text(request.POST.get('organization',''),180),email=request.POST['email'],message=text(request.POST.get('message',''),3000));messages.success(request,'Your enquiry has been saved. Follow-up is pending manual review. / 已收到，待工作人員聯絡。')
    except Exception:messages.error(request,'Please check required fields. / 請檢查必填欄位。')
    return redirect('/partners/apply/')


def security(request):
    from .mfa import generate_secret,cipher,validate,verify
    from django.conf import settings
    from urllib.parse import quote as urlquote
    row=StaffMFA.objects.filter(user=request.user).first()
    error=''
    if request.method=='POST':
        if not request.user.check_password(request.POST.get('current_password','')):error='Password confirmation failed. / 密碼確認失敗。'
        elif row:
            if verify(request.user,request.POST.get('code','')):
                request.session['staff_mfa_verified']=True;audit(request.user,'mfa_verified',request.user.pk);return redirect('/admin/')
            error='Invalid or already-used code. / 驗證碼無效或已使用。'
        else:
            secret=request.session.get('mfa_enrollment','');step=validate(secret,request.POST.get('code','')) if secret else None
            if step:
                StaffMFA.objects.create(user=request.user,encrypted_secret=cipher().encrypt(secret.encode()).decode(),last_step=step)
                request.session.pop('mfa_enrollment',None);request.session['staff_mfa_verified']=True;audit(request.user,'mfa_enrolled',request.user.pk);return redirect('/admin/')
            error='Authenticator code is invalid. / 驗證碼無效。'
    secret=''
    if not row:
        secret=request.session.setdefault('mfa_enrollment',generate_secret());request.session.modified=True
    uri='otpauth://totp/'+urlquote('KERAN:'+request.user.username)+'?secret='+secret+'&issuer=KERAN'
    return render(request,'core/security.html',{'enrolled':bool(row),'secret':secret,'uri':uri,'error':error})
