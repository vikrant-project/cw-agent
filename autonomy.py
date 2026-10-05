"""Goal contracts and evidence freshness for model-driven work, not task solutions."""
import hashlib, json, mimetypes, re, zipfile

def normalize_spec(action, project):
    goal=action.get('goal')
    if not isinstance(goal,str) or not 10<=len(goal.strip())<=1500:
        raise ValueError('State the actual user goal in spec.goal before assigning work')
    outputs=action.get('deliverables')
    if not isinstance(outputs,list) or not 1<=len(outputs)<=20:
        raise ValueError('List the actual expected files in spec.deliverables; notes are not a substitute')
    seen=set();checked=[]
    for item in outputs:
        if not isinstance(item,dict):raise ValueError('Each deliverable needs path and purpose')
        name=item.get('path');project.path(name)
        purpose=item.get('purpose')
        if name in seen or not isinstance(purpose,str) or not 5<=len(purpose)<=600:
            raise ValueError('Deliverables need unique concrete paths and a purpose')
        seen.add(name);checked.append({'path':name,'purpose':purpose})
    return {'goal':goal.strip(),'deliverables':checked,
            'criteria':[{'id':'A'+str(i+1),'requirement':s} for i,s in enumerate(action['acceptance'])]}

def fingerprint(project):
    """Ignore test outputs, not the deliverable being tested."""
    digest=hashlib.sha256()
    for item in project.files():
        name=item['path']
        if name.startswith(('task-skills/','test-evidence/','presentation-preview/')) or name in ('TEST_PLAN.md','WORKSHOP_EVIDENCE.json') or name.endswith(('.pyc','.db','.sqlite','.sqlite3','.db-wal','.db-shm')):continue
        digest.update(name.encode()+b'\0');digest.update(project.path(name).read_bytes())
    return digest.hexdigest()

def artifact_check(project,spec):
    evidence=[]
    for expected in spec['deliverables']:
        path=project.path(expected['path'])
        if not path.is_file() or path.stat().st_size==0:raise ValueError('Expected output missing or empty: '+expected['path'])
        data=path.read_bytes();ext=path.suffix.lower()
        if ext=='.pdf' and not data.startswith(b'%PDF-'):raise ValueError('Invalid PDF output')
        if ext in ('.pptx','.docx','.xlsx','.zip'):
            if not zipfile.is_zipfile(path):raise ValueError('Expected a real '+ext+' package, not renamed text')
            with zipfile.ZipFile(path) as z:
                if len(z.infolist())>5000 or sum(x.file_size for x in z.infolist())>200*1024**2:raise ValueError('Output package exceeds inspection limits')
                if z.testzip():raise ValueError('Corrupt output package')
                main={'.pptx':'ppt/presentation.xml','.docx':'word/document.xml','.xlsx':'xl/workbook.xml'}.get(ext)
                if main and main not in z.namelist():raise ValueError('Invalid '+ext+' output package')
        if ext in ('.png','.jpg','.jpeg','.webp'):
            from media import inspect_image
            inspect_image(path)
        if ext=='.json':json.loads(data)
        evidence.append({'path':expected['path'],'bytes':len(data),'sha256':hashlib.sha256(data).hexdigest()})
    return {'exit_code':0,'timed_out':False,'files':evidence,'scope':'File existence, signatures and integrity only; content requires independent acceptance review'}

def completed_visual_inspection(evidence,project):
    """A completed inspection may support individual facts while rejecting the whole image."""
    visual=evidence.get('visual') or {}
    files=visual.get('files') or []
    hashes=visual.get('sha256s') or {}
    return bool(evidence.get('kind')=='visual_check' and not evidence.get('timed_out')
                and evidence.get('exit_code') in (0,1) and isinstance(visual.get('approved'),bool)
                and visual.get('observations') and 'view_file' in visual.get('tool_names',[])
                and files and all(project.path(name).is_file() and hashes.get(name)==hashlib.sha256(project.path(name).read_bytes()).hexdigest() for name in files))

def verification(action,memory,cycle,project):
    checks=action.get('criteria');required={x['id'] for x in memory['spec']['criteria']}
    if not isinstance(checks,list) or len(checks)!=len(required):raise ValueError('Verify EVERY acceptance criterion, including failures')
    available={e['evidence_id']:e for e in memory['test_evidence'] if e['role']=='testing' and e['cycle']==cycle and e.get('fingerprint')==fingerprint(project)}
    seen=set();result=[]
    for check in checks:
        if not isinstance(check,dict):raise ValueError('Invalid criterion result')
        key=check.get('id');refs=check.get('evidence_ids');reason=check.get('reason')
        if key not in required or key in seen or not isinstance(check.get('passed'),bool) or not isinstance(reason,str) or not 5<=len(reason)<=1200:raise ValueError('Criterion needs id, explicit passed boolean, and concrete reason')
        if not isinstance(refs,list) or not refs or any(ref not in available for ref in refs):raise ValueError('Criterion must cite current-cycle executed tester evidence_ids from the unchanged project')
        if check['passed'] and any((available[ref]['exit_code']!=0 and not completed_visual_inspection(available[ref],project)) or available[ref]['timed_out'] or available[ref]['kind']=='browser_test' and not available[ref].get('browser',{}).get('passed') or available[ref]['kind']=='presentation_check' and not available[ref].get('presentation',{}).get('passed') for ref in refs):raise ValueError('Failed execution cannot support a passing criterion')
        seen.add(key);result.append({'id':key,'passed':check['passed'],'reason':reason,'evidence_ids':refs})
    return {'cycle':cycle,'fingerprint':fingerprint(project),'criteria':result,'passed':all(x['passed'] for x in result)}

def review_completion(action,memory,project):
    checks=action.get('criteria');required={x['id'] for x in memory['spec']['criteria']}
    if action.get('approved'):
        if action.get('goal_achieved') is not True:raise ValueError('Approval requires explicit goal_achieved true')
        if not isinstance(checks,list) or {x.get('id') for x in checks if isinstance(x,dict)}!=required or len(checks)!=len(required):raise ValueError('Review every acceptance criterion before approving')
        if any(x.get('passed') is not True or not isinstance(x.get('reason'),str) or len(x['reason'])<5 for x in checks):raise ValueError('Approval needs a concrete passing justification for every criterion')
        gate=memory.get('verification') or {}
        if not gate.get('passed') or gate.get('fingerprint')!=fingerprint(project):raise ValueError('Independent acceptance verification is missing, failed or stale')
    return {'goal_achieved':action.get('goal_achieved') is True,'criteria':checks if isinstance(checks,list) else [],'fingerprint':fingerprint(project)}

def goal_gate(memory,project,cycle):
    gate=memory.get('verification') or {};review=memory.get('review') or {};current=fingerprint(project)
    proof=[e for e in memory['test_evidence'] if e['role']=='testing' and e['cycle']==cycle and e.get('fingerprint')==current]
    kind=memory['spec']['type']
    from media import visual_gate
    if not visual_gate(memory,project,cycle):return False
    if not proof or any(e['exit_code']!=0 or e['timed_out'] for e in proof):return False
    if kind=='web' and not any(e['kind']=='browser_test' and e.get('browser',{}).get('passed') for e in proof):return False
    if kind=='presentation' and not any(e['kind']=='presentation_check' and e.get('presentation',{}).get('passed') for e in proof):return False
    if kind in ('python','mobile','other') and not any(e['kind'] in ('run','browser_test') for e in proof):return False
    return bool(gate.get('passed') and gate.get('cycle')==cycle and gate.get('fingerprint')==current and review.get('approved') and review.get('goal_achieved') and review.get('fingerprint')==current)

def public_progress(memory,stage,cycle):
    spec=memory.get('spec') or {};gate=memory.get('verification') or {};review=memory.get('review') or {}
    return {'goal':spec.get('goal'),'stage':stage,'cycle':cycle,'deliverables':spec.get('deliverables',[]),
            'criteria':spec.get('criteria',[]),'verification':gate.get('criteria',[]),'review_issues':review.get('issues',[]),
            'goal_achieved':bool(stage=='delivered' and review.get('approved') and review.get('goal_achieved'))}
