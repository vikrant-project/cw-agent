"""Typed CLI response envelope. Parameters must not be hidden in an action string."""
S={'type':'string'}
B={'type':'boolean'}
N={'type':'number'}
def array(item):return {'type':'array','items':item}
def obj(properties,required=()):return {'type':'object','properties':properties,'required':list(required),'additionalProperties':False}
NODE=obj({'icon':{'type':'string','enum':['server','client','router','firewall','cloud','database','bot']},'id':S,'label':S,'x':N,'y':N,'w':N,'h':N,'color':S,'fontSize':N},('id','label','x','y'))
EDGE=obj({'from':S,'to':S,'label':S,'dashed':B,'color':S},('from','to'))
CHART=obj({'type':{'type':'string','enum':['line','bar']},'categories':array(S),'series':array(obj({'name':S,'values':array(N)},('name','values'))),'unit':S,'disclosure':S},('type','categories','series'))
SLIDE=obj({'layout':{'type':'string','enum':['split','visual']},'title':S,'subtitle':S,'body':array(S),'notes':S,'sources':array(S),'takeaway':S,'diagram':obj({'nodes':array(NODE),'edges':array(EDGE)},('nodes','edges')),'chart':CHART,'table':array(array(S))},('title','body'))
STEP=obj({'type':S,'selector':S,'value':S,'path':S,'url':S,'valid':B},('type',))
CRITERION=obj({'id':S,'passed':B,'reason':S,'evidence_ids':array(S)},('id','passed','reason'))
ACTION_SCHEMA=obj({
 'action':{'type':'string','enum':['spec','respond','write','read','run','browser_test','presentation','presentation_check','artifact_check','image_generate','visual_check','verify','research','skill','review','done','decline','blocked']},
 'type':{'type':'string','enum':['web','mobile','python','other','document','research','presentation','image']},
 'goal':S,'deliverables':array(obj({'path':S,'purpose':S},('path','purpose'))),
 'roles':array({'type':'string','enum':['research','architect','backend','frontend','mobile']}),'assignments':obj({name:S for name in ('research','architect','backend','frontend','mobile')}),'acceptance':array(S),
 'text':S,'files':array(obj({'path':S,'content':S},('path','content'))),'path':S,
 'argv':array(S),'server':array(S),'steps':array(STEP),
 'deck':obj({'topic':S,'filename':S,'slides':array(SLIDE)},('topic','filename','slides')),
 'prompt':S,'reference_paths':array(S),'paths':array(S),'checks':S,'criteria':array(CRITERION),
 'url':S,'focus':S,'name':S,'content':S,'approved':B,'goal_achieved':B,'issues':array(S),'summary':S,'reason':S
},('action',))

# A single required serialized payload avoids optional-parameter loss in the
# native finish tool. Full action validation remains in the external controller.
WIRE_SCHEMA=obj({'payload':{'type':'string','description':'JSON-serialized complete external controller action, including every required parameter. Do not omit spec, file, deck or evidence fields.'}},('payload',))

WIRE_OBJECT_SCHEMA=obj({'payload':dict(ACTION_SCHEMA,description='The complete external controller action OBJECT with all parameters. Preserve nested spec, files, deck and evidence data; do not serialize it to a string.')},('payload',))


def phase_schema(role,context):
 import copy
 schema=copy.deepcopy(WIRE_OBJECT_SCHEMA);guidance='';kind=(context.get('spec')or{}).get('type')
 if role=='intake':
  if context.get('spec') and not context.get('temporary_skills'):
   allowed=['skill','blocked','decline'];guidance='The task spec is already accepted. Next create one concrete task playbook using skill with name and content. Do not repeat spec or finish before creating the playbook.'
  elif context.get('spec'):
   allowed=['done','write','read','blocked','decline'];guidance='Spec and playbook are established. Hand off with done now; optionally write TASK.md first if needed. Do not repeat spec or create extra skills.'
  else:
   allowed=['spec','respond','blocked','decline'];guidance='Classify once: respond directly for ordinary conversation, or create the complete spec for requested files/tools.'
 elif role=='review':allowed=['visual_check','research','read','review','blocked','decline'] if kind in ('image','presentation') else ['read','research','review','blocked','decline']
 elif role=='testing':
  if kind=='image':allowed=['artifact_check','visual_check','verify','read','write','done','blocked','decline']
  elif kind=='presentation':allowed=['presentation_check','visual_check','artifact_check','verify','research','read','write','done','blocked','decline']
  else:allowed=['run','browser_test','artifact_check','verify','research','read','write','done','blocked','decline']
 elif role=='release':allowed=['write','read','run','done','blocked','decline']
 else:
  if kind=='image':allowed=['image_generate','read','write','research','done','blocked','decline']
  elif kind=='presentation':allowed=['presentation','read','write','research','done','blocked','decline']
  else:allowed=['write','read','run','browser_test','research','done','blocked','decline']
  if role=='debugging' and kind in ('image','presentation'):allowed.append('visual_check')
  if role=='architect':allowed.append('skill')
 # Media verification has observable stages; advance without repeated renders
 # or prose approvals. Failed visible checks still count as inspected coverage,
 # and their failures must be recorded by verify/review, never hidden.
 if role in ('testing','review') and kind in ('image','presentation'):
  cycle=context.get('cycle',0);proof=[e for e in context.get('test_evidence',[]) if e.get('role')==role and e.get('cycle')==cycle]
  checker='presentation_check' if kind=='presentation' else 'artifact_check'
  if kind=='image':expected=[d['path'] for d in context['spec'].get('deliverables',[]) if d.get('path','').lower().endswith(('.jpg','.jpeg','.png','.webp'))]
  else:expected=[f['path'] for f in context.get('tree',[]) if f.get('path','').startswith('presentation-preview/') and f.get('path','').endswith('.png')]
  viewed={name for e in proof if e.get('kind')=='visual_check' for name in e.get('visual',{}).get('files',[])}
  missing=[p for p in expected if p not in viewed]
  if role=='testing' and context.get('verification') and context['verification'].get('cycle')==cycle:
   allowed=['done','read','blocked','decline'];guidance='Current-cycle verification is recorded. Return done and hand all passing or failing criteria to independent review. Do not repeat checks or change source after verification.'
  elif role=='testing' and not any(e.get('kind')==checker for e in proof):
   allowed=[checker,'read','write','research','blocked','decline'];guidance='Execute one fresh '+checker+' on the final actual artifact in this cycle. Then inspect the actual pixels and verify every criterion.'
  elif missing or (kind=='presentation' and not expected):
   allowed=['visual_check','read','research','blocked','decline'];guidance='Inspect the remaining actual output images in batches of at most four. Current missing paths: '+str(missing)+'. Report all real visible issues, then evaluate every criterion; do not rerender or repeat inspected batches.'
  else:
   allowed=(['verify','read','research','write','blocked','decline'] if role=='testing' else ['review','read','research','blocked','decline']);guidance='All required current images were inspected. Now return '+('verify mapping every criterion to current evidence_ids, including observed failures; then done' if role=='testing' else 'an explicit independent review verdict evaluating the original request, actual files and fresh evidence')+'. Do not substitute another inspection loop for a verdict.'
 fields={'spec':['type','goal','deliverables','roles','assignments','acceptance'],'respond':['text'],'write':['files'],'read':['path'],'run':['argv'],'browser_test':['server','steps'],'presentation':['deck'],'presentation_check':['path'],'artifact_check':[],'image_generate':['path','prompt','reference_paths'],'visual_check':['paths','checks'],'verify':['criteria'],'research':['url','focus'],'skill':['name','content'],'review':['approved','goal_achieved','criteria','issues'],'done':['summary'],'decline':['reason'],'blocked':['reason']}
 selected={'action'}
 for action in allowed:selected.update(fields[action])
 payload=schema['properties']['payload'];payload['properties']={k:v for k,v in payload['properties'].items() if k in selected};payload['properties']['action']['enum']=allowed
 return schema,guidance
