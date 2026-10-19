import getpass
from django.core.management.base import BaseCommand,CommandError
from django.contrib.auth.models import User,Group
from django.contrib.auth.password_validation import validate_password
from django.db import transaction
class Command(BaseCommand):
    help='Create an operations administrator without a shared password. Prompts securely.'
    def add_arguments(self,p):p.add_argument('username');p.add_argument('--email',default='')
    @transaction.atomic
    def handle(self,*a,**o):
        if User.objects.filter(username=o['username']).exists():raise CommandError('User already exists; no account changed.')
        u=User(username=o['username'],email=o['email']);password=getpass.getpass('New private password: ')
        if password!=getpass.getpass('Repeat private password: '):raise CommandError('Passwords differ.')
        validate_password(password,u);u.set_password(password);u.save();g,_=Group.objects.get_or_create(name='admin');u.groups.add(g)
        self.stdout.write('Operations administrator created. Create a separate reviewer for publication approval.')
