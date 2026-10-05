"""Fresh desktop and mobile sessions against the generated sandbox application."""
import json, subprocess, sys, time, urllib.request, uuid
from pathlib import Path
from playwright.sync_api import sync_playwright

def test(spec):
    server=subprocess.Popen(spec['server'],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
    results=[];errors=[]
    try:
        for _ in range(40):
            try:
                urllib.request.urlopen('http://127.0.0.1:8765/',timeout=1);break
            except Exception:time.sleep(.2)
        with sync_playwright() as p:
            browser=p.chromium.launch(headless=True,args=['--no-sandbox'])
            for width,height in [(1440,900),(390,844)]:
                unique=uuid.uuid4().hex[:12];identity={'unique':unique,'email':'test-'+unique+'@example.test','password':'Fresh-'+unique+'!'}
                def expand(value):
                    for key,v in identity.items():value=value.replace('{'+key+'}',v)
                    return value
                context=browser.new_context(viewport={'width':width,'height':height},service_workers='block')
                context.route('**/*',lambda route: route.continue_() if route.request.url.startswith('http://127.0.0.1:8765/') else route.abort())
                page=context.new_page();page.set_default_timeout(8000);local_errors=[]
                page.on('pageerror',lambda error:local_errors.append(str(error)[:500]))
                page.on('console',lambda message:local_errors.append('Console: '+message.text[:500]) if message.type=='error' else None)
                page.on('requestfailed',lambda request:local_errors.append('Failed request: '+request.url[:200]))
                page.on('response',lambda response:local_errors.append('HTTP '+str(response.status)+': '+response.url[:200]) if response.status>=500 else None)
                page.goto('http://127.0.0.1:8765/',wait_until='networkidle',timeout=15000)
                for step in spec['steps']:
                    kind=step['type'];selector=step.get('selector')
                    if kind=='fill':page.locator(selector).fill(expand(step['value']))
                    elif kind=='click':page.locator(selector).click()
                    elif kind=='check':page.locator(selector).check()
                    elif kind=='select':page.locator(selector).select_option(expand(step['value']))
                    elif kind=='goto':
                        target=step.get('path',step.get('url',step.get('value')))
                        if not isinstance(target,str):raise ValueError('goto requires path, for example /login.php')
                        path=expand(target)
                        if path.startswith('http://127.0.0.1:8765/') :path=path[len('http://127.0.0.1:8765'):]
                        if not path.startswith('/') or path.startswith('//') or '\\' in path:raise ValueError('Local relative navigation only')
                        page.goto('http://127.0.0.1:8765'+path,wait_until='networkidle')
                    elif kind=='assert_text':
                        actual=page.locator(selector).inner_text()
                        if expand(step['value']) not in actual:raise AssertionError('Expected text missing at '+selector)
                    elif kind=='assert_not_text':
                        if expand(step['value']) in page.locator(selector).inner_text():raise AssertionError('Unexpected text at '+selector)
                    elif kind=='assert_visible':
                        if not page.locator(selector).is_visible():raise AssertionError('Element not visible: '+selector)
                    elif kind=='assert_validity':
                        if page.locator(selector).evaluate('(element)=>element.checkValidity()')!=step['valid']:raise AssertionError('Unexpected form validity at '+selector)
                    else:raise ValueError('Unknown browser step')
                overflow=page.evaluate('document.documentElement.scrollWidth > innerWidth + 2')
                evidence=Path('/project/test-evidence');evidence.mkdir(exist_ok=True)
                screenshot=evidence/('browser-'+str(width)+'.png');page.screenshot(path=str(screenshot),full_page=True)
                results.append({'viewport':[width,height],'steps':len(spec['steps']),'overflow':overflow,'page_errors':local_errors,'test_email':identity['email'],'screenshot':'test-evidence/'+screenshot.name})
                context.close()
            browser.close()
        passed=bool(spec['steps']) and any(s['type'].startswith('assert_') for s in spec['steps']) and all(not r['overflow'] and not r['page_errors'] for r in results)
        return {'passed':passed,'fresh_sessions':2,'results':results,'errors':errors}
    except Exception as e:return {'passed':False,'results':results,'errors':[str(e)[:1000]]}
    finally:
        server.terminate()
        try:server.wait(timeout=3)
        except subprocess.TimeoutExpired:server.kill();server.wait()
if __name__=='__main__':
    result=test(json.loads(sys.argv[1]));print(json.dumps(result));sys.exit(0 if result['passed'] else 1)
