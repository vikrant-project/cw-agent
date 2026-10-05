<?php
declare(strict_types=1);
$root=getenv('CODING_ROOT')?:'/opt/coding-workshop';
$sessions=$root.'/portal-data/sessions';if(!is_dir($sessions))mkdir($sessions,0700);session_save_path($sessions);
$secure=($_SERVER['HTTPS']??'')==='on'||($_SERVER['HTTP_X_FORWARDED_PROTO']??'')==='https';
ini_set('session.use_strict_mode','1');session_set_cookie_params(['httponly'=>true,'secure'=>$secure,'samesite'=>'Strict']);session_start();
header('X-Content-Type-Options: nosniff');header('Referrer-Policy: same-origin');header('Cache-Control: no-store');
header("Content-Security-Policy: default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; frame-ancestors 'none'; base-uri 'none'; form-action 'self'");
$db=new PDO('sqlite:'.$root.'/portal-data/portal.sqlite3');$db->setAttribute(PDO::ATTR_ERRMODE,PDO::ERRMODE_EXCEPTION);$db->exec('PRAGMA busy_timeout=30000');$db->exec('PRAGMA foreign_keys=ON');
function query(string $sql,array $args=[]):PDOStatement{global $db;$q=$db->prepare($sql);$q->execute($args);return $q;}
function respond(array $data,int $status=200):never{http_response_code($status);header('Content-Type: application/json');echo json_encode($data,JSON_INVALID_UTF8_SUBSTITUTE);exit;}
function limit(string $category,int $max,int $seconds):void{
 global $db;$ip=$_SERVER['REMOTE_ADDR']??'local';
 if(in_array($ip,['127.0.0.1','::1'],true)&&filter_var($_SERVER['HTTP_X_REAL_IP']??'',FILTER_VALIDATE_IP))$ip=$_SERVER['HTTP_X_REAL_IP'];
 $key=hash('sha256',$category.$ip);$now=time();$db->exec('BEGIN IMMEDIATE');
 try{$r=query('SELECT * FROM rate_limits WHERE key=?',[$key])->fetch(PDO::FETCH_ASSOC);$count=(!$r||(int)$r['expires']<$now)?1:(int)$r['count']+1;$until=(!$r||(int)$r['expires']<$now)?$now+$seconds:(int)$r['expires'];query('INSERT INTO rate_limits VALUES(?,?,?) ON CONFLICT(key) DO UPDATE SET count=excluded.count,expires=excluded.expires',[$key,$count,$until]);$db->exec('COMMIT');}catch(Throwable $e){$db->exec('ROLLBACK');throw $e;}
 if($count>$max)respond(['error'=>'Please wait before trying again'],429);
}
$_SESSION['csrf']??=bin2hex(random_bytes(32));$path=parse_url($_SERVER['REQUEST_URI'],PHP_URL_PATH);
if($path==='/api'){
 $action=$_GET['action']??'';
 if($_SERVER['REQUEST_METHOD']==='POST'){
  if((int)($_SERVER['CONTENT_LENGTH']??0)>20000)respond(['error'=>'Request too large'],413);
  $data=json_decode(file_get_contents('php://input'),true)??[];
  if(!hash_equals($_SESSION['csrf'],(string)($data['csrf']??'')))respond(['error'=>'Session token missing; reload the page'],403);
  if(in_array($action,['signup','login'],true)){
   limit('auth',20,900);$email=strtolower(trim((string)($data['email']??'')));$password=(string)($data['password']??'');
   if(!filter_var($email,FILTER_VALIDATE_EMAIL)||strlen($email)>254||strlen($password)<12||strlen($password)>128)respond(['error'=>'Use a valid email and a password of 12–128 characters'],400);
   if($action==='signup'){
    if(!hash_equals(trim(file_get_contents($root.'/portal-data/invite.key')),(string)($data['invite']??'')))respond(['error'=>'A valid workshop invitation code is required'],403);
    $id=bin2hex(random_bytes(16));try{query('INSERT INTO users VALUES(?,?,?,?)',[$id,$email,password_hash($password,PASSWORD_DEFAULT),microtime(true)]);}catch(PDOException $e){respond(['error'=>'Account could not be created'],409);}
   }else{$user=query('SELECT * FROM users WHERE email=?',[$email])->fetch(PDO::FETCH_ASSOC);if(!$user||!password_verify($password,$user['password']))respond(['error'=>'Email or password is incorrect'],401);$id=$user['id'];}
   session_regenerate_id(true);$_SESSION['uid']=$id;$_SESSION['csrf']=bin2hex(random_bytes(32));respond(['ok'=>true,'csrf'=>$_SESSION['csrf']]);
  }
  if(!isset($_SESSION['uid']))respond(['error'=>'Log in first'],401);$uid=$_SESSION['uid'];
  if($action==='logout'){session_destroy();respond(['ok'=>true]);}
  if($action==='task'){
   limit('task-'.$uid,10,3600);$prompt=trim((string)($data['prompt']??''));if(strlen($prompt)<1||strlen($prompt)>12000)respond(['error'=>'Describe your task in 1–12,000 characters'],400);
   $db->exec('BEGIN IMMEDIATE');try{
    if(query("SELECT count(*) FROM tasks WHERE user_id=? AND status IN ('queued','working')",[$uid])->fetchColumn()>=3){$db->exec('ROLLBACK');respond(['error'=>'Three tasks already queued or working'],409);}
    $parent=$data['parent']??null;
    if($parent&&!query("SELECT 1 FROM tasks WHERE id=? AND user_id=? AND status NOT IN ('queued','working')",[$parent,$uid])->fetchColumn()){$db->exec('ROLLBACK');respond(['error'=>'This project cannot be revised'],403);}
    $id=bin2hex(random_bytes(16));$now=microtime(true);query('INSERT INTO tasks(id,user_id,prompt,created,updated,parent_id) VALUES(?,?,?,?,?,?)',[$id,$uid,$prompt,$now,$now,$parent]);$db->exec('COMMIT');respond(['id'=>$id]);
   }catch(Throwable $e){$db->exec('ROLLBACK');respond(['error'=>'Task could not be queued'],500);}
  }
  if($action==='cancel'){query("UPDATE tasks SET cancel=1,status=CASE WHEN status='queued' THEN 'cancelled' ELSE status END WHERE id=? AND user_id=? AND status IN ('queued','working')",[(string)($data['id']??''),$uid]);respond(['ok'=>true]);}
  if($action==='whatsapp'){
   $status=($data['connect']??true)?'requested':'disconnected';$current=query('SELECT status FROM whatsapp WHERE user_id=?',[$uid])->fetchColumn();
   if($status==='requested'&&in_array($current,['connecting','connected','qr','reconnecting'],true))respond(['ok'=>true,'status'=>$current]);
   query('INSERT INTO whatsapp(user_id,status,updated) VALUES(?,?,?) ON CONFLICT(user_id) DO UPDATE SET status=excluded.status,qr=NULL,updated=excluded.updated',[$uid,$status,microtime(true)]);respond(['ok'=>true]);
  }
  respond(['error'=>'Unknown action'],404);
 }
 if($action==='session')respond(['user'=>isset($_SESSION['uid'])?query('SELECT id,email FROM users WHERE id=?',[$_SESSION['uid']])->fetch(PDO::FETCH_ASSOC):null,'csrf'=>$_SESSION['csrf']]);
 if(!isset($_SESSION['uid']))respond(['error'=>'Log in first'],401);$uid=$_SESSION['uid'];
 if($action==='state'){
  $tasks=query('SELECT id,prompt,status,role,cycle,error,summary,mode,team,progress,model_calls,created,updated FROM tasks WHERE user_id=? ORDER BY created DESC LIMIT 30',[$uid])->fetchAll(PDO::FETCH_ASSOC);
  foreach($tasks as &$task){$task['deliverables']=query('SELECT path,mime,size FROM deliverables WHERE task_id=?',[$task['id']])->fetchAll(PDO::FETCH_ASSOC);}unset($task);
  $wa=query('SELECT status,qr,qr_expires,updated FROM whatsapp WHERE user_id=?',[$uid])->fetch(PDO::FETCH_ASSOC);if($wa&&($wa['qr_expires']??0)<microtime(true))$wa['qr']=null;
  $roles=query("SELECT h.role,CASE WHEN h.role='watchdog' THEN h.status WHEN t.user_id=? THEN h.status ELSE 'idle' END AS status,CASE WHEN t.user_id=? THEN h.task_id ELSE NULL END AS task_id,h.updated FROM heartbeats h LEFT JOIN tasks t ON t.id=h.task_id",[$uid,$uid])->fetchAll(PDO::FETCH_ASSOC);
  respond(['tasks'=>$tasks,'roles'=>$roles,'whatsapp'=>$wa?:['status'=>'disconnected']]);
 }
 if($action==='events')respond(['events'=>query('SELECT e.role,e.kind,e.detail,e.created FROM events e JOIN tasks t ON e.task_id=t.id WHERE t.id=? AND t.user_id=? ORDER BY e.id DESC LIMIT 60',[(string)($_GET['id']??''),$uid])->fetchAll(PDO::FETCH_ASSOC)]);
 respond(['error'=>'Unknown action'],404);
}
if($path==='/download'){
 if(!isset($_SESSION['uid'])){http_response_code(401);exit;}$id=(string)($_GET['id']??'');
 if(!preg_match('/^[0-9a-f]{32}$/',$id)||!query("SELECT 1 FROM artifacts a JOIN tasks t ON a.task_id=t.id WHERE t.id=? AND t.user_id=? AND t.status='ready'",[$id,$_SESSION['uid']])->fetchColumn()){http_response_code(404);exit;}
 $requested=$_GET['file']??null;
 if($requested!==null){$output=query('SELECT path,mime FROM deliverables WHERE task_id=? AND path=?',[$id,(string)$requested])->fetch(PDO::FETCH_ASSOC);if(!$output){http_response_code(404);exit;}$project=$root.'/downloads/'.$id.'/';$file=realpath($project.$output['path']);if(!$file||!str_starts_with($file,$project)||is_link($project.$output['path'])){http_response_code(404);exit;}header('Content-Type: '.$output['mime']);header('Content-Disposition: attachment; filename="'.basename($output['path']).'"');readfile($file);exit;}
 $file=$root.'/downloads/'.$id.'.zip';header('Content-Type: application/zip');header('Content-Disposition: attachment; filename="workshop-'.$id.'.zip"');readfile($file);exit;
}
if($path!=='/'){http_response_code(404);echo 'Not found';exit;}readfile(__DIR__.'/shell.html');
