import makeWASocket,{DisconnectReason,initAuthCreds,BufferJSON,proto,jidNormalizedUser} from '@whiskeysockets/baileys';
import QRCode from 'qrcode';import pino from 'pino';import fs from 'node:fs';import path from 'node:path';import crypto from 'node:crypto';
const root=process.env.CODING_ROOT||'/opt/coding-workshop',secrets=path.join(root,'bridge-private'),base=path.join(secrets,'sessions');fs.mkdirSync(base,{recursive:true,mode:0o700});
const token=fs.readFileSync(path.join(secrets,'bridge.key'),'utf8').trim(),master=Buffer.from(fs.readFileSync(path.join(secrets,'wa-encryption.key'),'utf8').trim(),'hex');
fs.writeFileSync(path.join(secrets,'capabilities.json'),JSON.stringify({direct_artifacts:true}),{mode:0o600});
const BOT_MARK='CW Agent : - ',LEGACY_BOT_MARK='\u2063CW\u2063';
const sessions=new Map(),connecting=new Set(),logger=pino({level:'silent'});
async function api(route,body){const r=await fetch('http://127.0.0.1:9871'+route,{method:body?'POST':'GET',headers:{Authorization:'Bearer '+token,...(body?{'Content-Type':'application/json'}:{})},body:body?JSON.stringify(body):undefined,signal:AbortSignal.timeout(10000)});const v=await r.json();if(!r.ok)throw Error(v.error||'Bridge rejected request');return v;}
function status(user_id,status,qr){return api('/status',{user_id,status,qr});}
function auth(user){
 if(!/^[a-f0-9]{32}$/.test(user))throw Error('Invalid user');const file=path.join(base,user+'.enc');let store;
 if(fs.existsSync(file)){const bytes=fs.readFileSync(file);const dec=crypto.createDecipheriv('aes-256-gcm',master,bytes.subarray(0,12));dec.setAuthTag(bytes.subarray(12,28));store=JSON.parse(Buffer.concat([dec.update(bytes.subarray(28)),dec.final()]).toString(),BufferJSON.reviver);}else store={creds:initAuthCreds(),keys:{}};
 const save=()=>{const iv=crypto.randomBytes(12),enc=crypto.createCipheriv('aes-256-gcm',master,iv);const bytes=Buffer.concat([enc.update(JSON.stringify(store,BufferJSON.replacer)),enc.final()]);fs.writeFileSync(file+'.tmp',Buffer.concat([iv,enc.getAuthTag(),bytes]),{mode:0o600});fs.renameSync(file+'.tmp',file);};
 return {state:{creds:store.creds,keys:{get:async(type,ids)=>{const r={};for(const id of ids){let v=store.keys[type]?.[id];if(type==='app-state-sync-key'&&v)v=proto.Message.AppStateSyncKeyData.fromObject(v);if(v)r[id]=v;}return r;},set:async data=>{for(const [type,entries]of Object.entries(data)){store.keys[type]??={};for(const [id,v]of Object.entries(entries)){if(v)store.keys[type][id]=v;else delete store.keys[type][id];}}save();}}},save};
}
async function start(user){
 if(sessions.has(user)||connecting.has(user))return;connecting.add(user);
 try{
  await status(user,'connecting');const a=auth(user);const sock=makeWASocket({auth:a.state,logger,markOnlineOnConnect:false,syncFullHistory:false});
  const entry={sock,connected:false,restarts:0};sessions.set(user,entry);
  sock.ev.on('creds.update',a.save);
  sock.ev.on('connection.update',async update=>{try{
   if(sessions.get(user)!==entry)return;
   if(update.qr)await status(user,'qr',await QRCode.toDataURL(update.qr));
   if(update.connection==='open'){entry.connected=true;await status(user,'connected');}
   if(update.connection==='close'){
    sessions.delete(user);const loggedOut=update.lastDisconnect?.error?.output?.statusCode===DisconnectReason.loggedOut;
    await status(user,loggedOut?'logged_out':'reconnecting');
    // Reconnect is bounded per five-minute interval by the polling scheduler.
   }
  }catch{console.error('WhatsApp connection state could not be persisted');}});
  sock.ev.on('messages.upsert',async event=>{
   if(event.type!=='notify'||!entry.connected)return;
   const own=new Set([sock.user?.id,sock.user?.lid].filter(Boolean).map(jidNormalizedUser));
   for(const m of event.messages){
    if(!m.key.fromMe||!own.has(jidNormalizedUser(m.key.remoteJid||'')))continue;
    const text=m.message?.conversation||m.message?.extendedTextMessage?.text||'';
    if(!text.trim()||text.startsWith(BOT_MARK)||text.startsWith(LEGACY_BOT_MARK))continue;
    try{const queued=await api('/submit',{user_id:user,prompt:text.startsWith('/build ')?'Build request: '+text.slice(7):text.startsWith('/chat ')?text.slice(6):text,message_id:m.key.id});await sock.sendMessage(m.key.remoteJid,{text:BOT_MARK+'Request queued: '+queued.task_id+'. View progress in your workshop portal.'});}
    catch(e){await sock.sendMessage(m.key.remoteJid,{text:BOT_MARK+'Request could not be queued: '+e.message.slice(0,200)}).catch(()=>{});}
   }
  });
 }catch{await status(user,'error').catch(()=>{});console.error('WhatsApp session initialization failed');}finally{connecting.delete(user);}
}
const retries=new Map();let polling=false;
async function poll(){if(polling)return;polling=true;try{
 const rows=await api('/sessions'),wanted=new Map(rows.map(r=>[r.user_id,r.status]));
 for(const [user,entry]of sessions){if(wanted.get(user)==='disconnected'||!wanted.has(user)){sessions.delete(user);await entry.sock.logout().catch(()=>{});fs.rmSync(path.join(base,user+'.enc'),{force:true});}else if(wanted.get(user)==='requested'&&!entry.connected){sessions.delete(user);entry.sock.end(new Error('Relink requested'));}}
 for(const row of rows){if(['requested','connecting','connected','reconnecting','qr'].includes(row.status)&&!sessions.has(row.user_id)){
  if(row.status==='requested'){retries.delete(row.user_id);fs.rmSync(path.join(base,row.user_id+'.enc'),{force:true});}
  const now=Date.now(),old=retries.get(row.user_id)||{start:now,count:0};if(now-old.start>300000){old.start=now;old.count=0;}
  if(old.count<3){old.count++;retries.set(row.user_id,old);await start(row.user_id);}else await status(row.user_id,'error');
 }}
 for(const task of await api('/notifications')){
  const entry=sessions.get(task.user_id);if(!entry?.connected)continue;
  await api('/notification',{task_id:task.id,status:'sending'});
  try{
   const jid=jidNormalizedUser(entry.sock.user.id);
   await entry.sock.sendMessage(jid,{text:BOT_MARK+(task.status==='answered'?task.summary:'Task '+task.id+': '+task.status+'\n'+(task.summary||task.error||'View your portal for details'))});
   if(task.status==='ready')for(const output of task.deliverables||[]){if(output.path.includes('..')||path.isAbsolute(output.path))throw Error('Invalid output path');await entry.sock.sendMessage(jid,{document:fs.readFileSync(path.join(root,'downloads',task.id,output.path)),mimetype:output.mime,fileName:path.basename(output.path)});}
   if(task.status==='ready')await entry.sock.sendMessage(jid,{document:fs.readFileSync(path.join(root,'downloads',task.id+'.zip')),mimetype:'application/zip',fileName:'workshop-'+task.id+'.zip'});
   await api('/notification',{task_id:task.id,status:'sent'});
  }catch{await api('/notification',{task_id:task.id,status:'uncertain',error:'Delivery result uncertain; not automatically repeated'}).catch(()=>{});}
 }
}catch{console.error('WhatsApp bridge temporarily unavailable');}finally{polling=false;}}
setInterval(poll,5000);await poll();
