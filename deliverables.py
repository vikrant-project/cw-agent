"""Requested formats are controller requirements, not optional model suggestions."""
import re,zipfile,posixpath,xml.etree.ElementTree as ET

def requested_format(prompt):
    if re.search(r'\b(powerpoint|pptx|ppt|slide deck)\b',prompt,re.I):
        count=re.search(r'\b(\d{1,2})[ -]*(?:slide|slides)\b',prompt,re.I)
        return {'kind':'presentation','extension':'.pptx','slides':int(count[1]) if count else None,'charts':bool(re.search(r'\b(chart|charts|graph|graphs)\b',prompt,re.I)),'required_topics':[term for term in ('UDP','TCP','detection','mitigation','impact','network behavior','attack flow') if re.search(r'\b'+re.escape(term)+r'\b',prompt,re.I)]}
    return None

def inspect_pptx(path,expected=None,charts=False,topics=None):
    ns={'p':'http://schemas.openxmlformats.org/presentationml/2006/main','a':'http://schemas.openxmlformats.org/drawingml/2006/main'}
    with zipfile.ZipFile(path) as z:
        if len(z.infolist())>5000 or sum(x.file_size for x in z.infolist())>200*1024**2:raise ValueError('Presentation package is too large')
        slides=sorted(n for n in z.namelist() if re.fullmatch(r'ppt/slides/slide\d+\.xml',n))
        if not slides or expected is not None and len(slides)!=expected:raise ValueError('Actual PowerPoint slide count does not match the request')
        if 'ppt/presentation.xml' not in z.namelist() or z.testzip():raise ValueError('Invalid PowerPoint package')
        for n in slides:
            tree=ET.fromstring(z.read(n))
            if not any((t.text or '').strip() for t in tree.findall('.//a:t',ns)):raise ValueError('Empty slide in presentation')
        visible=' '.join((t.text or '') for n in slides for t in ET.fromstring(z.read(n)).findall('.//a:t',ns))
        missing=[term for term in topics or [] if not re.search(r'\b'+re.escape(term)+r'\b',visible,re.I)]
        if missing:raise ValueError('Original requested topic coverage missing from slide content: '+', '.join(missing))
        chart_count=sum(bool(re.fullmatch(r'ppt/charts/chart\d+\.xml',n)) for n in z.namelist())
        if charts and not chart_count:raise ValueError('Requested charts are missing from PowerPoint')
        if '[Content_Types].xml' not in z.namelist():raise ValueError('PowerPoint content types are missing')
        for declaration in ET.fromstring(z.read('[Content_Types].xml')):
            part=declaration.attrib.get('PartName')
            if part and part.lstrip('/') not in z.namelist():raise ValueError('PowerPoint declares a missing package part')
        for n in z.namelist():
            if not n.endswith('.rels'):continue
            base=posixpath.dirname(posixpath.dirname(n)) if n!='_rels/.rels' else ''
            for relationship in ET.fromstring(z.read(n)):
                if relationship.attrib.get('TargetMode')=='External':continue
                target=relationship.attrib.get('Target','');resolved=target.lstrip('/') if target.startswith('/') else posixpath.normpath(posixpath.join(base,target))
                if resolved not in z.namelist():raise ValueError('PowerPoint has a broken internal relationship')
    return {'slides':len(slides),'editable_charts':chart_count,'format':'pptx'}

def collect(project,memory):
    requirement=memory.get('output_contract')
    if not requirement:
        import mimetypes
        from autonomy import artifact_check
        spec=memory.get('spec') or {}
        if not spec.get('deliverables'):return []
        checked=artifact_check(project,spec)
        return [{'path':item['path'],'size':item['bytes'],'mime':mimetypes.guess_type(item['path'])[0] or 'application/octet-stream','evidence':item} for item in checked['files']]
    files=[f for f in project.files() if f['path'].endswith(requirement['extension'])]
    if not files:raise ValueError('Requested PowerPoint file is missing. Markdown is not a substitute for .pptx')
    result=[]
    for f in files:
        evidence=inspect_pptx(project.path(f['path']),requirement.get('slides'),requirement.get('charts',False),requirement.get('required_topics'))
        result.append(dict(f,mime='application/vnd.openxmlformats-officedocument.presentationml.presentation',evidence=evidence))
    return result
