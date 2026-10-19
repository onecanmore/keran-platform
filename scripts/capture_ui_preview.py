"""Capture the running public UI only; write eight PNGs and a self-contained offline review page."""
import base64,html,json
from pathlib import Path
from playwright.sync_api import sync_playwright
root=Path(__file__).resolve().parent.parent
out=root/'artifacts/ui-preview';out.mkdir(parents=True,exist_ok=True)
captures=[]
with sync_playwright() as p:
    browser=p.chromium.launch(executable_path='/usr/bin/chromium',headless=True,args=['--no-sandbox'])
    for lang in ['en','zh']:
        context=browser.new_context(base_url='http://127.0.0.1:8000',viewport={'width':1440,'height':1000},device_scale_factor=1)
        page=context.new_page()
        response=page.goto('/',wait_until='networkidle');assert response.status==200
        if lang=='zh':
            page.locator('button[name=language]').click();page.wait_for_load_state('networkidle')
        assert page.locator('html').get_attribute('lang')==('zh-Hant' if lang=='zh' else 'en')
        for device,size in [('desktop',{'width':1440,'height':1000}),('mobile',{'width':390,'height':844})]:
            page.set_viewport_size(size)
            for kind,route in [('home','/'),('shop','/shop/')]:
                response=page.goto(route,wait_until='networkidle');assert response.status==200
                page.evaluate('document.fonts.ready')
                assert not page.evaluate('document.documentElement.scrollWidth > innerWidth'),(lang,device,kind)
                name=f'{kind}-{device}-{lang}.png'
                page.screenshot(path=str(out/name),full_page=True,animations='disabled')
                captures.append({'id':f'{kind}-{device}-{lang}','file':name,'page':kind,'device':device,'language':lang,'viewport':size,'height':page.evaluate('document.documentElement.scrollHeight'),'url_path':route})
        context.close()
    browser.close()
controls={'page':[('home','首頁 · Home'),('shop','商城 · Shop')],'device':[('desktop','桌面 · Desktop'),('mobile','手機 · Mobile')],'lang':[('en','English'),('zh','繁體中文')]}
inputs=[];groups=[];styles=[]
for group,items in controls.items():
    labels=[]
    for i,(value,label) in enumerate(items):
        ident=f'{group}-{value}'
        inputs.append(f'<input class="sr-only" type="radio" name="{group}" id="{ident}"'+(' checked' if i==0 else '')+'>')
        labels.append(f'<label for="{ident}">{label}</label>')
        styles.append(f'body:has(#{ident}:checked) label[for="{ident}"]{{background:#174d3c;color:#fff;}}body:has(#{ident}:focus-visible) label[for="{ident}"]{{outline:3px solid #b65335;outline-offset:3px}}')
    groups.append('<div class="control-group" role="group" aria-label="'+group+'">'+''.join(labels)+'</div>')
figures=[]
for c in captures:
    styles.append(f'body:has(#page-{c["page"]}:checked):has(#device-{c["device"]}:checked):has(#lang-{c["language"]}:checked) [data-preview="{c["id"]}"]{{display:block}}')
    image=base64.b64encode((out/c['file']).read_bytes()).decode()
    alt=('首頁' if c['page']=='home' else '商城')+' · '+('桌面' if c['device']=='desktop' else '手機')+' · '+('English' if c['language']=='en' else '繁體中文')
    figures.append(f'<figure class="preview {c["device"]}" data-preview="{c["id"]}"><figcaption>{html.escape(alt)} · {c["viewport"]["width"]} × {c["height"]} px</figcaption><img src="data:image/png;base64,{image}" alt="{html.escape(alt)}完整實際介面截圖"></figure>')
css='''*{box-sizing:border-box}body{margin:0;background:#f0f0e8;color:#203d30;font:16px/1.6 system-ui,-apple-system,sans-serif}.sr-only{position:absolute;width:1px;height:1px;overflow:hidden;clip-path:inset(50%)}header{background:#faf7f0;border-bottom:1px solid #d6ddce;padding:24px 5%}h1{margin:0;font:32px Georgia,serif}header p{margin:8px 0 0;font-size:14px;color:#586650}.toolbar{display:flex;flex-wrap:wrap;gap:16px;padding:16px 5%;position:sticky;top:0;background:#faf7f0f5;z-index:2;border-bottom:1px solid #d6ddce}.control-group{display:flex;border:1px solid #a5b39b;border-radius:5px;overflow:hidden}.control-group label{display:flex;align-items:center;justify-content:center;padding:10px 18px;min-height:44px;cursor:pointer;font-size:14px;background:#fffdf5}.control-group label+label{border-left:1px solid #a5b39b}main{padding:22px 3% 50px}.preview{display:none;margin:0 auto;max-width:1440px}.preview.mobile{max-width:390px}.preview img{width:100%;height:auto;display:block;box-shadow:0 10px 35px #263d3220;border:1px solid #d1d8c9;background:#faf7f0}.preview.mobile img{border-radius:22px}figcaption{text-align:center;font-size:13px;color:#52644b;margin-bottom:16px}footer{padding:20px 5%;font-size:12px;color:#52644b} @media(max-width:600px){header{padding:20px 5%}h1{font-size:27px}.toolbar{gap:8px;padding:12px 4%}.control-group label{padding:9px 12px;font-size:12px}main{padding:16px 3%}}'''
content='<!doctype html><html lang="zh-Hant"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>KERAN · 雙語介面設計預覽</title><style>'+css+''.join(styles)+'</style></head><body>'+''.join(inputs)+'<header><h1>KERAN 共益生活 · UI 預覽</h1><p>目前運行版本的完整介面截圖。切換首頁／商城、桌面／手機、英文／繁中檢視設計。</p><p>此頁僅供靜態設計審閱，不提供結帳、登入或表單提交；畫面中的商品均為明示的測試資料。</p></header><nav class="toolbar" aria-label="預覽選擇">'+''.join(groups)+'</nav><main>'+''.join(figures)+'</main><footer>所有截圖直接擷取自本機測試網站；本檔內嵌圖片，下載後不需網路即可開啟。桌面寬度1440px，手機寬度390px。</footer></body></html>'
(out/'index.html').write_text(content)
(out/'captures.json').write_text(json.dumps(captures,ensure_ascii=False,indent=2))
print(json.dumps({'files':len(captures),'html':'artifacts/ui-preview/index.html','captures':captures},ensure_ascii=False,indent=2))
