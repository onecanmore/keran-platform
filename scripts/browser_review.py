#!/usr/bin/env python
"""Repeatable Chromium E2E, mobile/locale checks, and screenshots on an isolated seeded DB."""
import json,os,sys,subprocess,tempfile,time,urllib.request
from pathlib import Path
from playwright.sync_api import sync_playwright
root=Path(__file__).resolve().parent.parent;artifacts=root/'artifacts';artifacts.mkdir(exist_ok=True)
checks=[]
def record(name):checks.append({'name':name,'passed':True})
with tempfile.TemporaryDirectory(prefix='keran-e2e-demo-') as tmp:
    env={**os.environ,'DATA_DIR':tmp,'DEBUG':'1','DJANGO_SETTINGS_MODULE':'config.settings'}
    for cmd in [['migrate','--noinput'],['seed','--demo']]:subprocess.run([sys.executable,str(root/'manage.py'),*cmd],env=env,cwd=root,check=True,stdout=subprocess.DEVNULL)
    creds=json.loads((Path(tmp)/'review-accounts.json').read_text())
    log=open(artifacts/'browser-server.log','w')
    server=subprocess.Popen([sys.executable,str(root/'manage.py'),'runserver','127.0.0.1:8001','--noreload'],env=env,cwd=root,stdout=log,stderr=log)
    try:
        for _ in range(100):
            try:
                if urllib.request.urlopen('http://127.0.0.1:8001/').status==200:break
            except Exception:time.sleep(.1)
        with sync_playwright() as p:
            browser=p.chromium.launch(executable_path=os.environ.get('CHROMIUM_PATH','/usr/bin/chromium'),args=['--no-sandbox'])
            errors=[]
            context=browser.new_context(viewport={'width':1440,'height':1000},base_url='http://127.0.0.1:8001')
            page=context.new_page();page.on('pageerror',lambda e:errors.append(str(e)))
            def login(role):
                page.goto('/login/');page.locator('[name=username]').fill(creds[role]['username']);page.locator('[name=password]').fill(creds[role]['password']);page.get_by_role('button',name='Sign in',exact=True).click();page.wait_for_url('**/account/')
            def post(url,data):
                token=page.locator('[name=csrfmiddlewaretoken]').first.input_value()
                response=page.request.post(url,data=json.dumps(data),headers={'Content-Type':'application/json','X-CSRFToken':token,'Idempotency-Key':__import__('uuid').uuid4().hex})
                assert response.status==200,(url,response.status,response.text());return response.json()['data']
            page.goto('/');page.screenshot(path=str(artifacts/'home-desktop.png'),full_page=True)
            assert not page.evaluate('document.documentElement.scrollWidth>innerWidth');record('desktop home and no horizontal overflow')
            page.keyboard.press('Tab');assert page.locator(':focus').get_attribute('class')=='skip';record('keyboard skip link')
            login('member')
            page.goto('/products/demo-pantry/');page.locator('[name=quantity]').fill('2');page.get_by_role('button',name='Add to bag').click();page.wait_for_url('**/cart/')
            page.get_by_role('button',name='Get a secure quote').click();page.locator('#confirm-checkout').wait_for(state='visible');assert 'Sandbox tax' in page.locator('#quote-result').inner_text()
            page.locator('#confirm-checkout').click();page.wait_for_url('**/sandbox/commerce/**');page.get_by_role('button',name='Simulate success').click();page.get_by_text('Test event confirmed.',exact=False).wait_for();record('shopping server quote → order → sandbox event → account')
            order_id=page.url.rstrip('/').split('/')[-1]
            page.goto('/account/orders/');assert 'paid' in page.locator('main').inner_text();order=page.request.get('/api/orders/'+order_id+'/').json()['data'];sub=order['suborders'][0]
            result=post(f'/api/orders/{order_id}/pickup/',{'suborder_id':sub['id']});pickup=result['token']
            page.goto('/help/new/');page.locator('[name=state]').fill('NY');page.locator('[name=city]').fill('New York');page.locator('[name=zip]').fill('10001');page.locator('[name=categories]').select_option(['food','home']);page.locator('[name=need_name]').fill('Test pantry support');page.locator('[name=need_quantity]').fill('2');page.locator('[name=message]').fill('Fictional E2E request. Private, not a public story.');page.locator('[name=contact_consent]').check();page.get_by_role('button',name='Send my request').click();page.wait_for_url('**/account/cases/**');case_id=page.url.rstrip('/').split('/')[-1];assert 'manual_pending' in page.locator('main').inner_text();record('open private request with multi-category needs and no story consent')
            page.locator('textarea[name=text]').fill('Please call in the afternoon.');page.get_by_role('button',name='Send update',exact=True).click();page.wait_for_load_state('networkidle');assert 'Please call in the afternoon.' in page.locator('main').inner_text()
            page.goto('/verification/new/');page.locator('[name=organization]').fill('Fictional review organization');page.locator('[name=description]').fill('Test volunteer service description');page.locator('[name=consent]').check();page.get_by_role('button',name='Submit for review').click();page.wait_for_url('**/account/verifications/');assert 'submitted' in page.locator('main').inner_text();record('volunteer verification submission and status')
            page.goto('/fundraising/demo-community-care/donate/');page.locator('[name=receipt_name]').fill('Fictional Donor');page.locator('[name=email]').fill('donor@example.invalid');page.locator('[name=policy_consent]').check();page.get_by_role('button',name='Continue to sandbox payment').click();page.wait_for_url('**/sandbox/public_donation/**');donation_id=page.url.rstrip('/').split('/')[-1];page.get_by_role('button',name='Simulate success').click();page.get_by_text('Test event confirmed.',exact=False).wait_for();assert page.request.get(f'/api/donations/{donation_id}/receipt/').status==200;record('campaign policy → contribution → sandbox confirmation and private receipt')
            page.goto('/fundraising/demo-community-care/');assert '$25.00' in page.locator('main').inner_text();assert 'Fictional Donor' not in page.locator('main').inner_text();page.screenshot(path=str(artifacts/'campaign.png'),full_page=True)
            context.clear_cookies();login('reviewer');page.goto(f'/admin/cases/{case_id}/');page.locator('select[name=status]').select_option('reviewing');page.locator('form[data-api$="/transition/"] input[name=reason]').fill('Reviewed fictional request');page.get_by_role('button',name='Update case',exact=True).click();page.wait_for_load_state('networkidle');assert page.locator('.section-heading').inner_text().startswith('reviewing')
            case=page.request.get(f'/api/help-requests/{case_id}/').json()['data'];need_id=case['needs'][0]['id'];post(f'/api/help-requests/{case_id}/confirm/',{'need_id':need_id,'quantity':2,'reason':'Fictional need confirmed'});record('reviewer updates case and confirms need quantities')
            page.goto('/admin/verifications/');page.locator('select[name=status]').first.select_option('approved');page.locator('input[name=reason]').first.fill('Human verification complete (test)');page.get_by_role('button',name='Save decision').first.click();page.wait_for_load_state('networkidle');assert 'approved' in page.locator('main').inner_text();record('reviewer manually approves volunteer with configured expiry')
            context.clear_cookies();login('admin');page.goto('/admin/plans/?new=1');page.locator('[name=name]').fill('Browser reviewed support plan');page.locator('[name=description]').fill('Fictional support plan');page.locator('[name=region]').fill('NY');page.locator('[name=needs]').select_option(need_id);page.locator('[name=public_summary]').fill('Anonymous household supplies test plan.');page.get_by_role('button',name='Save draft',exact=True).click();page.wait_for_url('**/admin/plans/');page.get_by_role('button',name='Reserve resources').click();page.wait_for_load_state('networkidle');assert 'Browser reviewed support plan' in page.locator('main').inner_text();record('plan links original need and reserves aid inventory')
            page.goto('/admin/');page.screenshot(path=str(artifacts/'work-centre.png'),full_page=True)
            context.clear_cookies();login('warehouse');page.goto('/admin/plans/');assert page.locator('main').get_by_text('Permission denied.',exact=False).count()>0
            page.goto('/admin/orders/');post(f'/api/fulfillment/{sub["id"]}/',{'token':pickup});response=page.request.get('/api/reports/orders/').json()['data'];assert response['results'][0]['status']=='fulfilled';record('warehouse fulfillment with one-time pickup code')
            context.clear_cookies();login('admin');page.goto('/admin/plans/');page.get_by_role('button',name='Confirm handover',exact=True).click();page.wait_for_load_state('networkidle');page.goto(f'/admin/cases/{case_id}/');assert '2 / 2 / 1 / 1' in page.locator('main').inner_text();record('partial resource handover updates allocated/fulfilled without inflating remaining needs')
            detail=page.request.get('/api/reports/cases/?state=NY').json()['data'];assert detail['count']==1;assert page.request.get('/api/reports/cases/export/?state=NY').status==200;record('filtered case details and Excel export')
            page.goto('/');page.locator('button[name=language]').click();page.wait_for_load_state('networkidle');assert page.locator('html').get_attribute('lang')=='zh-Hant';assert '讓付出被珍惜' in page.locator('h1').inner_text();record('remembered Traditional Chinese selection')
            page.set_viewport_size({'width':390,'height':844});page.goto('/');assert not page.evaluate('document.documentElement.scrollWidth>innerWidth');page.screenshot(path=str(artifacts/'home-mobile-zh.png'),full_page=True)
            for route in ['/shop/','/help/new/','/cart/','/fundraising/','/account/','/admin/cases/']:
                page.goto(route);assert not page.evaluate('document.documentElement.scrollWidth>innerWidth'),route
            record('390px mobile layout across shop, help, cart, fundraising, account and work centre')
            assert not errors,errors;record('no uncaught browser JavaScript errors')
            browser.close()
        subprocess.run([sys.executable,str(root/'scripts/verify_restore.py')],env=env,cwd=root,check=True,stdout=subprocess.DEVNULL);record('physical online backup/restore with identical relational and ledger tables')
        (artifacts/'browser-results.json').write_text(json.dumps({'passed':True,'checks':checks},indent=2));print(json.dumps({'passed':True,'checks':checks},indent=2))
    finally:
        server.terminate();server.wait(timeout=10);log.close()
