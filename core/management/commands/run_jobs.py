from django.core.management.base import BaseCommand
from django.utils import timezone
from core.models import *
from core.services import release_order,release_allocation,audit,config
class Command(BaseCommand):
    help='Idempotent expiry, scheduling, private evidence retention and sandbox outbox retry jobs.'
    def handle(self,*args,**kwargs):
        now=timezone.now();released=0
        for o in Order.objects.filter(payment_status='pending',expires_at__lte=now,released=False):release_order(o);released+=1
        for a in Allocation.objects.filter(fulfilled=False,reservation__status='reserved',reservation__expires_at__lte=now):release_allocation(a,'Aid collection period expired')
        Campaign.objects.filter(status='scheduled',starts_at__lte=now,ends_at__gt=now).update(status='published')
        Campaign.objects.filter(status__in=['published','scheduled'],ends_at__lte=now).update(status='closed')
        Verification.objects.filter(status='approved',expires_at__lte=now).update(status='expired')
        # Retention is opt-in configuration, never silently assumes indefinite approved retention.
        deleted=0
        for a in Attachment.objects.filter(retain_until__isnull=False,retain_until__lte=now):
            a.file.delete(save=False);audit(None,'retention_delete',a.pk);a.delete();deleted+=1
        for n in Outbox.objects.filter(status__in=['sandbox_queued','failed']):
            n.attempts+=1;n.status='sandbox_recorded';n.save()
        self.stdout.write(f'Released {released} orders; removed {deleted} expired evidence files. No real notifications sent.')
