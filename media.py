"""Native AntiGravity generation/vision; only task images enter an isolated workspace."""
import hashlib,json,os,re,shutil,subprocess,tempfile
from pathlib import Path
from state import ROLE_USERS,reserve,audit
from process_control import kill_tree,account_admission

def generation_brief(original,proposal):
    if not isinstance(original,str) or not isinstance(proposal,str) or not 10<=len(proposal)<=18000:raise ValueError('Invalid image design or repair proposal')
    combined='ORIGINAL USER REQUEST (preserve every requirement):\n'+original+'\n\nAGENT DESIGN OR REPAIR PLAN (must remain consistent with the original request):\n'+proposal
    if len(combined)>32000:raise ValueError('Combined image request exceeds context limit')
    return combined

def inspect_image(path,requirement=None):
    from PIL import Image,ImageStat
    requirement=requirement or {}
    with Image.open(path) as image:
        fmt=image.format;image.verify()
    with Image.open(path) as image:
        if image.width*image.height>20_000_000:raise ValueError('Image exceeds pixel limits')
        image.load();width,height=image.size
        expected={'.png':'PNG','.jpg':'JPEG','.jpeg':'JPEG','.webp':'WEBP'}.get(Path(path).suffix.lower())
        if fmt not in ('PNG','JPEG','WEBP') or not requirement.get('allow_extension_mismatch') and (not expected or fmt!=expected):raise ValueError('Image bytes do not match its declared extension')
        if width<requirement.get('min_width',512) or height<requirement.get('min_height',384):raise ValueError('Image is too small for the requested result')
        ratio=requirement.get('ratio')
        if ratio and abs(width/height-ratio)/ratio>.025:raise ValueError('Image aspect ratio does not match the request')
        variance=max(ImageStat.Stat(image.convert('RGB').resize((128,128))).var)
        if variance<10:raise ValueError('Image is blank or nearly uniform')
    return {'width':width,'height':height,'format':fmt,'sha256':hashlib.sha256(Path(path).read_bytes()).hexdigest(),'decoded':True,'scope':'Pixel decode, dimensions and file integrity; visual quality needs native vision review'}

def terminal_output(out):
    terminal=None;tools=[]
    for line in out.splitlines():
        try:record=json.loads(line)
        except ValueError:continue
        if record.get('event')=='result':terminal=record.get('result',record)
        info=(record.get('step_update')or{}).get('tool_info')
        if info and (record.get('step_update')or{}).get('state')=='DONE' and not info.get('error'):tools.append(info)
        step=record.get('step_update')or{}
        if step.get('state')=='DONE' and step.get('step_type')=='subagent' and any(x.get('type_name')=='image-generator' for x in step.get('subagent_info',{}).get('subagents',[])):tools.append({'name':'native-image-generator','parameters':step['subagent_info']})
    if not terminal:raise RuntimeError('Native AntiGravity media stream ended without a terminal result')
    if terminal.get('status')!='SUCCESS':raise RuntimeError('Native AntiGravity media failed: '+str(terminal.get('error') or terminal.get('status'))[:1200])
    answer=terminal.get('structured_output')
    if answer is None:
        value=terminal.get('response','').strip();match=re.fullmatch(r'```(?:json)?\s*([\s\S]*?)\s*```',value)
        answer=json.loads(match.group(1) if match else value)
    if not isinstance(answer,dict):raise ValueError('Native media response must be structured JSON')
    return answer,tools

def _native_once(project,c,task,role,mode,prompt,paths=None,output=None):
    def cancelled():
        row=c.execute('SELECT cancel FROM tasks WHERE id=?',(task['id'],)).fetchone()
        return not row or bool(row[0])
    with account_admission(ROLE_USERS[role],project.cfg['model_timeout'],cancelled,lambda:audit(c,role,'account_wait',task['id'],'Waiting for the existing account; no native model submission reserved')) as fd:
        return _native_admitted(project,c,task,role,mode,prompt,paths,output,fd)

def _native_admitted(project,c,task,role,mode,prompt,paths,output,fd):
    if mode not in ('generate','inspect') or not isinstance(prompt,str) or not 10<=len(prompt)<=32000:raise ValueError('Invalid media request')
    cfg=project.cfg;root=project.root;paths=paths or []
    if not isinstance(paths,list) or len(paths)>4 or any(not isinstance(v,str) for v in paths):raise ValueError('Use a list of up to four actual image paths')
    stage_root=root/'media-staging';stage_root.mkdir(mode=0o711,exist_ok=True);stage_root.chmod(0o711)
    schema={'type':'object','properties':{'approved':{'type':'boolean'},'issues':{'type':'array','items':{'type':'string'}},'observations':{'type':'array','items':{'type':'string'}}},'required':['approved','issues','observations'],'additionalProperties':False} if mode=='inspect' else {'type':'object','properties':{'created':{'type':'boolean'},'file':{'type':'string'},'limitations':{'type':'array','items':{'type':'string'}}},'required':['created','file','limitations'],'additionalProperties':False}
    import pwd
    account=pwd.getpwnam(ROLE_USERS[role]);reserve(c,cfg,task['id'],'model');audit(c,role,'model_started',task['id'],'native-'+mode)
    with tempfile.TemporaryDirectory(prefix='media-',dir=stage_root) as stage_name, tempfile.TemporaryDirectory(prefix='media-export-',dir=root/'private') as export_name:
        stage=Path(stage_name);labels=[];reference_hashes={}
        for i,name in enumerate(paths):
            source=project.path(name);reference_hashes[name]=inspect_image(source,{'min_width':1,'min_height':1})['sha256']
            label='input-'+str(i+1)+source.suffix.lower();shutil.copyfile(source,stage/label);labels.append('/workspace/'+label)
        if mode=='generate':
            project.path(output)
            if Path(output).suffix.lower() not in ('.jpg','.jpeg','.png','.webp'):raise ValueError('Use a supported raster output extension')
            native_filename='result.jpg'
            instruction='Use your built-in generate_image tool to create exactly one image. Its native artifact directory is supported: return the actual generated file path; the controller will collect the image. Do not attempt to copy or move it to /workspace/'+native_filename+'. Do not write code, SVG, Markdown, synthetic pixel placeholders or fetch stock images. Use the image-generation tool itself. Do not run commands. Wait until the native image-generator finishes; starting a subagent is not a completed image. Do not invent output paths. Report the actual tool result and failure reason. You may view reference images if supplied. Respect the requested composition and quality. Then return created/file/limitations JSON. USER IMAGE BRIEF:\n'+prompt
        else:
            instruction='This is a partial image batch from a potentially larger artifact. Do not reject because other slides or files are absent from this batch. Assess only the visible images; overall coverage is checked separately by the main reviewer. Do not require every slide to contain all requested visuals. Speaker notes and file metadata are checked separately from the artifact data, not inferred from rendered pixels. Use view_file on EVERY supplied image and visually inspect the actual pixels. Do not assume a file signature or text description establishes quality. Do not run commands, generate images, edit files or invent observations. Compare each image against the original request and provided checks. Return approved false for distortions, illegible text, overlaps, placeholder visuals or inadequate content; list concrete corrections and concise observations. Return only approved/issues/observations JSON. Images: '+json.dumps(labels)+'\nREVIEW BRIEF:\n'+prompt
        if labels and mode=='generate':instruction+='\nReference images: '+json.dumps(labels)+'. Open these actual images with view_file and use them as visual references for the native image generator. Preserve the good parts requested in the brief while correcting the observed defects. Never claim to have used an unseen reference.'
        for item in [stage,*stage.iterdir()]:os.chown(item,account.pw_uid,account.pw_gid);item.chmod(0o700 if item.is_dir() else 0o400)
        request=root/'private'/('media-request-'+task['id']+'.json');request.write_text(json.dumps({'workspace':str(stage),'mode':mode,'schema':schema,'export':export_name}))
        proc=subprocess.Popen(['/usr/bin/unshare','--net','--','/usr/bin/python3',str(root/'cli_sandbox.py'),'--role',role,'--model',cfg['model'],'--media-request',str(request)],stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,env=dict(os.environ,AGENT_MODEL_PRINT_TIMEOUT=str(cfg['model_timeout']-10)+'s',AGENT_ACCOUNT_LOCK_FD=str(fd)),pass_fds=(fd,))
        try:out,err=proc.communicate(json.dumps({'event':'user','message':{'content':instruction}})+'\n',timeout=cfg['model_timeout'])
        except subprocess.TimeoutExpired:kill_tree(proc);raise TimeoutError('Native media provider timed out')
        finally:request.unlink(missing_ok=True)
        (root/'private'/('media-log-'+task['id']+'.json')).write_text(json.dumps({'stdout':out[-600000:],'stderr':err[-20000:],'returncode':proc.returncode}))
        if proc.returncode:raise RuntimeError('Native CLI process failed with exit '+str(proc.returncode)+'; private log retained')
        answer,tools=terminal_output(out)
        manifest_path=Path(export_name)/'manifest.json'
        if manifest_path.exists():(root/'private'/('media-export-summary-'+task['id']+'.json')).write_text(manifest_path.read_text())
        names=[info.get('name',info.get('tool_name','')) for info in tools]
        audit(c,role,'native_media_result',task['id'],json.dumps({'mode':mode,'tool_names':names,'answer':answer})[:10000])
        audit(c,role,'model_finished',task['id'],'native-'+mode)
        if mode=='generate':
            manifest=json.loads(manifest_path.read_text()) if manifest_path.is_file() else {}
            validate_creation(answer,manifest)
            if labels and not all(label in json.dumps([t for t in tools if t.get('name')=='view_file']) for label in labels):raise RuntimeError('Native generator did not open every actual reference image')
            file=select_native_image(Path(export_name),answer)
            if not any(name in ('generate_image','native-image-generator') for name in names):raise RuntimeError('No native generate_image execution evidence; placeholder output rejected')
            metadata=inspect_image(file,{'min_width':512,'min_height':384})
            validate_generated_change(metadata,reference_hashes,Path(export_name))
            dest=project.path(output);dest.parent.mkdir(parents=True,exist_ok=True)
            # Preserve a previous raster for native revision, without delivering
            # rejected candidates as part of the source ZIP.
            candidates=[]
            if dest.is_file():
                try:old=inspect_image(dest)
                except (ValueError,OSError):old=None
                if old:
                    saved=project.path('image-candidates/'+old['sha256']+dest.suffix.lower());saved.parent.mkdir(parents=True,exist_ok=True)
                    if not saved.exists():shutil.copyfile(dest,saved)
            candidates=[x['path'] for x in project.files() if x['path'].startswith('image-candidates/')][-4:]

            if dest.suffix.lower() in ('.jpg','.jpeg') and metadata['format']=='JPEG':shutil.copyfile(file,dest)
            else:
                from PIL import Image
                with Image.open(file) as image:image.convert('RGB').save(dest,format='PNG' if dest.suffix.lower()=='.png' else ('JPEG' if dest.suffix.lower() in ('.jpg','.jpeg') else 'WEBP'))
            project.files();metadata=inspect_image(dest)
            return {'exit_code':0,'timed_out':False,'path':output,'image':metadata,'native_tool':'generate_image','reference_sha256s':reference_hashes,'reference_candidates':candidates,'tool_names':names,'limitations':answer.get('limitations',[])}
        viewed=json.dumps(tools)
        if not all(label in viewed for label in labels):raise RuntimeError('Native reviewer did not read every actual image')
        if not isinstance(answer.get('approved'),bool) or not isinstance(answer.get('issues'),list) or not isinstance(answer.get('observations'),list):raise ValueError('Invalid visual review verdict')
        return {'exit_code':0 if answer['approved'] else 1,'timed_out':False,'visual':dict(answer,files=paths,tool_names=names,sha256s={path:hashlib.sha256(project.path(path).read_bytes()).hexdigest() for path in paths}),'scope':'Actual native image inspection, not a prose-only approval'}


def image_requirement(prompt):
    if not re.search(r'\b(generate|create|make|draw|render)\b[\s\S]{0,200}\b(image|photo|photograph|wallpaper|artwork)\b',prompt,re.I):return None
    ratio=re.search(r'\b(\d{1,2})\s*:\s*(\d{1,2})\b',prompt)
    return {'min_width':1280 if re.search(r'photoreal|wallpaper|advertis|premium',prompt,re.I) else 512,'min_height':720 if re.search(r'photoreal|wallpaper|advertis|premium',prompt,re.I) else 384,'ratio':int(ratio[1])/int(ratio[2]) if ratio and int(ratio[2]) else None}

def visual_gate(memory,project,cycle,review=False):
    kind=(memory.get('spec') or {}).get('type')
    if kind not in ('image','presentation'):return True
    current=__import__('autonomy').fingerprint(project)
    if kind=='image':
        paths=[f['path'] for f in memory['spec']['deliverables'] if Path(f['path']).suffix.lower() in ('.png','.jpg','.jpeg','.webp')]
        if not paths:return False
        for path in paths:
            try:meta=inspect_image(project.path(path),memory.get('image_contract'))
            except (ValueError,OSError):return False
            proof=memory.get('image_provenance',{}).get(path,{})
            if proof.get('native_tool')!='generate_image' or proof.get('image',{}).get('sha256')!=meta['sha256']:return False
    else:
        if re.search(r'DDoS|protocol|technically|educational|explain',memory.get('request',''),re.I):
            sources={x.get('url') for x in memory.get('research_evidence',[]) if x.get('status')==200 and len(x.get('content',''))>200}
            if len(sources)<2:return False
        paths=[f['path'] for f in project.files() if f['path'].startswith('presentation-preview/') and f['path'].endswith('.png')]
        if not paths:return False
        rendered={}
        for e in memory.get('test_evidence',[]):
            if e.get('role')=='testing' and e.get('cycle')==cycle and e.get('fingerprint')==current and e.get('kind')=='presentation_check' and e.get('exit_code')==0:
                rendered.update(e.get('presentation',{}).get('preview_sha256s',{}))
        if not all(rendered.get(p)==hashlib.sha256(project.path(p).read_bytes()).hexdigest() for p in paths):return False
    for role in ('testing','review') if review else ('testing',):
        viewed=set()
        for e in memory.get('test_evidence',[]):
            if e.get('role')==role and e.get('cycle')==cycle and e.get('fingerprint')==current and e.get('kind')=='visual_check' and e.get('exit_code')==0 and e.get('visual',{}).get('approved') is True:
                viewed.update(p for p in e['visual'].get('files',[]) if e['visual'].get('sha256s',{}).get(p)==hashlib.sha256(project.path(p).read_bytes()).hexdigest())
        if not set(paths)<=viewed:return False
    return True



def native(project,c,task,role,mode,prompt,paths=None,output=None):
    # A bounded switch among existing accounts is allowed only for provider capacity errors.
    alternatives=[r for r in ('backend','frontend','architect','mobile','research') if r!=role]
    if mode=='generate':
        alternatives.sort(key=lambda r:c.execute("SELECT count(*) FROM events WHERE role=? AND kind='model_started' AND detail='native-generate' AND created>=strftime('%s','now','start of day')",(r,)).fetchone()[0])
    candidates=[role]+(alternatives if mode=='generate' else [])
    for index,account_role in enumerate(candidates[:2]):
        try:
            result=_native_once(project,c,task,account_role,mode,prompt,paths,output)
            result['provider_account_role']=account_role
            return result
        except RuntimeError as error:
            policy_block=re.search(r'polic|safety|refus|declin|unauthori|permission denied|cannot (?:assist|comply)|can.t (?:help|assist)',str(error),re.I)
            if policy_block or index>=min(len(candidates),2)-1 or not re.search(r'429|RESOURCE_EXHAUSTED|quota|capacity exhausted',str(error),re.I):raise
            audit(c,role,'provider_capacity_retry',task['id'],'Existing account '+account_role+' unavailable; one alternate account attempt. '+str(error)[:500])


def select_native_image(export,answer):
    manifest=json.loads((export/'manifest.json').read_text()) if (export/'manifest.json').is_file() else {'images':[]}
    images=manifest.get('images',[])
    selected=[i for i in images if answer.get('file') in i.get('source_paths',[])]
    if not selected and len(images)==1:selected=images
    if len(selected)!=1:
        errors=answer.get('limitations',[])+manifest.get('errors',[])
        raise RuntimeError('Native image generation unavailable: '+('; '.join(str(x) for x in errors)[:1500] or ('Ambiguous generated image outputs' if images else 'Native session reported completion but exported no raster bytes')))
    name=selected[0]['path']
    if not re.fullmatch(r'[0-3]\.(jpg|png|webp)',name):raise ValueError('Invalid native export path')
    path=export/name
    if path.is_symlink() or not path.is_file():raise ValueError('Native export is missing or unsafe')
    return path


def validate_generated_change(metadata,references,export=None):
    if metadata.get('sha256') in references.values():
        errors=[]
        if export and (export/'manifest.json').is_file():errors=json.loads((export/'manifest.json').read_text()).get('errors',[])
        raise RuntimeError('Native generation returned unchanged reference bytes; no new image was produced. '+('; '.join(str(v) for v in errors)[:1000]))


def validate_creation(answer,manifest):
    if answer.get('created') is not True:
        reasons=answer.get('limitations',[])+manifest.get('errors',[])
        raise RuntimeError('Native provider did not create an image: '+('; '.join(str(v) for v in reasons)[:1500] or 'No explicit successful creation result'))
