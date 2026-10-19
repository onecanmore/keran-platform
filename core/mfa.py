"""RFC 6238 TOTP; encrypted seeds; replay-resistant verification under a row lock."""
import base64,hashlib,hmac,secrets,struct,time
from cryptography.fernet import Fernet
from django.conf import settings
from django.db import transaction
from .models import StaffMFA

def cipher():return Fernet(base64.urlsafe_b64encode(hashlib.sha256((settings.SECRET_KEY+'staff-mfa').encode()).digest()))
def generate_secret():return base64.b32encode(secrets.token_bytes(20)).decode()
def code_for(secret,step):
    digest=hmac.new(base64.b32decode(secret),struct.pack('>Q',step),hashlib.sha1).digest();offset=digest[-1]&15
    return str((struct.unpack('>I',digest[offset:offset+4])[0]&0x7fffffff)%1000000).zfill(6)
def validate(secret,code,last=0):
    if not isinstance(code,str) or not code.isdigit() or len(code)!=6:return None
    step=int(time.time())//30
    for i in [step-1,step,step+1]:
        if i>last and hmac.compare_digest(code_for(secret,i),code):return i
    return None
@transaction.atomic
def verify(user,code):
    row=StaffMFA.objects.select_for_update().filter(user=user).first()
    if not row:return False
    secret=cipher().decrypt(row.encrypted_secret.encode()).decode();step=validate(secret,code,row.last_step)
    if step is None:return False
    row.last_step=step;row.save();return True
