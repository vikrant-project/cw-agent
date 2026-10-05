// Trusted data renderer. Content stays in the isolated task; no network or executable templates.
const fs=require('fs'),path=require('path'),pptxgen=require('pptxgenjs'),JSZip=require('jszip');
const data=JSON.parse(fs.readFileSync(process.argv[2],'utf8'));
if(!Array.isArray(data.slides)||data.slides.length<1||data.slides.length>40)throw Error('Use 1–40 slides');
const ppt=new pptxgen();ppt.layout='LAYOUT_WIDE';ppt.author='CW Agent';ppt.subject=data.topic||'Presentation';ppt.title=data.topic||'Presentation';ppt.lang='en-US';ppt.theme={headFontFace:'Liberation Sans',bodyFontFace:'Liberation Sans',lang:'en-US'};
const C={bg:'F5F6F8',ink:'13243B',muted:'52657B',blue:'2555D9',red:'C74949',teal:'008580',line:'C8D3E0'};
function text(s,t,x,y,w,h,size=20,color=C.ink,bold=false){s.addText(String(t||''),{x,y,w,h,fontFace:'Liberation Sans',fontSize:size,color,bold,margin:0,breakLine:false,vertAlign:'mid',fit:'shrink'});}
function networkIcon(s,kind,x,y,w=.7,h=.5){
 const box=(type,a,b,c,d,fill='FFFFFF')=>s.addShape(type,{x:a,y:b,w:c,h:d,fill:{color:fill},line:{color:C.blue,width:1.2}});
 const ln=(a,b,c,d)=>s.addShape(ppt.ShapeType.line,{x:a,y:b,w:c,h:d,line:{color:C.blue,width:1.2}});
 if(kind==='server'){for(let i=0;i<3;i++){box(ppt.ShapeType.roundRect,x,y+i*.16,w,.13);box(ppt.ShapeType.ellipse,x+.05,y+i*.16+.035,.04,.04,C.blue);ln(x+.18,y+i*.16+.065,w-.25,0);}}
 else if(kind==='database')box(ppt.ShapeType.can,x,y,w,h,'E6ECFA');
 else if(kind==='cloud')box(ppt.ShapeType.cloud,x-.07,y-.05,w+.14,h+.12,'E6ECFA');
 else if(kind==='firewall'){for(let row=0;row<3;row++){for(let col=0;col<3;col++){const width=w/3;box(ppt.ShapeType.rect,x+col*width,y+row*h/3,width,h/3,'FFE7D0');}}}
 else if(kind==='router'){box(ppt.ShapeType.roundRect,x,y+.13,w,.27,'E6ECFA');for(let j=0;j<4;j++)box(ppt.ShapeType.rect,x+.07+j*.14,y+.21,.07,.06,C.blue);ln(x+.10,y+.08,.18,0);ln(x+.42,y+.08,.18,0);}
 else if(kind==='client'){box(ppt.ShapeType.rect,x,y,w,h*.7,'E6ECFA');ln(x+w/2,y+h*.7,0,h*.22);ln(x+w*.25,y+h*.92,w*.5,0);}
 else if(kind==='bot'){box(ppt.ShapeType.roundRect,x+.06,y+.06,w-.12,h-.12,'E6ECFA');box(ppt.ShapeType.ellipse,x+.18,y+.17,.07,.07,C.blue);box(ppt.ShapeType.ellipse,x+w-.25,y+.17,.07,.07,C.blue);ln(x+.22,y+.33,w-.44,0);ln(x+w/2,y,0,.06);}
 else throw Error('Unsupported network icon');
}
function node(s,n){
 if(!n.id||!Number.isFinite(n.x)||!Number.isFinite(n.y)||n.x<.5||n.x>11.5||n.y<1.5||n.y>5.9)throw Error('Diagram node outside content area');
 const w=n.w||2,h=n.h||(n.icon?1.35:.7);if(w<.5||h<.4||n.x+w>12.8||n.y+h>6.2)throw Error('Diagram exceeds slide content bounds');
 if(n.icon&&(w<1.8||h<1.15))throw Error('Network-icon nodes need width >=1.8 and height >=1.15');
 s.addShape(n.icon?ppt.ShapeType.roundRect:ppt.ShapeType.rect,{x:n.x,y:n.y,w,h,fill:{color:n.color||(n.icon?'FFFFFF':'E6ECFA')},line:{color:C.line,width:1}});
 if(n.icon)networkIcon(s,n.icon,n.x+w/2-.35,n.y+.13);
 const longest=Math.max(1,...String(n.label||'').split(/\s+/).map(v=>v.length));const font=Math.min(n.fontSize||16,(w-.24)*72/(longest*.62));if(font<14)throw Error('Diagram node too narrow for a readable label; widen it or shorten label');
 text(s,n.label,n.x+.12,n.y+(n.icon?.72:.08),w-.24,h-(n.icon?.8:.16),font,C.ink,true);
}
function edgeGeometry(a,b,e,edges){
 let ax=a.x+(a.w||2)/2,ay=a.y+(a.h||(a.icon?1.35:.7))/2,bx=b.x+(b.w||2)/2,by=b.y+(b.h||(b.icon?1.35:.7))/2;
 if(Math.abs(ax-bx)>Math.abs(ay-by)){if(ax<bx){ax=a.x+(a.w||2);bx=b.x;}else{ax=a.x;bx=b.x+(b.w||2);}}else{if(ay<by){ay=a.y+(a.h||(a.icon?1.35:.7));by=b.y;}else{ay=a.y;by=b.y+(b.h||(b.icon?1.35:.7));}}
 if(edges.some(other=>other!==e&&other.from===e.to&&other.to===e.from)&&Math.abs(ay-by)<.05){const shift=ax<bx?-.23:.23;ay+=shift;by+=shift;}
 return {ax,ay,bx,by};
}
function coversConnector(box,routes){
 return routes.some(({ax,ay,bx,by})=>{
  for(let i=0;i<=64;i++){const t=i/64,x=ax+t*(bx-ax),y=ay+t*(by-ay);if(x>=box.x-.09&&x<=box.x+box.w+.09&&y>=box.y-.09&&y<=box.y+box.h+.09)return true;}
  return false;
 });
}

for(const [i,d] of data.slides.entries()){
 if(typeof d.title!=='string'||d.title.length>100)throw Error('Each slide needs a concise title');
 const s=ppt.addSlide();const full=d.layout==='visual';if(full&&Array.isArray(d.body)&&d.body.length>1)throw Error('Visual layout supports at most one lead sentence; move detail into notes');s.background={color:C.bg};s.addShape(ppt.ShapeType.rect,{x:.6,y:.22,w:.7,h:.05,line:{color:C.blue,transparency:100},fill:{color:C.blue}});text(s,String(i+1).padStart(2,'0')+' / '+data.slides.length,.6,6.95,2,.2,10,C.muted);text(s,d.title,.6,.42,12.1,.88,i===0?42:32,C.ink,true);
 if(d.subtitle)text(s,d.subtitle,.62,1.22,12.0,.48,16,C.muted);
 const body=Array.isArray(d.body)?d.body:[];if(body.length>6||body.some(x=>typeof x!=='string'||x.length>220))throw Error('Keep slide text concise; put detail in notes');
 const hasVisual=!!(d.diagram||d.chart||d.table);
 body.forEach((line,j)=>text(s,line,.65,full?1.55:1.94+j*.72,full?11.8:(hasVisual?4.0:11.6),.60,full?18:20));
 if(d.diagram){
  const nodes=d.diagram.nodes||[],edges=d.diagram.edges||[];if(nodes.length>12||edges.length>16)throw Error('Diagram too dense');
  const map=new Map(nodes.map(n=>[n.id,n]));
  const routes=edges.map(e=>{const a=map.get(e.from),b=map.get(e.to);if(!a||!b)throw Error('Unknown diagram node');return edgeGeometry(a,b,e,edges);});
  const seenLabels=[];for(const [edgeIndex,e] of edges.entries()){const a=map.get(e.from),b=map.get(e.to);if(!a||!b)throw Error('Unknown diagram node');
   const {ax,ay,bx,by}=routes[edgeIndex];
   s.addShape(ppt.ShapeType.line,{x:Math.min(ax,bx),y:Math.min(ay,by),w:Math.abs(bx-ax)||.001,h:Math.abs(by-ay)||.001,flipH:ax>bx,flipV:ay>by,line:{color:e.color||C.blue,width:2,beginArrowType:'none',endArrowType:'triangle',dashType:e.dashed?'dash':'solid'}});
   if(e.label){const w=Math.min(2.2,Math.max(.85,String(e.label).length*.095+.25)),h=.40;const overlap=(a,b)=>a.x<b.x+b.w+.04&&a.x+a.w+.04>b.x&&a.y<b.y+b.h+.04&&a.y+a.h+.04>b.y;const midX=(ax+bx)/2,midY=(ay+by)/2;const candidates=[];for(let y=1.5;y<=5.85;y+=.22)for(let x=full?.65:5.1;x<=10.9;x+=.2)candidates.push({x,y,w,h});candidates.sort((a,b)=>(Math.hypot(a.x+w/2-midX,a.y+h/2-midY)-Math.hypot(b.x+w/2-midX,b.y+h/2-midY)));const box=candidates.find(box=>Math.hypot(box.x+w/2-midX,box.y+h/2-midY)<=1.0&&!coversConnector(box,routes)&&!nodes.some(n=>overlap(box,{x:n.x,y:n.y,w:n.w||2,h:n.h||(n.icon?1.35:.7)}))&&!seenLabels.some(n=>overlap(box,n)));if(!box)throw Error('No nearby readable space for diagram edge label; simplify labels or reposition nodes');seenLabels.push({...box,label:e.label,color:e.color||C.blue});}

  }
  seenLabels.forEach(b=>{s.addShape(ppt.ShapeType.rect,{x:b.x-.04,y:b.y-.03,w:b.w+.08,h:b.h+.06,fill:{color:C.bg},line:{color:C.bg,transparency:100}});text(s,b.label,b.x,b.y,b.w,b.h,14,b.color,true);});
  nodes.forEach(n=>node(s,n));
 }
 if(d.chart){const ch=d.chart;if(!['line','bar'].includes(ch.type)||!Array.isArray(ch.categories)||ch.categories.length>15||!Array.isArray(ch.series)||ch.series.length>4)throw Error('Invalid chart');
  s.addChart(ch.type==='line'?ppt.ChartType.line:ppt.ChartType.bar,ch.series.map((v,j)=>({name:v.name,labels:ch.categories,values:v.values})),{x:full?.65:5.1,y:full?2.15:1.95,w:full?12.0:7.4,h:full?4.0:4.2,fontFace:'Liberation Sans',catAxisLabelFontFace:'Liberation Sans',valAxisLabelFontFace:'Liberation Sans',legendFontFace:'Liberation Sans',showLegend:true,legendPos:'b',showTitle:false,catAxisLabelFontSize:14,valAxisLabelFontSize:14,chartColors:ch.series.length===1?[C.blue]:[C.blue,C.red,C.teal],showValue:false,showCatName:false,showBorder:false,showCatName:false,valAxisTitle:ch.unit||'',showValAxisTitle:!!ch.unit,lineSize:3,showMarker:false,showLine:true,showShadow:false,catAxisLineColor:C.line,valAxisLineColor:C.line,showCatName:false});
  if(ch.disclosure)text(s,ch.disclosure,full?.65:5.15,6.25,full?11.8:7.2,.35,11,C.muted);
 }
 if(d.table){if(!Array.isArray(d.table)||d.table.length>7)throw Error('Invalid table');s.addTable(d.table,{x:!full&&hasVisual&&body.length?5.0:.65,y:2.15,w:!full&&hasVisual&&body.length?7.6:12.0,fontFace:'Liberation Sans',fontSize:18,color:C.ink,border:{type:'solid',pt:1,color:C.line},fill:'FFFFFF',margin:.12,rowH:.66,bold:false});}
 if(d.takeaway)text(s,d.takeaway,.65,6.36,11.9,.45,18,C.blue,true);
 const sources=Array.isArray(d.sources)?d.sources:[];s.addNotes([String(d.notes||''),'Sources:',...sources].join('\n'));
}
const file=data.filename||'presentation.pptx';if(!/^[A-Za-z0-9_-]+\.pptx$/.test(file))throw Error('Invalid presentation filename');
ppt.writeFile({fileName:file}).then(async()=>{
 // PptxGenJS 4.0.1 declares unused per-slide masters. Remove only orphan content-type declarations.
 const zip=await JSZip.loadAsync(fs.readFileSync(file));const contentTypes=await zip.file('[Content_Types].xml').async('string');
 zip.file('[Content_Types].xml',contentTypes.replace(/<Override\b[^>]*\/>/g,tag=>{const name=tag.match(/PartName="([^"]+)"/);return name&&!zip.file(name[1].replace(/^\//,''))?'':tag;}));
 fs.writeFileSync(file,await zip.generateAsync({type:'nodebuffer',compression:'DEFLATE'}));
 console.log(JSON.stringify({created:file,slides:data.slides.length}));
}).catch(e=>{console.error(e.message);process.exit(1);});
