const fs=require('fs'),path=require('path'),cp=require('child_process'),JSZip=require('jszip');
const file=process.argv[2];if(!file||path.isAbsolute(file)||file.split('/').includes('..')||!file.endsWith('.pptx'))throw Error('Invalid presentation path');
async function main(){
const zip=await JSZip.loadAsync(fs.readFileSync(file));const types=await zip.file('[Content_Types].xml').async('string');
for(const tag of types.match(/<Override\b[^>]*\/>/g)||[]){const part=tag.match(/PartName="([^"]+)"/);if(part&&!zip.file(part[1].replace(/^\//,'')))throw Error('Missing package declaration target. Regenerate with the updated presentation tool.');}
fs.mkdirSync('presentation-preview',{recursive:true});
const run=(cmd,args)=>{const r=cp.spawnSync(cmd,args,{encoding:'utf8',timeout:70000});if(r.status!==0)throw Error(cmd+' failed: '+(r.stderr||r.error||'').toString().slice(-500));return r.stdout;};
run('libreoffice',['-env:UserInstallation=file:///tmp/cw-office-'+process.pid,'--headless','--convert-to','pdf','--outdir','presentation-preview',file]);
const pdf='presentation-preview/'+path.basename(file,'.pptx')+'.pdf';if(!fs.existsSync(pdf))throw Error('Presentation did not render');
const info=run('pdfinfo',[pdf]),match=info.match(/^Pages:\s+(\d+)/m);if(!match)throw Error('Rendered PDF has no page count');
run('pdftoppm',['-scale-to','1280','-png',pdf,'presentation-preview/slide']);
const pages=fs.readdirSync('presentation-preview').filter(x=>/^slide-\d+\.png$/.test(x));if(pages.length!==Number(match[1]))throw Error('Not every slide rendered');
console.log(JSON.stringify({passed:true,pages:Number(match[1]),preview_files:pages.map(x=>'presentation-preview/'+x),pdf}));
}
main().catch(e=>{console.error(e.message);process.exit(1);});
