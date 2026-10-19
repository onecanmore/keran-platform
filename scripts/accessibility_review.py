#!/usr/bin/env python
"""axe-core checks of current local preview; install axe-core in /tmp as documented."""
import os,json
from pathlib import Path
from playwright.sync_api import sync_playwright
root=Path(__file__).resolve().parent.parent
axe=Path(os.environ.get('AXE_PATH','/tmp/keran-a11y/node_modules/axe-core/axe.min.js'))
if not axe.exists():raise SystemExit('Install axe-core@4.11.1 in /tmp/keran-a11y; see ACCEPTANCE.md.')
results=[]
with sync_playwright() as p:
    browser=p.chromium.launch(executable_path=os.environ.get('CHROMIUM_PATH','/usr/bin/chromium'),args=['--no-sandbox'])
    context=browser.new_context(bypass_csp=True,viewport={'width':1280,'height':900})
    page=context.new_page()
    for route in ['/','/shop/','/help/','/help/new/','/fundraising/','/login/']:
        page.goto('http://127.0.0.1:8000'+route,wait_until='networkidle')
        page.add_script_tag(path=str(axe))
        result=page.evaluate("async()=>{const r=await axe.run(document,{runOnly:{type:'tag',values:['wcag2a','wcag2aa','wcag21aa']}});return {violations:r.violations.map(v=>({id:v.id,impact:v.impact,description:v.description,nodes:v.nodes.map(n=>({target:n.target,summary:n.failureSummary}))})),incomplete:r.incomplete.map(v=>v.id),passes:r.passes.length};}")
        result['route']=route;results.append(result)
    browser.close()
report={'tool':'axe-core 4.11.1','note':'Automated checks supplement, not replace, human accessibility review. CSP bypass is test instrumentation only.','pages':results,'violations':sum(len(r['violations']) for r in results)}
(root/'artifacts/accessibility.json').write_text(json.dumps(report,ensure_ascii=False,indent=2));print(json.dumps(report,ensure_ascii=False,indent=2))
raise SystemExit(1 if report['violations'] else 0)
