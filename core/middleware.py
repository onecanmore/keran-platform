class LanguageMiddleware:
    def __init__(self,get_response):self.get_response=get_response
    def __call__(self,request):
        request.lang=request.session.get('language','en')
        from django.utils import translation
        translation.activate('zh-hant' if request.lang=='zh' else 'en')
        request.LANGUAGE_CODE='zh-hant' if request.lang=='zh' else 'en'
        return self.get_response(request)

class StaffMFAMiddleware:
    def __init__(self,get_response):self.get_response=get_response
    def __call__(self,request):
        from django.conf import settings
        from django.shortcuts import redirect
        from django.http import JsonResponse
        staff=request.user.is_authenticated and (request.user.is_superuser or request.user.groups.exists())
        if settings.REQUIRE_STAFF_MFA and staff and not request.session.get('staff_mfa_verified') and (request.path.startswith('/admin/') or request.path.startswith('/api/')):
            if request.path.startswith('/api/'):return JsonResponse({'error':{'code':'mfa_required','message':'Staff MFA verification is required.'}},status=403)
            return redirect('/account/security/')
        response=self.get_response(request)
        if request.user.is_authenticated or request.path.startswith(('/api/','/private/','/sandbox/')):
            response['Cache-Control']='no-store'
        response['Referrer-Policy']='same-origin'
        response['Content-Security-Policy']="default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; object-src 'none'; base-uri 'self'; frame-ancestors 'none'; form-action 'self'"
        return response
