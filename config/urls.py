from django.urls import path
from django.contrib.auth.views import LogoutView
from core import views as v,api as a
urlpatterns=[
path('catalog-images/<str:kind>/<uuid:pk>/',a.public_image),
path('api/staff/roles/',a.roles),path('api/tasks/<uuid:pk>/',a.task_action),path('api/plans/<uuid:pk>/',a.plan_action),path('api/budgets/',a.budget_create),path('api/grants/<uuid:pk>/revoke/',a.grant_action),path('api/donations/<uuid:pk>/resend/',a.receipt_resend),path('api/campaigns/<uuid:pk>/updates/',a.campaign_update),path('api/campaign-updates/<uuid:pk>/approve/',a.approve_update),path('api/stock/import/',a.stock_import),
path('',v.public),path('language/',v.language),path('login/',v.SafeLoginView.as_view(),name='login'),path('logout/',LogoutView.as_view()),path('register/',v.register),
path('shop/',v.public,{'page':'shop'}),path('care-items/',v.public,{'page':'care-items'}),path('volunteer-benefits/',v.public,{'page':'volunteer-benefits'}),path('products/<slug:slug>/',v.public,{'page':'product'}),
path('cart/',v.cart),path('cart/add/<uuid:pk>/',v.cart_add),path('checkout/',v.cart),
path('help/',v.public,{'page':'help'}),path('help/new/',v.workflow,{'page':'help_form'}),path('verification/new/',v.workflow,{'page':'verification_form'}),path('appointments/new/',v.workflow,{'page':'appointment_form'}),path('services/water/',v.public,{'page':'water'}),
path('fundraising/',v.public,{'page':'fundraising'}),path('fundraising/<slug:slug>/',v.public,{'page':'campaign'}),path('fundraising/<slug:slug>/donate/',v.public,{'page':'donate'}),path('donations/result/',v.workflow,{'page':'donation_result'}),
path('community-needs/',v.public,{'page':'community-needs'}),path('impact/',v.public,{'page':'impact'}),path('partners/',v.public,{'page':'partners'}),path('partners/apply/',v.public,{'page':'partner_form'}),path('partners/submit/',v.partner_apply),
path('privacy/',v.public,{'page':'privacy'}),path('terms/',v.public,{'page':'terms'}),path('returns/',v.public,{'page':'returns'}),path('accessibility/',v.public,{'page':'accessibility'}),
path('account/',v.member_page),path('account/cases/<uuid:pk>/',v.member_page,{'page':'case'}),path('account/<str:page>/',v.member_page),
path('admin/',v.work),path('admin/catalog/<uuid:pk>/publish/',v.publish_product),path('admin/cases/<uuid:pk>/',v.work,{'section':'case'}),path('admin/<str:section>/<uuid:pk>/',v.work),path('admin/<str:section>/',v.work),
path('sandbox/<str:purpose>/<uuid:pk>/',v.sandbox),
path('api/catalogue/',a.catalogue),path('api/help-requests/',a.cases),path('api/help-requests/<uuid:pk>/',a.cases),path('api/help-requests/<uuid:pk>/<str:action>/',a.cases),
path('api/verifications/',a.verifications),path('api/verifications/<uuid:pk>/',a.verifications),path('api/checkout/<str:action>/',a.checkout),path('api/orders/',a.orders),path('api/orders/<uuid:pk>/',a.orders),path('api/orders/<uuid:pk>/<str:action>/',a.orders),path('api/fulfillment/<uuid:pk>/',a.fulfillment),
path('api/stock/<uuid:pk>/<str:action>/',a.stock),path('api/assets/<uuid:pk>/',a.asset_action),path('api/allocations/',a.allocations),path('api/allocations/<uuid:pk>/',a.allocations),path('api/appointments/',a.appointments),path('api/appointments/<uuid:pk>/',a.appointments),
path('api/campaigns/',a.campaigns),path('api/campaigns/<uuid:pk>/',a.campaigns),path('api/campaigns/<uuid:pk>/<str:action>/',a.campaigns),path('api/donation-checkout/',a.donate),path('api/donations/<uuid:pk>/',a.donation_status),path('api/donations/<uuid:pk>/receipt/',a.donation_receipt),
path('api/refunds/',a.refunds),path('api/payment/webhook/',a.webhook),path('api/sandbox/<str:purpose>/<uuid:pk>/',a.sandbox_pay),path('api/reports/<str:kind>/',a.reports),path('api/reports/<str:kind>/export/',a.reports,{'export':True}),
path('api/attachments/',a.upload),path('api/attachments/<uuid:pk>/',a.attachment_link),path('private/<uuid:pk>/',a.attachment_download),path('api/finance/reconcile/',a.reconcile),path('api/campaign-expenses/',a.expenses),path('api/campaign-expenses/<uuid:pk>/',a.expenses),
]
