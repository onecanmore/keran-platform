from datetime import datetime,time,timedelta
from zoneinfo import ZoneInfo
from django.db.models import Q,Sum,F
from .models import *
from .services import require,case_scope,campaign_totals,config,fail
NY=ZoneInfo('America/New_York')
def date_bounds(value):
    try:d=datetime.strptime(value,'%Y-%m-%d').date()
    except (ValueError,TypeError):fail('Date must use YYYY-MM-DD.')
    return datetime.combine(d,time.min,NY),datetime.combine(d+timedelta(days=1),time.min,NY)

def rows_for(user,kind,params):
    require(user,'admin','reviewer','caseworker','warehouse','finance','merchant')
    groups=set(user.groups.values_list('name',flat=True))
    all_access=user.is_superuser or 'admin' in groups
    if kind=='cases':
        require(user,'admin','reviewer','caseworker');qs=case_scope(user).exclude(status='draft')
        for k in ['status','state','zip','assignee_id']:
            if params.get(k):
                if k=='status' and params[k]=='open':qs=qs.exclude(status__in=['completed','withdrawn','declined'])
                else:qs=qs.filter(**{k:params[k]})
        if params.get('city'):qs=qs.filter(city__icontains=params['city'])
        if params.get('category'):qs=qs.filter(needs__category=params['category']).distinct()
        qs=filter_dates(qs,params)
        return [{'id':str(c.pk),'created_at':c.created_at.isoformat(),'status':c.status,'state':c.state,'city':c.city,'zip':c.zip,'household':str(c.household_id),'assignee':c.assignee.username if c.assignee else '', 'requested_items':' / '.join(f'{n.requested} {n.unit} {n.name}' for n in c.needs.all()),'gap_items':' / '.join(f'{n.gap} {n.unit} {n.name}' for n in c.needs.all()),'age_days':(timezone.now()-c.created_at).days,'first_response_hours':round((c.first_response-c.created_at).total_seconds()/3600,2) if c.first_response else None} for c in qs.order_by('-created_at')]
    if kind=='inventory':
        require(user,'admin','warehouse','reviewer');qs=filter_dates(Lot.objects.select_related('product'),params)
        if params.get('source'):qs=qs.filter(product__source=params['source'])
        return [{'id':str(l.pk),'name':l.product.name,'unit':l.product.unit,'warehouse':l.warehouse,'location':l.location,'purpose':l.purpose,'on_hand':l.on_hand,'reserved':l.reserved,'hold':l.hold,'available':l.available if not l.expires_at or l.expires_at>timezone.now() else 0} for l in qs]
    if kind=='orders':
        require(user,'admin','warehouse','finance','merchant');qs=filter_dates(Suborder.objects.select_related('order','merchant'),params)
        if not all_access and not groups&{'finance','warehouse'}:qs=qs.filter(merchant__user=user)
        if params.get('status'):qs=qs.filter(status=params['status'])
        if params.get('merchant_id'):qs=qs.filter(merchant_id=params['merchant_id'])
        rows=[]
        for s in qs:
            row={'id':str(s.pk),'order_id':str(s.order_id),'seller':s.merchant.name if s.merchant else '', 'status':s.status,'payment_status':s.order.payment_status,'goods_cents':sum(i.unit_price_cents*i.quantity for i in s.items.all()),'item_summary':' / '.join(f'{i.product.name} × {i.quantity}' for i in s.items.all()),'zip':s.order.zip,'method':s.order.method,'delivery_address':s.order.address if s.order.method=='delivery' else ''}
            if all_access or 'finance' in groups:
                row.update(cash_cents=sum(i.cash_cents for i in s.items.all())+s.shipping_cents,aid_cents=sum(i.aid_cents for i in s.items.all()))
            rows.append(row)
        return rows
    if kind=='donations':
        require(user,'admin','finance');qs=filter_dates(Donation.objects.select_related('campaign'),params)
        if params.get('status'):qs=qs.filter(status=params['status'])
        if params.get('campaign_id'):qs=qs.filter(campaign_id=params['campaign_id'])
        return [{'id':str(d.pk),'campaign':d.campaign.name,'created_at':d.created_at.isoformat(),'status':d.status,'amount_cents':d.amount_cents,'refunded_cents':d.refunded_cents,'chargeback_cents':d.chargeback_cents,'disputed_cents':d.disputed_cents,'confirmed_cents':d.amount_cents-d.refunded_cents-d.chargeback_cents if d.status=='succeeded' else 0,'receipt_email':d.email,'needs_review':d.needs_review,'sandbox':d.sandbox} for d in qs.order_by('-created_at')]
    if kind=='finance':
        require(user,'admin','finance','merchant');qs=filter_dates(FinanceEntry.objects.all(),params)
        if not all_access and 'finance' not in groups:qs=qs.filter(organization__user=user,bucket='corporate_donation')
        if params.get('bucket'):qs=qs.filter(bucket=params['bucket'])
        return [{'id':str(e.pk),'created_at':e.created_at.isoformat(),'bucket':e.bucket,'kind':e.kind,'amount_cents':e.amount_cents,'reference':e.reference,'reason':e.reason} for e in qs.order_by('-created_at')]
    if kind=='tasks':
        qs=Task.objects.all() if all_access else Task.objects.filter(assignee=user)
        if params.get('status'):qs=qs.filter(status=params['status'])
        if params.get('assignee_id'):qs=qs.filter(assignee_id=params['assignee_id'])
        if params.get('overdue'):qs=qs.filter(due_at__lt=timezone.now()).exclude(status='done')
        return [{'id':str(t.pk),'title':t.title,'assignee':t.assignee.username if t.assignee else '', 'status':t.status,'due_at':t.due_at.isoformat() if t.due_at else '', 'minutes':t.minutes,'hours_approved':t.hours_approved} for t in filter_dates(qs,params)]
    if kind=='impact':
        require(user,'admin','reviewer');qs=Allocation.objects.filter(fulfilled=True)
        return [{'id':str(a.pk),'plan':a.plan.name,'quantity':a.reservation.quantity,'unit':a.need.unit,'household':str(a.need.case.household_id)} for a in filter_dates(qs,params)]
    require(user,'admin');return []
def filter_dates(qs,params):
    if params.get('from'):qs=qs.filter(created_at__gte=date_bounds(params['from'])[0])
    if params.get('to'):qs=qs.filter(created_at__lt=date_bounds(params['to'])[1])
    return qs

def sort_rows(rows,params):
    sort=params.get('sort','');field=sort.lstrip('-')
    if sort and rows and field in rows[0]:rows.sort(key=lambda r:(r.get(field) is None,r.get(field) if r.get(field) is not None else ''),reverse=sort.startswith('-'))
    return rows

def report_totals(rows,kind):
    if not rows:return {}
    def sums(group):
        return {field:sum(r.get(field,0) or 0 for r in group) for field in group[0] if field.endswith('_cents') or field in ['on_hand','reserved','hold','available','minutes']}
    if kind in ['inventory','finance','impact']:
        groups={}
        for r in rows:
            key=r.get('unit','')+(' / '+r.get('purpose','') if kind=='inventory' else '') if kind!='finance' else r['bucket']+' / '+r['kind']
            groups.setdefault(key,[]).append(r)
        return {key:sums(group) for key,group in groups.items()}
    return sums(rows)
