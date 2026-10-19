from .services import config

def brand(request):
    return {'lang':getattr(request,'lang','en'),'brand':config('brand',{'name':'KERAN COMMONS','name_zh':'KERAN 共益生活'}),'sandbox':True,'cart_count':sum(request.session.get('cart',{}).values()),'staff_access':request.user.is_authenticated and (request.user.is_superuser or request.user.groups.exists())}
