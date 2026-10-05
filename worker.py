"""One durable coordinator drives ten independent CLI accounts and quality gates."""
import hashlib, json, os, threading, time
from pathlib import Path
from state import ROOT, ROLES, initialize, connect, config, claim, audit, heartbeat,recover_interrupted
from tools import Project, research
from media import native,inspect_image,image_requirement,visual_gate,generation_brief
from agent import decide
from deliverables import requested_format,collect
from autonomy import normalize_spec,fingerprint,artifact_check,verification,review_completion,goal_gate,public_progress
CONTRACT_ASSIGNMENT={"backend":"Produce the exact deliverables in the goal contract using available tools. Never substitute a different format."}

def review_verdict(action):
    if not isinstance(action.get('approved'),bool):raise ValueError('Review approved must be an explicit JSON boolean')
    issues=action.get('issues',[])
    if not isinstance(issues,list) or not all(isinstance(s,str) for s in issues):raise ValueError('Review issues must be a list of strings')
    return {'approved':action['approved'],'issues':issues[:20]}

def assigned_roles(action):
    kind=action.get('type')
    if kind not in ('web','mobile','python','other','document','research','presentation','image'):raise ValueError('Invalid task type')
    roles=action.get('roles')
    defaults={'web':['architect','backend','frontend'],'mobile':['architect','backend','mobile'],'python':['backend'],'other':['backend'],'document':['backend'],'research':['research','backend'],'presentation':['research','backend'],'image':['frontend']}
    if roles is None:roles=defaults[kind]
    eligible={'research','architect','backend','frontend','mobile'}
    if not isinstance(roles,list) or not 1<=len(roles)<=5 or len(set(roles))!=len(roles) or any(r not in eligible for r in roles):raise ValueError('roles must contain 1-5 unique implementation slots: research, architect, backend, frontend, mobile. Testing, debugging, review and release are attached automatically; omit them from roles. Received: '+str(roles)[:300])
    if not isinstance(action.get('acceptance'),list) or not 1<=len(action['acceptance'])<=20 or not all(isinstance(s,str) and 5<=len(s)<=500 for s in action['acceptance']):raise ValueError('acceptance must be a list of 1-20 complete criterion strings, each 5-500 characters; include the full goal, deliverables and assignments in spec')
    return roles

def publish(root,c,task,project,memory):
    if not (memory.get('review') or {}).get('approved'):raise ValueError('Explicit approved review required')
    proof=[e for e in memory.get('test_evidence',[]) if e.get('role')=='testing']
    last_cycle=max((e['cycle'] for e in proof),default=-1);latest=[e for e in proof if e['cycle']==last_cycle]
    if memory.get('autonomy_version')==2:latest=[e for e in latest if e.get('fingerprint')==fingerprint(project)]
    if (memory.get('spec') or {}).get('type') not in ('document','research') and (not latest or any(e['exit_code']!=0 or e['timed_out'] or (e['kind']=='browser_test' and not e.get('browser',{}).get('passed')) or (e['kind']=='presentation_check' and not e.get('presentation',{}).get('passed')) for e in latest)):raise ValueError('Passing executed final tester evidence required')
    if (memory.get('spec')or{}).get('type')=='web' and not any(e['kind']=='browser_test' and e.get('browser',{}).get('passed') for e in latest):raise ValueError('Passing web browser evidence required')
    if memory.get('autonomy_version')==2:
        if not goal_gate(memory,project,last_cycle):raise ValueError('Goal contract, fresh acceptance checks and independent review must all pass')
        artifact_check(project,memory['spec'])
        if not visual_gate(memory,project,last_cycle,review=True):raise ValueError('Final native image/slide visual evidence or image provenance is missing')
    outputs=collect(project,memory)
    if memory.get('output_contract'):
        checks=[p for p in latest if p['kind']=='presentation_check' and p.get('presentation',{}).get('passed')]
        if not checks:raise ValueError('Requested PowerPoint needs an executed final render check')
    dest=Path(root)/'downloads';dest.mkdir(exist_ok=True)
    project.write([{'path':'WORKSHOP_EVIDENCE.json','content':json.dumps({'notes':memory['notes'],'tests':memory['test_evidence'],'review':memory['review']},indent=2)}])
    artifact=dest/(task['id']+'.zip');digest=project.package(artifact)
    for output in outputs:
        import shutil
        exported=dest/task['id']/output['path'];exported.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(project.path(output['path']),exported);exported.chmod(0o644)
        c.execute('INSERT OR REPLACE INTO deliverables VALUES(?,?,?,?)',(task['id'],output['path'],output['mime'],output['size']))
    c.execute('INSERT OR REPLACE INTO artifacts VALUES(?,?,?,?)',(task['id'],digest,artifact.stat().st_size,time.time()))
    summary=('Goal achieved: '+memory['spec']['goal']+' | '+str(len(outputs))+' requested file(s), acceptance checked and independently reviewed') if memory.get('autonomy_version')==2 else ('Verified requested files' if outputs else 'Verified source package')
    c.execute("UPDATE tasks SET status='ready',role=NULL,error=NULL,summary=?,updated=? WHERE id=?",(summary,time.time(),task['id']))
    c.execute("INSERT INTO notifications(task_id) VALUES(?) ON CONFLICT(task_id) DO UPDATE SET status='pending',error=NULL WHERE notifications.status NOT IN ('sending','uncertain')",(task['id'],));audit(c,'coordinator','ready',task['id'],digest)

def process(root,c,task,decision=decide):
    cfg=config(root);project=Project(root,task['id'],cfg);started=time.monotonic()
    if task.get('parent_id') and not (task.get('recovery_attempts') and project.files()):
        import shutil
        parent=c.execute('SELECT user_id,status FROM tasks WHERE id=?',(task['parent_id'],)).fetchone()
        if not parent or parent['user_id']!=task['user_id'] or parent['status'] in ('queued','working'):raise ValueError('Cannot revise this project')
        old=Project(root,task['parent_id'],cfg)
        for item in old.files():
            if item['path']=='WORKSHOP_EVIDENCE.json':continue
            dest=project.path(item['path']);dest.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(old.path(item['path']),dest)
    memory={'image_contract':image_requirement(task['prompt']),'image_provenance':{},'media_attempts':0,'research_evidence':[],'output_contract':requested_format(task['prompt']),'response':None,'assignments':{},'request':task['prompt'],'autonomy_version':2,'verification':None,'spec':None,'notes':[],'temporary_skills':[],'test_evidence':[],'review':None,'tool_history':[],'previous_tool_result':None}
    memory['conversation']=[{'user':r['prompt'],'assistant':r['summary']} for r in reversed(c.execute("SELECT prompt,summary FROM tasks WHERE user_id=? AND status='answered' ORDER BY created DESC LIMIT 6",(task['user_id'],)).fetchall())]
    memory_path=Path(root)/'private'/'memory'/task['id'];memory_path.parent.mkdir(exist_ok=True)
    if task.get('recovery_attempts') and memory_path.exists():
        saved=json.loads(memory_path.read_text())
        memory['recovery_context']={'previous_goal':(saved.get('spec')or{}).get('goal'),'peer_notes':saved.get('notes',[])[-8:],'previous_review_issues':(saved.get('review')or{}).get('issues',[]),'previous_verification':saved.get('verification'),'instruction':'A worker interruption retained the task source. Replan from the original request and actual files. All prior approval and test evidence is stale: independently execute fresh checks before release.'}
    stage='understand';stage_cycle=0
    def persist():
        memory_path.write_text(json.dumps(memory,ensure_ascii=False),encoding='utf-8')
        c.execute('UPDATE tasks SET progress=?,updated=? WHERE id=?',(json.dumps(public_progress(memory,stage,stage_cycle)),time.time(),task['id']))
    def run_role(role,cycle):
        nonlocal stage,stage_cycle
        stage=role;stage_cycle=cycle
        if role=='testing':memory['verification']=None
        if role=='review':memory['review']=None
        persist()
        c.execute('UPDATE tasks SET role=?,cycle=?,updated=? WHERE id=?',(role,cycle,time.time(),task['id']))
        heartbeat(c,role,'working',task['id']);audit(c,role,'role_started',task['id'])
        try:
            errors=0;transport_errors=0
            for turn in range(cfg['max_turns_per_role']):
                row=c.execute('SELECT cancel FROM tasks WHERE id=?',(task['id'],)).fetchone()
                if row[0]:raise RuntimeError('Task cancelled')
                if time.monotonic()-started>cfg['task_deadline']:raise TimeoutError('Task deadline reached')
                tree=project.files()
                source={};budget=100000
                for item in tree:
                    if item['size']>min(budget,64000) or not item['path'].endswith(('.py','.php','.js','.mjs','.json','.md','.html','.css','.yml','.yaml','.dart','.kt','.java','.txt')):continue
                    try:content=project.read(item['path'])
                    except (UnicodeError,OSError,ValueError):continue
                    source[item['path']]=content;budget-=len(content.encode())
                context=dict(memory,assignment=memory['assignments'].get(role,CONTRACT_ASSIGNMENT.get(role,'')),verification_requirement=('Execute NEW acceptance checks in this cycle. Prior-cycle evidence cannot satisfy this pass. For web, run browser_test again even if unchanged.' if role=='testing' else ''),tree=tree,source_files=source,role=role,cycle=cycle,turn=turn,remaining_turns=cfg['max_turns_per_role']-turn)
                try:
                    try:action=decision(root,c,cfg,task,role,context)
                    except (TimeoutError,RuntimeError) as e:
                        if not isinstance(e,TimeoutError) and not str(e).startswith('CLI process failed'):raise
                        transport_errors+=1;memory['previous_tool_result']={'error':'Model transport failed or timed out; bounded retry '+str(transport_errors)};persist();audit(c,role,'model_retry',task['id'],str(e)[:300])
                        if transport_errors>=3:
                            if role=='intake' and not memory['spec']:raise RuntimeError('Intake model transport unavailable') from e
                            if role=='review':memory['review']={'approved':False,'issues':['Reviewer model transport unavailable']}
                            memory['notes'].append({'role':role,'summary':'Model transport unavailable after three attempts. Contribution incomplete; quality gates remain enforced.'});persist();return
                        continue
                    kind=action['action']
                    if role=='review' and kind not in ('read','research','visual_check','review','done','decline','blocked'):raise ValueError('Independent review is read-only')
                    if kind=='spec':
                        if role!='intake':raise ValueError('Only intake assigns tasks')
                        roles=assigned_roles(action)
                        if memory['output_contract'] and action['type']!='presentation':raise ValueError('This request requires a real PowerPoint .pptx. Use type presentation, not document or web.')
                        if memory['image_contract'] and action['type']!='image':raise ValueError('Requested generated image needs type image and native image_generate; code or notes are not substitutes')
                        assignments=action.get('assignments',{})
                        if not isinstance(assignments,dict) or set(assignments)!=set(roles) or any(not isinstance(v,str) or not 10<=len(v)<=1500 for v in assignments.values()):raise ValueError('Give every selected specialist a concrete task-specific assignment')
                        memory['assignments']=assignments
                        contract=normalize_spec(action,project)
                        memory['spec']=dict(contract,type=action['type'],acceptance=action['acceptance'],roles=roles);result={'spec':memory['spec']}
                        team=['intake']+roles+['testing','debugging','review','release']
                        c.execute('UPDATE tasks SET mode=?,team=? WHERE id=?',(action['type'],json.dumps(team),task['id']))
                        audit(c,role,'team_assigned',task['id'],json.dumps({'roles':team,'assignments':assignments}))
                    elif kind=='respond':
                        if role!='intake' or memory['spec'] or memory['output_contract'] or memory['image_contract']:raise ValueError('Direct responses are intake-only before a build plan')
                        text=action.get('text')
                        if not isinstance(text,str) or not 1<=len(text.strip())<=12000:raise ValueError('Invalid response')
                        memory['response']=text.strip();persist();return
                    elif kind=='write':
                        if role=='testing' and any(not (f['path'].startswith('tests/') or f['path']=='TEST_PLAN.md' or (f['path'].startswith('test_') and f['path'].endswith('.py'))) for f in action['files']):raise ValueError('Testing may write only test files and TEST_PLAN.md; report implementation defects for debugging')
                        result=project.write(action['files'])
                        if memory['output_contract'] and any(f['path']=='presentation.json' for f in action['files']):
                            build=project.presentation(json.loads(project.read('presentation.json')),memory['output_contract'])
                            result=dict(result,presentation_build=build,exit_code=build['exit_code'],stderr=build.get('stderr',''))
                    elif kind=='read':result={'path':action['path'],'content':project.read(action['path'])}
                    elif kind in ('run','browser_test'):
                        result=project.command(action['argv'] if kind=='run' else action['server'],None if kind=='run' else action['steps'])
                        if role in ('testing','debugging'):
                            proof=dict(result,role=role,cycle=cycle,kind=kind,argv=action.get('argv',action.get('server')),evidence_id='E'+str(len(memory['test_evidence'])+1),fingerprint=fingerprint(project))
                            memory['test_evidence'].append(proof)
                    elif kind=='image_generate':
                        if role!='debugging' and role not in (memory.get('spec')or{}).get('roles',[]):raise ValueError('Only assigned implementation specialists or debugging generate images')
                        if memory['media_attempts']>=4:raise RuntimeError('Image-generation retry budget reached; no invented output accepted')
                        memory['media_attempts']+=1
                        try:
                            result=native(project,c,task,role,'generate',generation_brief(memory['request'],action['prompt']),paths=action.get('reference_paths',[]),output=action['path'])
                            memory['image_provenance'][action['path']]=result
                        except (RuntimeError,TimeoutError) as error:
                            result={'exit_code':1,'timed_out':isinstance(error,TimeoutError),'error':str(error),'scope':'No verified generated image; use concrete error to repair or report blocked'}
                    elif kind=='visual_check':
                        if role not in ('testing','review','debugging'):raise ValueError('Visual checks belong to independent testing/review or debugging')
                        result=native(project,c,task,role,'inspect',memory['request']+'\nAdditional checks: '+str(action.get('checks','')),paths=action['paths'])
                        memory['test_evidence'].append(dict(result,role=role,cycle=cycle,kind=kind,evidence_id='E'+str(len(memory['test_evidence'])+1),fingerprint=fingerprint(project)))
                    elif kind=='presentation':
                        if role=='testing':raise ValueError('Tester must check existing slides; report content defects to debugging')
                        result=project.presentation(action['deck'],memory['output_contract'])
                    elif kind=='presentation_check':
                        result=project.check_presentation(action['path'],memory['output_contract'])
                        if role in ('testing','debugging'):memory['test_evidence'].append(dict(result,role=role,cycle=cycle,kind=kind,evidence_id='E'+str(len(memory['test_evidence'])+1),fingerprint=fingerprint(project)))
                    elif kind=='artifact_check':
                        if role not in ('testing','debugging'):raise ValueError('Only testers or debuggers execute artifact_check')
                        try:result=artifact_check(project,memory['spec'])
                        except (ValueError,OSError) as e:result={'exit_code':1,'timed_out':False,'stderr':str(e),'files':[]}
                        memory['test_evidence'].append(dict(result,role=role,cycle=cycle,kind=kind,evidence_id='E'+str(len(memory['test_evidence'])+1),fingerprint=fingerprint(project)))
                    elif kind=='verify':
                        if role!='testing':raise ValueError('Only independent tester verifies acceptance')
                        memory['verification']=verification(action,memory,cycle,project);result=memory['verification']
                        audit(c,role,'acceptance_verified',task['id'],json.dumps(result))
                    elif kind=='research':
                        result=research(action['url'],cfg,action.get('focus'))
                        memory['research_evidence']=(memory['research_evidence']+[{'url':result['url'],'status':result['status'],'content':result['content'][:10000]}])[-12:]
                    elif kind=='skill':
                        if role not in ('intake','architect'):raise ValueError('Only intake and architect create temporary skills')
                        name=action['name'];content=action['content']
                        import re
                        if not isinstance(name,str) or not re.fullmatch('[a-z][a-z0-9-]{2,60}',name) or not isinstance(content,str) or not 20<=len(content)<=6000:raise ValueError('Invalid temporary skill')
                        if len(memory['temporary_skills'])>=12:raise ValueError('Temporary skill limit reached')
                        skill={'name':name,'content':content,'created_by':role,'trust':'task-data-only'};memory['temporary_skills'].append(skill)
                        project.write([{'path':'task-skills/'+name+'.md','content':content}]);result={'skill_created':name}
                    elif kind=='review':
                        if role!='review':raise ValueError('Only independent review may approve')
                        if action.get('approved') and not visual_gate(memory,project,cycle,review=True):raise ValueError('Approval requires actual native visual review of every final image/slide, and native generation provenance for requested images')
                        memory['review']=dict(review_verdict(action),**review_completion(action,memory,project));audit(c,role,'review_verdict',task['id'],json.dumps(memory['review']));persist();return
                    elif kind=='done':
                        if role=='testing':
                            if not memory.get('verification') or memory['verification']['cycle']!=cycle:raise ValueError('Use verify to evaluate every goal criterion against current evidence before done')
                            proof=[p for p in memory['test_evidence'] if p['role']=='testing' and p['cycle']==cycle]
                            if memory['output_contract'] and not any(p['kind']=='presentation_check' for p in proof):raise ValueError('Execute presentation_check on the actual .pptx in this cycle before done')
                            if not proof:raise ValueError('Execute NEW tests in this cycle before done; previous results do not count')
                            if memory['spec']['type']=='web' and not any(p['kind']=='browser_test' for p in proof):raise ValueError('Run a NEW browser_test in this cycle before done; prior browser evidence does not count')
                        if role=='intake' and not memory['response'] and (not memory['spec'] or not memory['temporary_skills']):raise ValueError('Intake must create a spec and at least one temporary skill before done')
                        memory['notes'].append({'role':role,'cycle':cycle,'summary':str(action.get('summary',''))[:2500]});persist();return
                    elif kind=='blocked':raise RuntimeError('Required capability unavailable: '+str(action.get('reason','Missing concrete reason'))[:700])
                    elif kind=='decline':raise RuntimeError('Model declined: '+str(action.get('reason',''))[:500])
                    else:raise ValueError('Unknown tool action')
                    memory['previous_tool_result']={'role':role,'action':kind,'result':result}
                    # Compact history persists failed commands and avoids stateless reread loops.
                    history={'role':role,'action':kind,'result':dict(result)}
                    for field in ('content','stdout','stderr'):
                        if isinstance(history['result'].get(field),str):history['result'][field]=history['result'][field][-4000:]
                    memory['tool_history']=(memory['tool_history']+[history])[-12:]
                    persist();audit(c,role,'tool_result',task['id'],json.dumps(memory['previous_tool_result'])[:11000])
                except (ValueError,KeyError) as e:
                    errors+=1;memory['previous_tool_result']={'error':str(e)[:500]};persist()
                    audit(c,role,'tool_validation_failed',task['id'],str(e)[:500])
                    if errors>=3:
                        if role=='testing':
                            memory['notes'].append({'role':role,'summary':'Missing valid execution evidence: '+str(e)});persist();return
                        raise RuntimeError('Invalid actions from '+role+': '+str(e)[:500]) from e
            if role=='intake' and not memory['response'] and (not memory['spec'] or not memory['temporary_skills']):raise RuntimeError('Intake did not establish a valid task specification')
            if role=='review':memory['review']={'approved':False,'issues':['Reviewer exhausted its turn limit without a verdict']}
            note={'role':role,'cycle':cycle,'summary':'Turn limit reached. Contribution is partial; pass remaining work and actual tool failures to independent testing/debugging. This is not a completion claim.'}
            memory['notes'].append(note);persist();audit(c,role,'partial_handoff',task['id'],note['summary'])
        finally:heartbeat(c,role,'idle');audit(c,role,'role_finished',task['id'])
    run_role('intake',0)
    if memory['response']:
        c.execute("UPDATE tasks SET status='answered',mode='chat',team=?,role=NULL,error=NULL,summary=?,updated=? WHERE id=?",(json.dumps(['intake']),memory['response'],time.time(),task['id']))
        c.execute("INSERT INTO notifications(task_id) VALUES(?) ON CONFLICT(task_id) DO UPDATE SET status='pending',error=NULL WHERE notifications.status NOT IN ('sending','uncertain')",(task['id'],));audit(c,'intake','answered',task['id'],memory['response']);return
    for role in memory['spec']['roles']:run_role(role,0)
    for cycle in range(cfg['max_revision_cycles']+1):
        if cycle>0:run_role('debugging',cycle)
        run_role('testing',cycle);run_role('review',cycle)
        if goal_gate(memory,project,cycle):break
        memory['notes'].append({'role':'coordinator','summary':'Goal not achieved. Repair concrete failed criteria and review issues; then independently recheck the changed outputs.'});persist()
    else:raise RuntimeError('Revision limit reached; requested goal remains incomplete: '+('; '.join((memory.get('review')or{}).get('issues',[])[:3])[:900] or 'Acceptance checks did not pass'))
    if memory['spec']['type'] in ('image','presentation'):
        # Native artifacts have no application setup step. Publish unchanged,
        # independently tested/reviewed files instead of adding irrelevant source docs.
        publish(root,c,task,project,memory)
        stage='delivered';stage_cycle=cycle;persist();return
    run_role('release',cycle)
    for final_cycle in range(cycle+1,cycle+cfg['max_revision_cycles']+2):
        run_role('testing',final_cycle);run_role('review',final_cycle)
        if goal_gate(memory,project,final_cycle):break
        memory['notes'].append({'role':'coordinator','summary':'Final release verification failed. Repair and check the final files again; earlier evidence is stale after changes.'});persist()
        if final_cycle<cycle+cfg['max_revision_cycles']+1:run_role('debugging',final_cycle)
    else:raise RuntimeError('Final release verification failed after bounded repair attempts')
    publish(root,c,task,project,memory)
    stage='delivered';stage_cycle=final_cycle;persist()

def main(root=ROOT):
    import fcntl,subprocess
    initialize(root);lock=open(Path(root)/'private'/'worker.lock','a');fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
    c=connect(root)
    lane=c.execute("SELECT value FROM settings WHERE key='queue_lane_active'").fetchone()
    protected=[lane[0]] if lane and subprocess.run(['systemctl','is-active','coding-queue-lane.service'],capture_output=True,text=True).stdout.strip()=='active' else []
    recover_interrupted(c,config(root),exclude=protected)
    for role in ROLES:
        current=c.execute('SELECT task_id FROM heartbeats WHERE role=?',(role,)).fetchone()
        if not current or current[0] not in protected:heartbeat(c,role,'idle')
    def pulse():
        db=connect(root)
        while True:
            db.execute('UPDATE heartbeats SET updated=?',(time.time(),));time.sleep(5)
    threading.Thread(target=pulse,daemon=True).start()
    while True:
        task=claim(c)
        if not task:time.sleep(2);continue
        try:
            import subprocess
            from process_control import kill_tree
            # Each task imports fresh reviewed source; deployments do not interrupt another build.
            logdir=Path(root)/'private'/'task-logs';logdir.mkdir(exist_ok=True)
            with open(logdir/(task['id']+'.log'),'w') as log:
                proc=subprocess.Popen(['/usr/bin/python3',str(Path(root)/'task_runner.py'),task['id']],stdout=log,stderr=log)
                try:proc.wait(timeout=config(root)['task_deadline']+config(root)['model_timeout']+60)
                except subprocess.TimeoutExpired:kill_tree(proc);raise TimeoutError('Task subprocess exceeded hard deadline')
            if proc.returncode:raise RuntimeError('Task subprocess failed; inspect private operator log')
        except Exception as e:
            error=str(e)[:1200];audit(c,'coordinator','failed',task['id'],error)
            c.execute("UPDATE tasks SET status=CASE WHEN cancel=1 THEN 'cancelled' ELSE 'needs_attention' END,error=?,role=NULL,updated=? WHERE id=?",(error,time.time(),task['id']))
            c.execute("INSERT INTO notifications(task_id) VALUES(?) ON CONFLICT(task_id) DO UPDATE SET status='pending',error=NULL WHERE notifications.status NOT IN ('sending','uncertain')",(task['id'],))
        finally:
            c.execute("UPDATE heartbeats SET status='idle',task_id=NULL,updated=? WHERE task_id=?",(time.time(),task['id']))
if __name__=='__main__':main()
