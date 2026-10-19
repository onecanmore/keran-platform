import uuid
from django.conf import settings
from django.db import models
from django.db.models import Q, F
from django.utils import timezone

U = settings.AUTH_USER_MODEL
class Record(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    created_at = models.DateTimeField(default=timezone.now, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)
    version = models.PositiveIntegerField(default=1)
    class Meta: abstract = True
    def __str__(self): return str(getattr(self,'name',getattr(self,'title',self.id)))

class Setting(models.Model):
    key = models.CharField(max_length=100, primary_key=True)
    value = models.JSONField(default=dict, null=True)
    def __str__(self): return self.key

class Organization(Record):
    name = models.CharField(max_length=180)
    kind = models.CharField(max_length=30, default='merchant')
    contact = models.CharField(max_length=180, blank=True)
    region = models.JSONField(default=list)
    agreement_status = models.CharField(max_length=30, default='draft')
    expires_at = models.DateTimeField(null=True, blank=True)
    user = models.ForeignKey(U, null=True, blank=True, on_delete=models.PROTECT)
    public = models.BooleanField(default=False)
    terms = models.TextField(blank=True)

class Household(Record):
    label = models.CharField(max_length=120, blank=True)
    verified = models.BooleanField(default=False)
    members = models.ManyToManyField(U, related_name='households')

class Verification(Record):
    user = models.ForeignKey(U,on_delete=models.PROTECT)
    organization = models.CharField(max_length=180, blank=True)
    description = models.TextField()
    consent = models.BooleanField(default=False)
    status = models.CharField(max_length=30, default='submitted', db_index=True)
    expires_at = models.DateTimeField(null=True, blank=True)
    reviewer = models.ForeignKey(U,null=True,blank=True,on_delete=models.PROTECT,related_name='+')
    reason = models.TextField(blank=True)

class Product(Record):
    TYPES = [('physical','Physical / 實物'),('service_booking','Service booking / 服務預約'),('application_only','Application only / 申請物資')]
    STATES = [('draft','Draft / 草稿'),('pending','Pending review / 待審'),('published','Published / 已發布'),('paused','Paused / 暫停'),('archived','Archived / 下架')]
    name = models.CharField(max_length=180)
    name_zh = models.CharField(max_length=180, blank=True)
    slug = models.SlugField(unique=True)
    description = models.TextField(blank=True)
    description_zh = models.TextField(blank=True)
    kind = models.CharField(max_length=25, choices=TYPES, default='physical')
    source = models.CharField(max_length=30, choices=[('merchant_supply','Merchant supply'),('donated_inventory','Donated inventory')], default='merchant_supply')
    category = models.CharField(max_length=80, default='home')
    status = models.CharField(max_length=20,choices=STATES,default='draft',db_index=True)
    merchant = models.ForeignKey(Organization,null=True,blank=True,on_delete=models.PROTECT)
    fulfiller = models.CharField(max_length=180,blank=True)
    specifications = models.JSONField(default=dict,blank=True)
    unit = models.CharField(max_length=40, default='item')
    price_cents = models.PositiveIntegerField(null=True,blank=True)
    volunteer_price_cents = models.PositiveIntegerField(null=True,blank=True)
    care_price_cents = models.PositiveIntegerField(null=True,blank=True)
    donation_bps = models.PositiveIntegerField(null=True,blank=True)
    donation_fixed_cents = models.PositiveIntegerField(null=True,blank=True)
    donation_rule_version = models.PositiveIntegerField(default=1)
    safety_confirmed = models.BooleanField(default=False)
    policy = models.TextField(blank=True)
    image = models.ImageField(upload_to='catalog/',blank=True)
    is_demo = models.BooleanField(default=False)

class Lot(Record):
    product = models.ForeignKey(Product,on_delete=models.PROTECT,related_name='lots')
    warehouse = models.CharField(max_length=120, default='Main')
    location = models.CharField(max_length=100,blank=True)
    owner = models.CharField(max_length=120,blank=True)
    batch = models.CharField(max_length=100)
    purpose = models.CharField(max_length=20,choices=[('sale','Sale'),('aid','Aid')])
    restricted = models.BooleanField(default=False)
    expires_at = models.DateTimeField(null=True,blank=True)
    on_hand = models.PositiveIntegerField(default=0)
    reserved = models.PositiveIntegerField(default=0)
    hold = models.PositiveIntegerField(default=0)
    class Meta:
        constraints = [models.CheckConstraint(condition=Q(on_hand__gte=F('reserved')+F('hold')),name='stock_nonnegative')]
        indexes = [models.Index(fields=['product','warehouse','purpose'])]
    @property
    def available(self): return self.on_hand-self.reserved-self.hold

class Asset(Record):
    product = models.ForeignKey(Product,on_delete=models.PROTECT)
    serial = models.CharField(max_length=100,unique=True)
    status = models.CharField(max_length=30,default='pending_inspection')
    inspection = models.TextField(blank=True)
    recipient = models.ForeignKey(U,null=True,blank=True,on_delete=models.PROTECT)
    receipt_confirmed = models.BooleanField(default=False)

class Case(Record):
    user = models.ForeignKey(U,on_delete=models.PROTECT)
    household = models.ForeignKey(Household,on_delete=models.PROTECT)
    status = models.CharField(max_length=30,default='draft',db_index=True)
    applicant_type = models.CharField(max_length=30,default='self')
    state = models.CharField(max_length=2)
    city = models.CharField(max_length=100)
    zip = models.CharField(max_length=10,db_index=True)
    categories = models.JSONField(default=list)
    urgency = models.CharField(max_length=30,default='two_weeks')
    recurrence = models.CharField(max_length=30,default='once')
    message = models.TextField(blank=True)
    method = models.CharField(max_length=30,default='unsure')
    email = models.EmailField(blank=True)
    phone = models.CharField(max_length=30,blank=True)
    language = models.CharField(max_length=10,default='en')
    contact_time = models.CharField(max_length=120,blank=True)
    contact_status = models.CharField(max_length=30,default='manual_pending')
    outside_region = models.BooleanField(default=False)
    assignee = models.ForeignKey(U,null=True,blank=True,on_delete=models.PROTECT,related_name='assigned_cases')
    follow_up = models.DateTimeField(null=True,blank=True)
    first_response = models.DateTimeField(null=True,blank=True)
    reconfirmed_at = models.DateTimeField(null=True,blank=True)
    class Meta: indexes = [models.Index(fields=['status','assignee','state','created_at'])]

class Need(Record):
    case = models.ForeignKey(Case,on_delete=models.PROTECT,related_name='needs')
    name = models.CharField(max_length=180)
    category = models.CharField(max_length=80)
    unit = models.CharField(max_length=30)
    requested = models.PositiveIntegerField()
    confirmed = models.PositiveIntegerField(default=0)
    allocated = models.PositiveIntegerField(default=0)
    fulfilled = models.PositiveIntegerField(default=0)
    people = models.PositiveIntegerField(default=1)
    use = models.TextField(blank=True)
    substitutes = models.BooleanField(default=True)
    class Meta:
        constraints = [models.CheckConstraint(condition=Q(fulfilled__lte=F('allocated')) & Q(allocated__lte=F('confirmed')) & Q(confirmed__lte=F('requested')),name='need_quantity_order')]
    @property
    def gap(self):
        if self.case.status in ['declined','withdrawn']:return 0
        if self.case.status=='waitlisted':
            from datetime import timedelta
            if not self.case.reconfirmed_at or self.case.reconfirmed_at<timezone.now()-timedelta(days=30):return 0
        return max(0,self.confirmed-self.allocated)

class Consent(Record):
    user = models.ForeignKey(U,on_delete=models.PROTECT)
    case = models.ForeignKey(Case,null=True,blank=True,on_delete=models.PROTECT)
    kind = models.CharField(max_length=40)
    granted = models.BooleanField(default=False)
    policy_version = models.CharField(max_length=40,default='1.0')

class Note(Record):
    case = models.ForeignKey(Case,on_delete=models.PROTECT,related_name='notes')
    author = models.ForeignKey(U,on_delete=models.PROTECT)
    text = models.TextField()
    member_visible = models.BooleanField(default=False)

class Attachment(Record):
    owner = models.ForeignKey(U,on_delete=models.PROTECT)
    case = models.ForeignKey(Case,null=True,blank=True,on_delete=models.PROTECT)
    verification = models.ForeignKey(Verification,null=True,blank=True,on_delete=models.PROTECT)
    file = models.FileField(upload_to='evidence/')
    original_name = models.CharField(max_length=180)
    mime = models.CharField(max_length=60)
    scan_status = models.CharField(max_length=30,default='quarantined')
    retain_until = models.DateTimeField(null=True,blank=True)

class Budget(Record):
    name = models.CharField(max_length=180)
    funded_cents = models.PositiveIntegerField(default=0)
    committed_cents = models.PositiveIntegerField(default=0)
    class Meta: constraints=[models.CheckConstraint(condition=Q(funded_cents__gte=F('committed_cents')),name='budget_funded')]

class Grant(Record):
    user = models.ForeignKey(U,on_delete=models.PROTECT)
    case = models.ForeignKey(Case,on_delete=models.PROTECT)
    reviewer = models.ForeignKey(U,on_delete=models.PROTECT,related_name='+')
    budget = models.ForeignKey(Budget,null=True,blank=True,on_delete=models.PROTECT)
    kind = models.CharField(max_length=30,choices=[('credit','Credit'),('free','Free item'),('discount','Care discount')])
    products = models.ManyToManyField(Product,blank=True)
    categories = models.JSONField(default=list)
    granted_cents = models.PositiveIntegerField(default=0)
    reserved_cents = models.PositiveIntegerField(default=0)
    redeemed_cents = models.PositiveIntegerField(default=0)
    revoked_cents = models.PositiveIntegerField(default=0)
    quantity_limit = models.PositiveIntegerField(default=1)
    quantity_used = models.PositiveIntegerField(default=0)
    expires_at = models.DateTimeField()
    reason = models.TextField()
    source = models.CharField(max_length=180)
    active = models.BooleanField(default=True)
    class Meta: constraints=[models.CheckConstraint(condition=Q(granted_cents__gte=F('reserved_cents')+F('redeemed_cents')+F('revoked_cents')),name='credit_nonnegative')]
    @property
    def available(self): return self.granted_cents-self.reserved_cents-self.redeemed_cents-self.revoked_cents

class Plan(Record):
    name = models.CharField(max_length=180)
    description = models.TextField(blank=True)
    state = models.CharField(max_length=30,default='draft')
    region = models.CharField(max_length=120,blank=True)
    owner = models.ForeignKey(U,null=True,blank=True,on_delete=models.PROTECT)
    budget_cents = models.PositiveIntegerField(default=0)
    deadline = models.DateTimeField(null=True,blank=True)
    needs = models.ManyToManyField(Need,blank=True)
    public = models.BooleanField(default=False)
    public_summary = models.TextField(blank=True)
    public_approved_by = models.ForeignKey(U,null=True,blank=True,on_delete=models.PROTECT,related_name='+')

class Order(Record):
    user = models.ForeignKey(U,on_delete=models.PROTECT)
    payment_status = models.CharField(max_length=30,default='pending')
    fulfillment_status = models.CharField(max_length=30,default='unfulfilled')
    refund_status = models.CharField(max_length=30,default='none')
    total_cents = models.PositiveIntegerField()
    cash_cents = models.PositiveIntegerField()
    aid_cents = models.PositiveIntegerField(default=0)
    shipping_cents = models.PositiveIntegerField(default=0)
    tax_cents = models.PositiveIntegerField(default=0)
    quote_snapshot = models.JSONField()
    grant = models.ForeignKey(Grant,null=True,blank=True,on_delete=models.PROTECT)
    expires_at = models.DateTimeField()
    released = models.BooleanField(default=False)
    sandbox = models.BooleanField(default=True)
    zip = models.CharField(max_length=10)
    method = models.CharField(max_length=20)
    address = models.TextField(blank=True)
    idempotency_key = models.CharField(max_length=100)
    class Meta: constraints=[models.UniqueConstraint(fields=['user','idempotency_key'],name='order_idempotent')]

class Suborder(Record):
    order = models.ForeignKey(Order,on_delete=models.PROTECT,related_name='suborders')
    merchant = models.ForeignKey(Organization,null=True,blank=True,on_delete=models.PROTECT)
    fulfiller = models.CharField(max_length=180)
    status = models.CharField(max_length=30,default='unfulfilled')
    shipping_cents = models.PositiveIntegerField(default=0)
    tracking = models.CharField(max_length=180,blank=True)

class Item(Record):
    suborder = models.ForeignKey(Suborder,on_delete=models.PROTECT,related_name='items')
    product = models.ForeignKey(Product,on_delete=models.PROTECT)
    lot = models.ForeignKey(Lot,on_delete=models.PROTECT)
    quantity = models.PositiveIntegerField()
    unit_price_cents = models.PositiveIntegerField()
    cash_cents = models.PositiveIntegerField()
    aid_cents = models.PositiveIntegerField(default=0)
    refunded_cash_cents = models.PositiveIntegerField(default=0)
    refunded_aid_cents = models.PositiveIntegerField(default=0)
    donation_basis_cents = models.PositiveIntegerField(default=0)
    donation_estimated_cents = models.PositiveIntegerField(default=0)
    snapshot = models.JSONField()

class Reservation(Record):
    lot = models.ForeignKey(Lot,on_delete=models.PROTECT)
    order = models.ForeignKey(Order,null=True,blank=True,on_delete=models.PROTECT)
    quantity = models.PositiveIntegerField()
    status = models.CharField(max_length=30,default='reserved')
    expires_at = models.DateTimeField(null=True,blank=True)

class Allocation(Record):
    plan = models.ForeignKey(Plan,on_delete=models.PROTECT)
    need = models.ForeignKey(Need,on_delete=models.PROTECT)
    reservation = models.OneToOneField(Reservation,on_delete=models.PROTECT)
    fulfilled = models.BooleanField(default=False)

class Pickup(Record):
    suborder = models.OneToOneField(Suborder,on_delete=models.PROTECT)
    token_hash = models.CharField(max_length=64,unique=True)
    used_at = models.DateTimeField(null=True,blank=True)
    revoked = models.BooleanField(default=False)

class StockMovement(Record):
    lot = models.ForeignKey(Lot,on_delete=models.PROTECT)
    actor = models.ForeignKey(U,null=True,on_delete=models.PROTECT)
    kind = models.CharField(max_length=30)
    quantity = models.IntegerField()
    reference = models.CharField(max_length=100)
    reason = models.CharField(max_length=500)

class AidLedger(Record):
    grant = models.ForeignKey(Grant,on_delete=models.PROTECT)
    amount_cents = models.IntegerField()
    kind = models.CharField(max_length=30)
    reference = models.CharField(max_length=100)

class Appointment(Record):
    user = models.ForeignKey(U,on_delete=models.PROTECT)
    product = models.ForeignKey(Product,null=True,blank=True,on_delete=models.PROTECT)
    zip = models.CharField(max_length=10)
    address = models.TextField()
    phone = models.CharField(max_length=40)
    preferred = models.CharField(max_length=180)
    status = models.CharField(max_length=30,default='submitted')
    notes = models.TextField(blank=True)

class Task(Record):
    title = models.CharField(max_length=180)
    assignee = models.ForeignKey(U,null=True,blank=True,on_delete=models.PROTECT)
    case = models.ForeignKey(Case,null=True,blank=True,on_delete=models.PROTECT)
    due_at = models.DateTimeField(null=True,blank=True)
    status = models.CharField(max_length=30,default='open')
    minutes = models.PositiveIntegerField(default=0)
    hours_approved = models.BooleanField(default=False)

class Campaign(Record):
    name = models.CharField(max_length=180)
    name_zh = models.CharField(max_length=180,blank=True)
    slug = models.SlugField(unique=True)
    summary = models.TextField()
    summary_zh = models.TextField(blank=True)
    body = models.TextField(blank=True)
    cover = models.ImageField(upload_to='campaigns/',blank=True)
    category = models.CharField(max_length=80,default='community')
    region = models.CharField(max_length=120,default='NY / NJ')
    target_cents = models.PositiveIntegerField()
    starts_at = models.DateTimeField()
    ends_at = models.DateTimeField()
    status = models.CharField(max_length=40,default='draft',db_index=True)
    owner = models.ForeignKey(U,on_delete=models.PROTECT)
    approver = models.ForeignKey(U,null=True,blank=True,on_delete=models.PROTECT,related_name='+')
    plan = models.ForeignKey(Plan,null=True,blank=True,on_delete=models.PROTECT)
    budget = models.JSONField(default=list)
    beneficiaries = models.CharField(max_length=300)
    execution = models.TextField()
    consent_basis = models.TextField()
    policy = models.TextField()
    minimum_cents = models.PositiveIntegerField(default=100)
    maximum_cents = models.PositiveIntegerField(default=1000000)
    suggested = models.JSONField(default=list)
    allow_overfund = models.BooleanField(default=False)
    is_demo = models.BooleanField(default=False)
    class Meta: constraints=[models.CheckConstraint(condition=Q(target_cents__gt=0)&Q(minimum_cents__gt=0)&Q(maximum_cents__gte=F('minimum_cents'))&Q(ends_at__gt=F('starts_at')),name='campaign_valid')]

class PolicyVersion(Record):
    campaign = models.ForeignKey(Campaign,on_delete=models.PROTECT,related_name='policies')
    number = models.PositiveIntegerField()
    snapshot = models.JSONField()
    approved_by = models.ForeignKey(U,on_delete=models.PROTECT)
    class Meta: constraints=[models.UniqueConstraint(fields=['campaign','number'],name='policy_version_unique')]

class Donation(Record):
    campaign = models.ForeignKey(Campaign,on_delete=models.PROTECT,related_name='donations')
    user = models.ForeignKey(U,null=True,blank=True,on_delete=models.PROTECT)
    donor_reference = models.UUIDField(default=uuid.uuid4)
    amount_cents = models.PositiveIntegerField()
    refunded_cents = models.PositiveIntegerField(default=0)
    chargeback_cents = models.PositiveIntegerField(default=0)
    disputed_cents = models.PositiveIntegerField(default=0)
    status = models.CharField(max_length=30,default='pending')
    email = models.EmailField()
    receipt_name = models.CharField(max_length=180)
    anonymous = models.BooleanField(default=True)
    marketing = models.BooleanField(default=False)
    message = models.TextField(blank=True)
    policy_snapshot = models.JSONField()
    expires_at = models.DateTimeField()
    needs_review = models.BooleanField(default=False)
    sandbox = models.BooleanField(default=True)
    access_hash = models.CharField(max_length=64)
    idempotency_key = models.CharField(max_length=100,unique=True)

class PaymentEvent(Record):
    event_id = models.CharField(max_length=180,unique=True)
    purpose = models.CharField(max_length=30)
    reference = models.UUIDField()
    kind = models.CharField(max_length=40)
    payload_digest = models.CharField(max_length=64)

class Refund(Record):
    shipping_cents = models.PositiveIntegerField(default=0)
    tax_cents = models.PositiveIntegerField(default=0)
    order = models.ForeignKey(Order,null=True,blank=True,on_delete=models.PROTECT)
    item = models.ForeignKey(Item,null=True,blank=True,on_delete=models.PROTECT)
    donation = models.ForeignKey(Donation,null=True,blank=True,on_delete=models.PROTECT)
    amount_cents = models.PositiveIntegerField()
    aid_cents = models.PositiveIntegerField(default=0)
    status = models.CharField(max_length=30,default='approved')
    reason = models.TextField()
    approver = models.ForeignKey(U,on_delete=models.PROTECT)
    external_id = models.CharField(max_length=180,unique=True)

class Dispute(Record):
    donation = models.ForeignKey(Donation,on_delete=models.PROTECT)
    external_id = models.CharField(max_length=180,unique=True)
    amount_cents = models.PositiveIntegerField()
    status = models.CharField(max_length=30,default='open')

class FinanceEntry(Record):
    bucket = models.CharField(max_length=30)
    kind = models.CharField(max_length=40)
    amount_cents = models.IntegerField()
    reference = models.CharField(max_length=100)
    campaign = models.ForeignKey(Campaign,null=True,blank=True,on_delete=models.PROTECT)
    organization = models.ForeignKey(Organization,null=True,blank=True,on_delete=models.PROTECT)
    external_id = models.CharField(max_length=180,blank=True)
    actor = models.ForeignKey(U,null=True,blank=True,on_delete=models.PROTECT)
    reason = models.TextField(blank=True)

class Expense(Record):
    campaign = models.ForeignKey(Campaign,on_delete=models.PROTECT)
    category = models.CharField(max_length=100)
    payee = models.CharField(max_length=180)
    amount_cents = models.PositiveIntegerField()
    status = models.CharField(max_length=30,default='submitted')
    reason = models.TextField()
    approved_by = models.ForeignKey(U,null=True,blank=True,on_delete=models.PROTECT)
    public = models.BooleanField(default=False)

class CampaignUpdate(Record):
    campaign = models.ForeignKey(Campaign,on_delete=models.PROTECT,related_name='updates')
    title = models.CharField(max_length=180)
    text = models.TextField()
    approved = models.BooleanField(default=False)

class Receipt(Record):
    donation = models.OneToOneField(Donation,on_delete=models.PROTECT)
    snapshot = models.JSONField()

class Outbox(Record):
    user = models.ForeignKey(U,null=True,blank=True,on_delete=models.PROTECT)
    recipient = models.EmailField(blank=True)
    kind = models.CharField(max_length=50)
    reference = models.CharField(max_length=100)
    status = models.CharField(max_length=30,default='sandbox_queued')
    attempts = models.PositiveIntegerField(default=0)
    class Meta: constraints=[models.UniqueConstraint(fields=['kind','reference'],name='notification_once')]

class Audit(Record):
    actor = models.ForeignKey(U,null=True,blank=True,on_delete=models.PROTECT)
    action = models.CharField(max_length=100)
    target = models.CharField(max_length=100)
    reason = models.CharField(max_length=500,blank=True)
    metadata = models.JSONField(default=dict)

class PartnerInquiry(Record):
    organization = models.CharField(max_length=180)
    email = models.EmailField()
    message = models.TextField()
    status = models.CharField(max_length=30,default='received')

class LoginAttempt(models.Model):
    key = models.CharField(max_length=64,primary_key=True)
    attempts = models.PositiveIntegerField(default=0)
    window_start = models.DateTimeField(default=timezone.now)

class Mutation(Record):
    scope = models.CharField(max_length=250)
    key = models.CharField(max_length=100)
    digest = models.CharField(max_length=64)
    result = models.JSONField(default=dict)
    class Meta: constraints=[models.UniqueConstraint(fields=['scope','key'],name='mutation_once')]

class StaffMFA(models.Model):
    user = models.OneToOneField(U,on_delete=models.CASCADE)
    encrypted_secret = models.TextField()
    last_step = models.BigIntegerField(default=0)
