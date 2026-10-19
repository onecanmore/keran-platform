from django import template
register=template.Library()
@register.simple_tag(takes_context=True)
def tr(context,en,zh):return zh if context.get('lang')=='zh' else en
@register.filter
def money(cents):return f'${(cents or 0)/100:,.2f}'
@register.filter
def label(obj,lang):return getattr(obj,'name_zh','') if lang=='zh' and getattr(obj,'name_zh','') else obj.name

@register.simple_tag(takes_context=True)
def work_title(context,section):
    labels={'overview':('Today & overview','今日工作'),'case':('Case review','案件審核'),'cases':('Support requests','需求案件'),'catalog':('Catalogue','商品管理'),'inventory':('Inventory','庫存與資產'),'fundraising':('Fundraising','公益眾籌'),'donations':('Public donations','公眾捐款'),'finance':('Finance & reconciliation','財務及對帳'),'partners':('Partners','商家及機構'),'plans':('Plans & matching','幫扶計畫與匹配'),'tasks':('Tasks','工作任務'),'orders':('Orders & fulfillment','訂單與履約'),'appointments':('Appointments','服務預約'),'verifications':('Verifications','志願者認證'),'reports':('Reports','統計報表'),'settings':('Settings & roles','設定及角色'),'audit':('Audit log','稽核日誌')}
    pair=labels.get(section,(section.title(),section))
    return pair[1] if context.get('lang')=='zh' else pair[0]

@register.simple_tag(takes_context=True)
def page_query(context,number):
    query=context['request'].GET.copy();query['page']=number;return query.urlencode()
@register.simple_tag(takes_context=True)
def sort_query(context,field):
    query=context['request'].GET.copy();query['sort']='-'+field if query.get('sort')==field else field;query.pop('page',None);return query.urlencode()
