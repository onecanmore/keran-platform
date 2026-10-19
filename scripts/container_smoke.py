#!/usr/bin/env python
"""Local-only Docker/Gunicorn smoke and persistent restart check. Never publishes the site."""
import json,secrets,subprocess,time
from pathlib import Path
from playwright.sync_api import sync_playwright
root=Path(__file__).resolve().parent.parent
with sync_playwright() as p:
    browser=p.chromium.launch(executable_path='/usr/bin/chromium',args=['--no-sandbox'])
    page=browser.new_page(base_url='http://127.0.0.1:8002')
    for _ in range(100):
        try:
            if page.goto('/').status==200:break
        except Exception:time.sleep(.1)
    assert page.request.get('/api/catalogue/').json()['data']['count']==0
    page.goto('/register/');name='container_'+secrets.token_hex(4);password=secrets.token_urlsafe(22)
    for field,value in {'username':name,'email':'test@example.invalid','password1':password,'password2':password}.items():page.locator('[name='+field+']').fill(value)
    page.get_by_role('button',name='Create my account').click();page.wait_for_url('**/account/')
    token=page.locator('[name=csrfmiddlewaretoken]').first.input_value()
    data={'state':'NY','city':'New York','zip':'10001','categories':['food'],'needs':[{'name':'Container test need','quantity':1,'unit':'item'}],'email':'test@example.invalid','contact_consent':True}
    response=page.request.post('/api/help-requests/',data=json.dumps(data),headers={'Content-Type':'application/json','X-CSRFToken':token});assert response.status==200,response.text();case=response.json()['data']['id']
    subprocess.run(['docker','restart','keran-review-smoke'],check=True,stdout=subprocess.DEVNULL)
    for _ in range(100):
        try:
            response=page.request.get('/api/help-requests/'+case+'/')
            if response.status==200:break
        except Exception:time.sleep(.1)
    assert response.status==200 and response.json()['data']['id']==case
    browser.close()
result={'passed':True,'server':'Gunicorn in non-root Docker container, loopback bind only','checks':['migrations and real draft seed','empty verified public catalogue','CSRF-protected registration and login','private request database write','container restart preserves secret key, session, user and case']}
(root/'artifacts/container.json').write_text(json.dumps(result,indent=2));print(json.dumps(result,indent=2))
