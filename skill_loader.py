"""Reviewed role instructions are distinct from untrusted temporary task playbooks."""
from pathlib import Path
import hashlib, shutil
from state import ROLES
CONTRACTS={
 'intake':'First classify the request. For greetings or ordinary conversation use respond immediately; do not build files. For a requested artifact state goal, exact deliverable paths, measurable acceptance criteria and concrete responsibilities in spec. Assign only necessary specialists; the slot name is not a restriction on task expertise. Documents/research need actual-file integrity checks and independent content review, not invented browser tests. Write TASK.md with explicit acceptance criteria, platform, assumptions and a non-destructive implementation plan. Create task-specific skill playbooks with checks and debugging methods. Ask for missing essential credentials by documenting an integration requirement; never invent them.',
 'research':'Research applicable frameworks and design tradeoffs. Use research tools for primary documentation when needed. Write RESEARCH.md with URLs and concrete implications. Match available offline tools and avoid unnecessary dependencies.',
 'architect':'Define a coherent project structure, data flow, interfaces, persistence and tests. Write ARCHITECTURE.md. Prefer the simplest complete implementation. Coordinate previous notes and acceptance criteria.',
 'backend':'Create the assigned deliverable using the tools that match this task. This account is an implementation slot, not a requirement to write an application. Use image_generate for requested generated images, presentation for PowerPoint, and coding tools for actual software. Preserve the original format, quality and coverage. Consult peer evidence and never substitute placeholders.',
 'frontend':'Create the assigned visual or interface deliverable. This account is a task-specific design slot, not a requirement to build forms. For generated artwork use image_generate; for slides use presentation; for actual websites include usable responsive interfaces. Match the original brief and peer contracts.',
 'mobile':'Implement mobile components when requested; otherwise review responsive layouts or portability. Clearly separate source delivery from an APK/IPA build. Do not claim device verification without actual tooling and results.',
 'testing':'Independently derive tests from TASK.md. Execute commands and fresh-session browser workflows. Check empty/invalid forms, signup/login when present, core journeys and a mobile viewport. Save TEST_PLAN.md. Passing status requires controller-recorded evidence and an explicit verify action mapping EVERY acceptance criterion to current-cycle evidence_ids, not prose. For reports check real files and independently review content with artifact_check; for code execute assertions.',
 'debugging':'Use actual compiler, command, browser and peer-review failures. Find causes, implement repairs and rerun the affected tests. Keep changes consistent with acceptance criteria. Document unresolved problems instead of hiding them.',
 'review':'Independently compare all acceptance criteria with files and actual test evidence. Read-only tools: read and research. Inspect authentication, data isolation, error handling, UI behavior and integration gaps. Return review with approved true and goal_achieved true only after evaluating EVERY criterion in criteria [{id,passed,reason}] against actual files and fresh tester evidence. Otherwise return approved false with concrete issues. Never weaken the request. Never return done instead of a review.',
 'release':'Prepare README.md with setup, usage, limitations, tests and integration requirements. Check the final tree and package readiness. Do not claim a public deployment or binary build that did not occur.'
}
def load(root,role):
    if role not in ROLES:raise ValueError('Unknown role')
    names=('coding-common','coding-'+role);result=[]
    for name in names:
        p=Path(root)/'skills'/name/'SKILL.md';s=p.read_text(encoding='utf-8')
        if p.is_symlink() or len(s)>16000 or 'name: '+name+'\n' not in s:raise ValueError('Invalid reviewed skill')
        result.append({'name':name,'text':s,'path':str(p),'sha256':hashlib.sha256(s.encode()).hexdigest()})
    return result
def prepare_workspace(root,role,workspace):
    base=Path(workspace);base.mkdir(parents=True,exist_ok=True)
    for s in load(root,role):
        dest=base/'.agents'/'skills'/s['name'];dest.mkdir(parents=True,exist_ok=True);shutil.copyfile(s['path'],dest/'SKILL.md')
    for p in [base,*base.rglob('*')]:p.chmod(0o755 if p.is_dir() else 0o644)
    return base

def native_skill(root):
    source=Path(root)/'skills'/'native-media'/'SKILL.md'
    if source.is_symlink():raise ValueError('Invalid native media skill')
    text=source.read_text(encoding='utf-8')
    if len(text)>16000 or 'name: native-media\n' not in text:raise ValueError('Invalid native media skill')
    return source,text

def native_session_instruction(root,mode,request):
    if mode not in ('generate','inspect') or not isinstance(request,str):raise ValueError('Invalid native session request')
    _,text=native_skill(root)
    return 'TRUSTED NATIVE MEDIA INSTRUCTIONS (apply in this session):\n'+text+'\nSESSION REQUEST:\n'+request

def prepare_native_workspace(root,mode,workspace,uid,gid):
    """Native sessions get purpose-specific instructions, not external controller actions."""
    import os
    if mode not in ('generate','inspect'):raise ValueError('Unknown native media mode')
    source,_=native_skill(root)
    base=Path(workspace)
    if any(path.is_symlink() for path in [base,*base.rglob('*')]):raise ValueError('Symlinks are not permitted in native media staging')
    destination=base/'.agents'/'skills'/'native-media';destination.mkdir(parents=True,exist_ok=True)
    shutil.copyfile(source,destination/'SKILL.md')
    for path in [base,*base.rglob('*')]:
        if path.is_symlink():raise ValueError('Symlinks are not permitted in native media staging')
        os.chown(path,uid,gid);path.chmod(0o700 if path.is_dir() else 0o400)
    return base
