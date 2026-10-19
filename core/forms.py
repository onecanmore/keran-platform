from django import forms
from django.contrib.auth.forms import UserCreationForm, AuthenticationForm
from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from PIL import Image
from .models import Product, Campaign, Organization, Plan, Task, Lot

class RegistrationForm(UserCreationForm):
    email=forms.EmailField()
    class Meta: model=User; fields=['username','email','password1','password2']

class ProductForm(forms.ModelForm):
    class Meta:
        model=Product
        fields=['name','name_zh','slug','description','description_zh','kind','source','category','merchant','fulfiller','specifications','unit','price_cents','volunteer_price_cents','care_price_cents','donation_bps','donation_fixed_cents','policy','image','safety_confirmed']
    def clean_image(self):
        f=self.cleaned_data.get('image')
        if f and hasattr(f,'size') and f.size>5*1024*1024:raise ValidationError('Image must be at most 5 MB.')
        if f:
            try:
                img=Image.open(f);img.verify();f.seek(0)
                if img.format not in ['PNG','JPEG','WEBP'] or img.width*img.height>20000000:raise ValueError()
            except Exception:raise ValidationError('Use a valid PNG, JPEG or WEBP image.')
        return f

class CampaignForm(forms.ModelForm):
    class Meta:
        model=Campaign
        fields=['name','name_zh','slug','summary','summary_zh','body','cover','category','region','target_cents','starts_at','ends_at','budget','beneficiaries','execution','consent_basis','policy','minimum_cents','maximum_cents','suggested','allow_overfund','plan']
        widgets={'starts_at':forms.DateTimeInput(attrs={'type':'datetime-local'}),'ends_at':forms.DateTimeInput(attrs={'type':'datetime-local'})}
    def clean_cover(self):
        f=self.cleaned_data.get('cover')
        if f and f.size>5*1024*1024:raise ValidationError('Image must be at most 5 MB.')
        if f:
            try:
                img=Image.open(f);img.verify();f.seek(0)
                if img.format not in ['PNG','JPEG','WEBP'] or img.width*img.height>20000000:raise ValueError()
            except Exception:raise ValidationError('Use a valid PNG, JPEG or WEBP image.')
        return f

class OrganizationForm(forms.ModelForm):
    class Meta: model=Organization;fields=['name','kind','contact','region','agreement_status','expires_at','user','public','terms']
class PlanForm(forms.ModelForm):
    class Meta:model=Plan;fields=['name','description','region','owner','budget_cents','deadline','needs','public_summary']
class TaskForm(forms.ModelForm):
    class Meta:model=Task;fields=['title','assignee','case','due_at','status','minutes']
class LotForm(forms.ModelForm):
    class Meta:model=Lot;fields=['product','warehouse','location','owner','batch','purpose','restricted','expires_at']

LABELS_ZH={'name':'名稱（英文）','name_zh':'繁體中文名稱','slug':'公開網址代稱','description':'說明（英文）','description_zh':'說明（繁體中文）','kind':'類型','source':'來源','category':'類別','merchant':'銷售商家','fulfiller':'履約方','specifications':'規格（JSON）','unit':'計量單位','price_cents':'公開價格（USD 美分）','volunteer_price_cents':'志願者價格（USD 美分）','care_price_cents':'關懷價格（USD 美分）','donation_bps':'捐款比例（萬分比）','donation_fixed_cents':'每件固定捐款（美分）','policy':'退款、超募、未達標、取消及剩餘資金政策','image':'商品圖片','safety_confirmed':'已確認安全及用途','summary':'摘要（英文）','summary_zh':'摘要（繁體中文）','body':'公開正文','cover':'封面圖片','region':'服務地區','target_cents':'目標金額（USD 美分）','starts_at':'開始時間（紐約）','ends_at':'截止時間（紐約）','budget':'分項預算（JSON）','beneficiaries':'匿名受助對象及預計人數','execution':'執行安排','consent_basis':'發布同意依據（內部）','minimum_cents':'最低捐款（美分）','maximum_cents':'最高捐款（美分）','suggested':'建議金額（美分陣列）','allow_overfund':'依事先政策持續超募','plan':'關聯幫扶計畫','contact':'聯絡資料','agreement_status':'協議狀態','expires_at':'有效期限','user':'關聯帳號','public':'公開','terms':'已確認合作條件','owner':'負責人','budget_cents':'預算（USD 美分）','deadline':'期限','needs':'關聯原需求明細','public_summary':'對外匿名彙總（另需審核）','title':'標題','assignee':'負責人','case':'關聯案件','due_at':'跟進期限','status':'狀態','minutes':'服務分鐘數','product':'商品','warehouse':'倉庫','location':'倉位','batch':'批次','purpose':'用途池','restricted':'捐贈用途限制'}
