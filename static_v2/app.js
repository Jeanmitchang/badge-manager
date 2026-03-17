// Badge Manager v2.2 — app.js — version unique consolidée

// ─── STATE ────────────────────────────────────────────────
const S = {
  token:null, role:null, login:null, userId:null,
  mustChangePwd:false,
  icons:{nb:'🔑',eb:'🔑',sb:'🔑'},
  color:'#8b5cf6',
  currentConvPid:null, currentConvOtherId:null,
  groups:[], admins:[], users:[], contacts:[],
  _editGroupId:null,
};
let _meInterval = null;

// ─── API ──────────────────────────────────────────────────
async function api(method, path, body=null, raw=false) {
  const opts = {method, headers:{'Content-Type':'application/json'}};
  if (S.token) opts.headers['Authorization'] = `Bearer ${S.token}`;
  if (body) opts.body = JSON.stringify(body);
  const r = await fetch(path, opts);
  if (raw) return r;
  const txt = await r.text();
  let data; try { data = JSON.parse(txt); } catch { data = {detail:txt}; }
  if (!r.ok) throw new Error(data.detail || `Erreur ${r.status}`);
  return data;
}

// ─── UTILS ────────────────────────────────────────────────
function toast(msg, type='ok') {
  document.querySelectorAll('.toast').forEach(t=>t.remove());
  const t = document.createElement('div');
  t.className = `toast toast-${type}`;
  t.textContent = msg;
  document.body.appendChild(t);
  setTimeout(()=>t.remove(), 3200);
}
function errHtml(e){ return `<div class="loading" style="color:var(--red);">⚠ ${e.message||e}</div>`; }
function emptyHtml(m){ return `<div class="loading" style="color:var(--text3);">${m}</div>`; }
function fmtDate(iso, short=false) {
  if (!iso) return '—';
  const d = new Date(iso.endsWith('Z')?iso:iso+'Z');
  if (short) return d.toLocaleTimeString('fr-FR',{hour:'2-digit',minute:'2-digit'});
  return d.toLocaleDateString('fr-FR',{day:'2-digit',month:'2-digit',year:'2-digit'})+' '+d.toLocaleTimeString('fr-FR',{hour:'2-digit',minute:'2-digit'});
}
function updateTime(){ const e=document.getElementById('tb-t'); if(e) e.textContent=new Date().toLocaleTimeString('fr-FR'); }
function reqTypeLabel(t){ return {badge_quota:'📛 Badges supplémentaires',mct_rallonge:'⏱ Rallonge MCT',group_change:'🔄 Changement de groupe',delete_user:'🗑 Suppression'}[t]||t; }
function miniBar(v,mx,col='var(--cyan)'){const p=Math.min(100,Math.round(v/Math.max(mx,1)*100));return `<span style="display:inline-block;width:36px;height:3px;background:var(--bg);border-radius:2px;vertical-align:middle;margin:0 3px;overflow:hidden;"><span style="display:block;height:100%;width:${p}%;background:${p>=100?'var(--red)':col};border-radius:2px;"></span></span>`;}
function renderHeatmap(data){
  const D=['L','M','M','J','V','S','D'],counts={};
  (data||[]).forEach(d=>{counts[`${d.day}_${d.hour}`]=d.count;});
  const mx=Math.max(1,...Object.values(counts));
  let h='<div class="hm-grid"><div></div>';
  for(let i=0;i<24;i++) h+=`<div class="hm-hl">${i}</div>`;
  for(let d=0;d<7;d++){
    h+=`<div class="hm-dl">${D[d]}</div>`;
    for(let i=0;i<24;i++){const c=counts[`${d}_${i}`]||0;const v=c===0?0:Math.ceil((c/mx)*5);h+=`<div class="hm-c v${v}" title="${D[d]} ${i}h — ${c} MCT"></div>`;}
  }
  return h+'</div>';
}
function renderChart(data){
  const days=['L','M','M','J','V','S','A'],mx=Math.max(1,...(data||[]));
  return '<div class="ch-b">'+(data||[]).map((v,i)=>`<div class="ch-c"><div class="ch-bar" style="height:${Math.round(v/mx*100)}%;background:${i===6?'var(--cyan)':'rgba(0,200,240,.32)'};" title="${v} MCT"></div></div>`).join('')+'</div><div style="display:flex;justify-content:space-between;margin-top:5px;">'+days.map((x,i)=>`<span style="font-size:8px;color:${i===6?'var(--cyan)':'var(--text3)'};font-family:'DM Mono',monospace;flex:1;text-align:center;">${x}</span>`).join('')+'</div>';
}
function validateUID(uid){
  uid=uid.trim().toUpperCase();
  if(uid.length!==8) return 'UID doit faire exactement 8 caractères';
  if(!/^[0-9A-F]{8}$/.test(uid)) return 'UID doit contenir uniquement des caractères hex (0-9, A-F)';
  if(uid==='00000000'||uid==='FFFFFFFF') return 'UID invalide (valeur réservée)';
  return null;
}
function updC(ii,ci){const i=document.getElementById(ii),c=document.getElementById(ci);if(!i||!c)return;const l=i.value.length;c.textContent=`${l}/280`;c.style.color=l>250?'var(--amber)':'var(--text3)';}
function checkPwdStr(){
  const v=document.getElementById('pwd-new')?.value||'';
  const el=document.getElementById('pwd-str');if(!el)return;
  if(v.length<6){el.style.width=`${(v.length/6)*30}%`;el.style.background='var(--red)';}
  else if(v.length<=8){el.style.width='50%';el.style.background='var(--amber)';}
  else if(v.length<=11){el.style.width='75%';el.style.background='var(--teal)';}
  else{el.style.width='100%';el.style.background='var(--green)';}
}

// ─── SIDEBAR MOBILE ───────────────────────────────────────
function toggleSidebar(){
  const sb=document.getElementById('sb');
  const ov=document.getElementById('sb-overlay');
  sb.classList.toggle('open');
  if(sb.classList.contains('open')){ov.classList.add('hidden');ov.style.display='block';}
  else{ov.style.display='';}
}
function closeSidebar(){
  document.getElementById('sb').classList.remove('open');
  document.getElementById('sb-overlay').style.display='';
}

// ─── SIDEBAR MOBILE ───────────────────────────────────────
function toggleSidebar(){
  const sb=document.getElementById('sb');
  sb.classList.toggle('open');
}
function closeSidebar(){
  document.getElementById('sb').classList.remove('open');
}

// ─── AUTH ─────────────────────────────────────────────────
async function doLogin() {
  const login=document.getElementById('li').value.trim();
  const password=document.getElementById('lp').value;
  const errEl=document.getElementById('lerr');
  errEl.textContent='';
  if(!login||!password){errEl.textContent='Remplissez tous les champs';return;}
  try {
    const d=await api('POST','/api/login',{login,password});
    S.token=d.token; S.role=d.role; S.login=d.login; S.mustChangePwd=d.must_change_pwd;
    const parts=d.token.split('.');
    const pl=JSON.parse(atob(parts[1].replace(/-/g,'+').replace(/_/g,'/')));
    S.userId=pl.sub;
    document.getElementById('scr-login').classList.add('hidden');
    document.getElementById('scr-app').classList.remove('hidden');
    document.getElementById('sb-n').textContent=login;
    document.getElementById('sb-c').textContent={superadmin:'Superadmin',admin:'Administrateur',user:'Utilisateur'}[d.role]||d.role;
    if(S.mustChangePwd) document.getElementById('pwd-banner').classList.remove('hidden');
    buildNav(d.role);
    setInterval(updateTime,1000);
    setInterval(pollNotifs,30000);
    // Poll blocage compte
    _meInterval=setInterval(async()=>{
      if(!S.token)return;
      try{await api('GET','/api/me');}
      catch(e){
        if(e.message==='ACCOUNT_BLOCKED'){
          clearInterval(_meInterval);
          showBlockedOverlay();
        }
      }
    },30000);
    const first={superadmin:'sa-dash',admin:'adm-dash',user:'usr-badges'}[d.role];
    showP(first);
    pollNotifs();
  } catch(e) {
    errEl.textContent=e.message==='ACCOUNT_BLOCKED'?'Compte bloqué — contactez votre administrateur':e.message||'Connexion impossible';
    document.getElementById('lp').classList.add('inp-err');
    setTimeout(()=>document.getElementById('lp').classList.remove('inp-err'),2000);
  }
}

function showBlockedOverlay(){
  const ov=document.createElement('div');
  ov.style.cssText='position:fixed;inset:0;background:rgba(0,0,0,.92);z-index:999;display:flex;align-items:center;justify-content:center;flex-direction:column;gap:16px;';
  ov.innerHTML=`<div style="font-size:40px;">🚫</div><div style="font-family:'Syne',sans-serif;font-size:20px;font-weight:800;color:var(--red);">Compte bloqué</div><div style="font-size:13px;color:var(--text2);text-align:center;max-width:300px;">Votre compte a été bloqué. Contactez votre administrateur.</div><button onclick="doLogout()" style="padding:10px 24px;background:var(--bg3);border:1px solid var(--border);color:var(--text);border-radius:8px;cursor:pointer;font-family:'DM Sans',sans-serif;margin-top:8px;">Retour à la connexion</button>`;
  document.body.appendChild(ov);
  S.token=null;
}

function doLogout(){
  if(_meInterval){clearInterval(_meInterval);_meInterval=null;}
  S.token=S.role=S.login=S.userId=null; S.mustChangePwd=false;
  document.getElementById('scr-app').classList.add('hidden');
  document.getElementById('scr-login').classList.remove('hidden');
  document.getElementById('li').value=''; document.getElementById('lp').value='';
  document.getElementById('pwd-banner').classList.add('hidden');
  // Supprimer overlay blocage si présent
  document.querySelectorAll('[style*="z-index:999"]').forEach(e=>e.remove());
}

async function doChangePwd(){
  const cur=document.getElementById('pwd-cur').value;
  const nw=document.getElementById('pwd-new').value;
  const cfm=document.getElementById('pwd-cfm').value;
  const errEl=document.getElementById('pwd-err');
  errEl.textContent='';
  if(nw!==cfm){errEl.textContent='Les mots de passe ne correspondent pas';return;}
  if(nw.length<6||nw.length>14){errEl.textContent='6 à 14 caractères requis';return;}
  try{
    await api('POST','/api/change-password',{current_password:cur,new_password:nw});
    toast('Mot de passe mis à jour — reconnectez-vous','ok');
    setTimeout(()=>doLogout(),1500);
  }catch(e){errEl.textContent=e.message;}
}

// ─── NAV ──────────────────────────────────────────────────
const NAVS={
  superadmin:[{s:'Supervision'},{id:'sa-dash',i:'📊',l:'Tableau de bord',p:'sa-dash'},{id:'sa-journal',i:'📋',l:'Journal',p:'sa-journal'},{s:'Gestion'},{id:'sa-admins',i:'🛡️',l:'Admins',p:'sa-admins'},{id:'sa-users',i:'👥',l:'Utilisateurs et Groupes',p:'sa-users'},{id:'sa-badges',i:'🏷️',l:'Gestion des badges',p:'sa-badges'},{id:'sa-dem',i:'📨',l:'Demandes',p:'sa-dem',nb:1},{id:'sa-msgs',i:'💬',l:'Messages',p:'sa-msgs',nb:1},{s:'Système'},{id:'sa-params',i:'⚙️',l:'Paramètres',p:'sa-params'},{id:'params',i:'🔑',l:'Mon compte',p:'params'}],
  admin:[{s:'Supervision'},{id:'adm-dash',i:'📊',l:'Tableau de bord',p:'adm-dash'},{s:'Gestion'},{id:'adm-users',i:'👥',l:'Utilisateurs',p:'adm-users'},{id:'adm-grps',i:'🗂️',l:'Groupes',p:'adm-grps'},{id:'adm-dem',i:'📨',l:'Demandes',p:'adm-dem',nb:1},{id:'adm-msgs',i:'💬',l:'Messages',p:'adm-msgs',nb:1},{s:'Mon compte'},{id:'params',i:'🔑',l:'Mon compte',p:'params'}],
  user:[{s:'Mes accès'},{id:'usr-badges',i:'🏷️',l:'Mes badges',p:'usr-badges'},{id:'usr-mct',i:'📄',l:'Mes MCT',p:'usr-mct'},{s:'Communication'},{id:'usr-msgs',i:'💬',l:'Messages',p:'usr-msgs',nb:1},{id:'usr-dem',i:'📨',l:'Mes demandes',p:'usr-dem'},{s:'Mon compte'},{id:'params',i:'🔑',l:'Mon compte',p:'params'}],
};
const TITLES={'sa-dash':'Tableau de bord','sa-journal':'Journal','sa-admins':'Admins','sa-users':'Utilisateurs et Groupes','sa-badges':'Gestion des badges','sa-dem':'Demandes','sa-msgs':'Messages','sa-params':'Paramètres','adm-dash':'Tableau de bord','adm-users':'Utilisateurs','adm-grps':'Groupes','adm-dem':'Demandes','adm-msgs':'Messages','usr-badges':'Mes badges','usr-mct':'Mes MCT','usr-msgs':'Messages','usr-dem':'Mes demandes','params':'Mon compte'};

function buildNav(role){
  const nav=document.getElementById('sb-nav');nav.innerHTML='';
  (NAVS[role]||[]).forEach(it=>{
    if(it.s){const d=document.createElement('div');d.className='ns';d.textContent=it.s;nav.appendChild(d);return;}
    const d=document.createElement('div');d.className='ni';d.id='nav-'+it.id;
    d.innerHTML=`<span class="ni-i">${it.i}</span><span>${it.l}</span>${it.nb?`<span class="ni-b hidden" id="nb-${it.id}">0</span>`:''}`;
    d.onclick=()=>showP(it.p,it.id);
    nav.appendChild(d);
  });
}

function showP(pid,nid){
  document.querySelectorAll('.page').forEach(p=>p.classList.remove('act'));
  document.querySelectorAll('.ni').forEach(n=>n.classList.remove('act'));
  const pg=document.getElementById('p-'+pid);if(pg)pg.classList.add('act');
  if(nid){const nv=document.getElementById('nav-'+nid);if(nv)nv.classList.add('act');}
  document.getElementById('tb-bc').textContent=TITLES[pid]||pid;
  // Fermer sidebar sur mobile après navigation
  if(window.innerWidth<=860) closeSidebar();
  loadPage(pid);
}

async function pollNotifs(){
  if(!S.token)return;
  try{
    const d=await api('GET','/api/notifications');
    const total=(d.unread_notifs||0)+(d.unread_messages||0);
    document.getElementById('tb-dot')?.classList.toggle('hidden',total===0);
    if(d.unread_messages>0){['sa-msgs','adm-msgs','usr-msgs'].forEach(id=>{const nb=document.getElementById('nb-'+id);if(nb){nb.textContent=d.unread_messages;nb.classList.remove('hidden');}});}
    const pending=(await api('GET','/api/requests').catch(()=>[])).filter(r=>r.status==='pending').length;
    if(pending>0){['sa-dem','adm-dem'].forEach(id=>{const nb=document.getElementById('nb-'+id);if(nb){nb.textContent=pending;nb.classList.remove('hidden');}});}
  }catch(e){}
}

// ─── NOTIF PANEL ──────────────────────────────────────────
async function openNotifPanel(){
  const existing=document.getElementById('notif-panel');
  if(existing){existing.remove();return;}
  if(!S.token)return;
  try{
    const d=await api('GET','/api/notifications');
    await api('POST','/api/notifications/read');
    document.getElementById('tb-dot')?.classList.add('hidden');
    const notifs=(d.notifications||[]).filter(n=>n.type!=='watchdog_ok');
    let html=`<div id="notif-panel" style="position:fixed;top:56px;right:16px;width:300px;background:var(--bg2);border:1px solid var(--border);border-radius:12px;box-shadow:0 12px 40px rgba(0,0,0,.6);z-index:300;max-height:380px;overflow-y:auto;">
      <div style="padding:10px 14px;border-bottom:1px solid var(--border);display:flex;justify-content:space-between;align-items:center;">
        <span style="font-size:12px;font-weight:600;">Notifications</span>
        <span onclick="document.getElementById('notif-panel').remove()" style="cursor:pointer;font-size:18px;color:var(--text3);">×</span>
      </div>`;
    if(!notifs.length){html+='<div style="padding:20px;text-align:center;font-size:11px;color:var(--text3);">Aucune notification</div>';}
    else{
      const ic={new_message:'💬',new_request:'📨',request_handled:'✓',badge_attributed:'🏷️',system_alert:'⚠️',group_change:'🔄',delete_user:'🗑',user_assigned:'👤',group_deleted:'🗑'};
      notifs.slice(0,15).forEach(n=>{
        html+=`<div style="padding:9px 14px;border-bottom:1px solid rgba(30,45,66,.4);${!n.is_read?'background:rgba(0,200,240,.04)':''}">
          <div style="font-size:11px;font-weight:600;color:var(--text);">${ic[n.type]||'🔔'} ${n.title}</div>
          ${n.body?`<div style="font-size:10px;color:var(--text2);margin-top:2px;">${n.body}</div>`:''}
          <div style="font-size:9px;color:var(--text3);font-family:'DM Mono',monospace;margin-top:2px;">${fmtDate(n.created_at)}</div>
        </div>`;
      });
    }
    html+='</div>';
    document.body.insertAdjacentHTML('beforeend',html);
    setTimeout(()=>{
      document.addEventListener('click',function cp(e){
        const p=document.getElementById('notif-panel');
        if(p&&!p.contains(e.target)){p.remove();document.removeEventListener('click',cp);}
      });
    },100);
  }catch(e){toast(e.message,'err');}
}

// ─── PAGE LOADERS ──────────────────────────────────────────
async function loadPage(pid){
  const map={'sa-dash':loadSaDash,'sa-admins':loadSaAdmins,'sa-users':loadSaUsers,'sa-badges':loadSaBadges,'sa-dem':()=>loadDemandes('c-sa-dem'),'sa-msgs':()=>loadMsgs('c-sa-msgs'),'sa-journal':loadLogs,'sa-params':loadSaParams,'adm-dash':loadAdmDash,'adm-users':loadAdmUsers,'adm-grps':loadAdmGrps,'adm-dem':()=>loadDemandes('c-adm-dem'),'adm-msgs':()=>loadMsgs('c-adm-msgs'),'usr-badges':loadUsrBadges,'usr-mct':loadUsrMct,'usr-msgs':()=>loadMsgs('c-usr-msgs'),'usr-dem':loadUsrDem};
  if(map[pid]) await map[pid]();
}

// ─── SA DASH ──────────────────────────────────────────────
async function loadSaDash(){
  const el=document.getElementById('c-sa-dash');
  try{
    const[stats,health]=await Promise.all([api('GET','/api/dashboard'),api('GET','/api/health')]);
    const disk=health.disk||{};
    const isMobile=window.innerWidth<=600;
    el.innerHTML=`
    <div class="g4" style="${isMobile?'grid-template-columns:1fr 1fr;':''}">
      <div class="kpi k1"><div class="kpi-l">Admins</div><div class="kpi-v">${stats.admins||0}</div><div class="kpi-s">${stats.groups||0} groupes</div></div>
      <div class="kpi k2"><div class="kpi-l">Utilisateurs</div><div class="kpi-v">${stats.users||0}</div><div class="kpi-s">${stats.suspended||0} suspendus</div></div>
      <div class="kpi k3"><div class="kpi-l">MCT / 24h</div><div class="kpi-v">${stats.mct_24h||0}</div><div class="kpi-s">${stats.mct_7d||0} / 7j</div></div>
      <div class="kpi k4"><div class="kpi-l">Demandes</div><div class="kpi-v">${stats.pending_requests||0}</div><div class="kpi-s">en attente</div></div>
    </div>
    ${isMobile?`
    <div class="card" style="margin-bottom:13px;">
      <div class="ct">Résumé système</div>
      <div style="display:flex;flex-direction:column;gap:8px;font-size:11px;font-family:'DM Mono',monospace;">
        <div style="display:flex;justify-content:space-between;">
          <span style="color:var(--text3);">Wine</span><span style="color:${health.wine?'var(--teal)':'var(--red)'}">${health.wine?'✓ OK':'✗ KO'}</span>
        </div>
        <div style="display:flex;justify-content:space-between;">
          <span style="color:var(--text3);">Cert SSL</span><span style="color:${health.cert?'var(--teal)':'var(--red)'}">${health.cert?'✓ OK':'✗ KO'}</span>
        </div>
        <div style="display:flex;justify-content:space-between;">
          <span style="color:var(--text3);">Disque</span><span style="color:${(disk.pct||0)>80?'var(--amber)':'var(--teal)'}">${disk.pct||0}% utilisé</span>
        </div>
        <div style="display:flex;justify-content:space-between;">
          <span style="color:var(--text3);">Queue Wine</span><span style="color:var(--text)">${health.queue||0}/5</span>
        </div>
        <div style="display:flex;justify-content:space-between;">
          <span style="color:var(--text3);">Badges stock</span><span style="color:var(--purple)">${stats.stock_badges||0}</span>
        </div>
      </div>
    </div>
    <div class="card">
      <div class="ct">MCT — 7 derniers jours</div>
      ${renderChart(stats.mct_by_day||[])}
    </div>
    `:` 
    <div class="g6040">
      <div class="card"><div class="ct">Profil d'utilisation — 7 jours</div><div style="overflow-x:auto;">${renderHeatmap(stats.heatmap||[])}</div></div>
      <div class="card"><div class="ct">Santé système</div>
        <div class="hl-g">
          <div><div class="hl-l">Disque <span>${disk.pct||0}%</span></div><div class="hl-b"><div class="hl-f ${(disk.pct||0)>80?'wa':'ok'}" style="width:${disk.pct||0}%"></div></div></div>
          <div><div class="hl-l">Queue Wine <span>${health.queue||0}/5</span></div><div class="hl-b"><div class="hl-f ok" style="width:${(health.queue||0)*20}%"></div></div></div>
          <div><div class="hl-l">Wine <span style="color:${health.wine?'var(--teal)':'var(--red)'}">${health.wine?'OK':'KO'}</span></div><div class="hl-b"><div class="hl-f ${health.wine?'ok':'wa'}" style="width:${health.wine?100:0}%"></div></div></div>
          <div><div class="hl-l">Cert <span style="color:${health.cert?'var(--teal)':'var(--red)'}">${health.cert?'OK':'KO'}</span></div><div class="hl-b"><div class="hl-f ${health.cert?'ok':'wa'}" style="width:${health.cert?100:0}%"></div></div></div>
        </div>
        <div style="margin-top:10px;padding-top:8px;border-top:1px solid var(--border);font-size:9px;color:var(--text3);font-family:'DM Mono',monospace;">
          Stock badges: <span style="color:var(--purple)">${stats.stock_badges||0}</span> &nbsp;·&nbsp; Disque libre: <span style="color:var(--teal)">${disk.free_gb||'?'} Go</span>
        </div>
      </div>
    </div>
    <div class="card"><div class="ct">MCT — 7 derniers jours</div>${renderChart(stats.mct_by_day||[])}</div>
    `}`;
  }catch(e){el.innerHTML=errHtml(e);}
}

// ─── SA ADMINS ────────────────────────────────────────────
async function loadSaAdmins(){
  const el=document.getElementById('c-sa-admins');
  try{
    const admins=await api('GET','/api/admins');
    S.admins=admins;
    if(!admins.length){el.innerHTML=emptyHtml('Aucun admin — créez-en un avec le bouton ci-dessus');return;}
    el.innerHTML=`<div class="tbl-wrap"><table class="tbl"><thead><tr><th>Identifiant</th><th>Groupes</th><th>Utilisateurs</th><th>Statut</th><th>Actions</th></tr></thead><tbody>
    ${admins.map(a=>`<tr>
      <td style="color:var(--text);font-family:'DM Mono',monospace;">${a.login}</td>
      <td>${a.group_count||0}</td><td>${a.user_count||0}</td>
      <td><span class="chip ${a.is_active?'c-ok':'c-err'}">${a.is_active?'Actif':'Bloqué'}</span></td>
      <td><div style="display:flex;gap:4px;">
        <button class="btn bg xs" onclick="openEditAdmin('${a.id}','${a.login}',${a.jwt_ttl_hours})">✏️ Éditer</button>
        <button class="btn bg xs" onclick="openResetPwd('${a.id}','${a.login}')">🔑 Reset MDP</button>
        <button class="btn bw xs" onclick="toggleBlock('${a.id}',${a.is_active},true)">${a.is_active?'⛔ Bloquer':'✓ Débloquer'}</button>
        <button class="btn bd xs" onclick="confirmAction('Supprimer ${a.login} ?','Cette action est irréversible.',()=>delAdmin('${a.id}'))">🗑</button>
      </div></td>
    </tr>`).join('')}</tbody></table></div>`;
  }catch(e){el.innerHTML=errHtml(e);}
}

// ─── SA USERS ─────────────────────────────────────────────
async function loadSaUsers(){
  const el=document.getElementById('c-sa-users');
  try{
    const[users,admins,groups]=await Promise.all([api('GET','/api/users'),api('GET','/api/admins'),api('GET','/api/groups')]);
    S.users=users;S.admins=admins;S.groups=groups;
    const byAdmin={};const susp=[];
    users.forEach(u=>{
      if(u.is_deleted){susp.push(u);return;}
      const k=u.admin_id||'__none__';
      (byAdmin[k]=byAdmin[k]||[]).push(u);
    });
    let html='';
    for(const[aid,list] of Object.entries(byAdmin)){
      const adm=admins.find(a=>a.id===aid);
      html+=`<div class="card" style="margin-bottom:12px;"><div style="display:flex;align-items:center;gap:8px;margin-bottom:10px;"><span>🛡️</span><span style="font-size:12px;font-weight:600;">${adm?adm.login:'Sans admin'}</span><span style="font-size:10px;color:var(--text3);font-family:'DM Mono',monospace;margin-left:auto;">${list.length} user(s)</span></div>${list.map(u=>renderUser(u,groups,true)).join('')}</div>`;
    }
    if(susp.length) html+=`<div class="card" style="margin-bottom:12px;border-top:2px solid var(--red);"><div style="display:flex;align-items:center;gap:8px;margin-bottom:10px;"><span>⚠️</span><span style="font-size:12px;font-weight:600;color:var(--red);">Suspendus (${susp.length})</span></div>${susp.map(u=>`<div class="ur"><div class="ur-av">❓</div><div class="ur-inf"><div class="ur-n">${u.login}</div><div class="ur-m">En attente décision superadmin</div></div><span class="chip c-susp">Suspendu</span><div class="ur-acts"><button class="btn bt xs" onclick="restoreUser('${u.id}')">Restaurer</button><button class="btn bd xs" onclick="confirmAction('Supprimer définitivement ${u.login} ?','',()=>delUser('${u.id}',true))">🗑 Suppr.</button></div></div>`).join('')}</div>`;
    el.innerHTML=html||emptyHtml('Aucun utilisateur');
  }catch(e){el.innerHTML=errHtml(e);}
}

// ─── SA BADGES (STOCK) ────────────────────────────────────
async function loadSaBadges(){
  const el=document.getElementById('c-sa-badges');
  try{
    const[stock,users,admins]=await Promise.all([api('GET','/api/stock'),api('GET','/api/users'),api('GET','/api/admins')]);
    const avail=stock.filter(b=>b.stock_status==='available');
    const attrib=stock.filter(b=>b.stock_status==='attributed');
    const all=[...users,...admins];
    let html=`<div class="card" style="margin-bottom:13px;"><div class="ct">Stock disponible — ${avail.length} référence(s)</div>
    ${avail.length?avail.map(b=>`<div class="stock-row">
      <span style="font-size:20px;">${b.icon}</span>
      <div class="stock-inf"><div class="stock-n">${b.name}</div><div class="stock-u">${b.uid}</div></div>
      <span class="chip c-dispo">Disponible</span>
      <div style="display:flex;gap:5px;">
        <button class="btn bp2 sm" onclick="openAttrib('${b.id}','${b.name} — ${b.uid}')">Attribuer</button>
        <button class="btn bd sm" onclick="confirmAction('Supprimer ce badge ?','',()=>delStock('${b.id}'))">🗑</button>
      </div>
    </div>`).join(''):'<div style="font-size:11px;color:var(--text3);text-align:center;padding:16px;">Aucun badge en stock — référencez-en avec le bouton ci-dessus</div>'}
    </div>`;
    if(attrib.length){
      html+=`<div class="card"><div class="ct">Badges attribués</div>
      <table class="tbl"><thead><tr><th>Badge</th><th>UID</th><th>Attribué à</th><th>Rôle</th><th>Actions</th></tr></thead><tbody>
      ${attrib.map(b=>{const t=all.find(u=>u.id===b.attributed_to);return`<tr>
        <td>${b.icon} ${b.name}</td><td class="mc">${b.uid}</td>
        <td style="color:var(--text);">${t?t.login:'?'}</td>
        <td><span class="chip c-info">${t?t.role:'?'}</span></td>
        <td><button class="btn bd sm" onclick="reclaimStock('${b.id}')">Retirer</button></td>
      </tr>`;}).join('')}</tbody></table></div>`;
    }
    el.innerHTML=html;
  }catch(e){el.innerHTML=errHtml(e);}
}

// ─── DEMANDES ─────────────────────────────────────────────
async function loadDemandes(cid){
  const el=document.getElementById(cid);
  try{
    const reqs=await api('GET','/api/requests');
    const pend=(reqs||[]).filter(r=>r.status==='pending');
    if(!pend.length){el.innerHTML=emptyHtml('Aucune demande en attente ✓');return;}
    el.innerHTML=pend.map(r=>`<div class="dm">
      <div style="display:flex;align-items:flex-start;justify-content:space-between;gap:8px;">
        <div><div class="dm-t">${reqTypeLabel(r.type)}</div>
        <div class="dm-u">${r.requester_login||r.requester_id}</div>
        <div class="dm-m">${r.motif||'Sans motif'} · ${fmtDate(r.created_at)}</div></div>
        <span class="chip c-warn">En attente</span>
      </div>
      <div class="dm-acts">
        <button class="btn bt sm" onclick="handleReq('${r.id}','approved','${cid}')">✓ Approuver</button>
        <button class="btn bd sm" onclick="handleReq('${r.id}','refused','${cid}')">✗ Refuser</button>
      </div>
    </div>`).join('');
    // Mettre à jour badge nav
    ['sa-dem','adm-dem'].forEach(id=>{const nb=document.getElementById('nb-'+id);if(nb){nb.textContent=pend.length;nb.classList.toggle('hidden',pend.length===0);}});
  }catch(e){el.innerHTML=errHtml(e);}
}

async function handleReq(rid,status,cid){
  try{await api('PATCH',`/api/requests/${rid}`,{status});toast(`Demande ${status==='approved'?'approuvée':'refusée'}`,'ok');await loadDemandes(cid);pollNotifs();}
  catch(e){toast(e.message,'err');}
}

// ─── MESSAGES ─────────────────────────────────────────────
async function loadMsgs(cid){
  const el=document.getElementById(cid);
  try{
    const[convs,contacts]=await Promise.all([api('GET','/api/messages/conversations'),api('GET','/api/messages/contacts')]);
    S.contacts=contacts;
    el.innerHTML=`<div class="g2">
      <div class="card">
        <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:10px;">
          <div class="ct" style="margin:0;">Conversations</div>
          ${contacts.length?`<button class="btn bp sm" onclick="openNewMsg('${cid}')">+ Message</button>`:''}
        </div>
        ${convs.length?convs.map(c=>`<div class="conv-item" onclick="loadConv('${c.other_id}','${c.other_login}','${cid}')">
          <div class="conv-av">👤</div>
          <div style="flex:1;min-width:0;">
            <div class="conv-n">${c.other_login}${c.unread?` <span class="ni-b">${c.unread}</span>`:''} <span class="chip c-info" style="margin-left:2px;">${c.other_role}</span></div>
            <div class="conv-l">${c.last_message||'—'}</div>
          </div>
        </div>`).join(''):emptyHtml('Aucune conversation')}
      </div>
      <div class="card" id="conv-panel-${cid}">
        <div style="font-size:11px;color:var(--text3);text-align:center;padding:24px;">Sélectionnez une conversation</div>
      </div>
    </div>`;
  }catch(e){el.innerHTML=errHtml(e);}
}

async function loadConv(otherId,otherLogin,cid){
  S.currentConvOtherId=otherId;S.currentConvPid=cid;
  const panel=document.getElementById(`conv-panel-${cid}`);
  panel.innerHTML=`<div class="ct">${otherLogin}</div>
    <div class="msg-th" id="conv-thread"></div>
    <div class="mc-wrap">
      <div style="flex:1;"><textarea class="mc-inp" id="conv-inp" rows="2" placeholder="Message... (max 280 car.)" maxlength="280" oninput="updC('conv-inp','conv-ctr')"></textarea><div class="mc-ctr" id="conv-ctr">0/280</div></div>
      <button class="btn bp sm" onclick="sendConvMsg('${otherId}','${cid}')">Envoyer</button>
    </div>`;
  try{
    const msgs=await api('GET',`/api/messages/${otherId}`);
    const thread=document.getElementById('conv-thread');
    thread.innerHTML=msgs.map(m=>`<div class="mi ${m.from_id===S.userId?'fa':'fu'}">${m.content}<div class="mm">${m.from_id===S.userId?'Moi':otherLogin} · ${fmtDate(m.created_at)}</div></div>`).join('');
    thread.scrollTop=thread.scrollHeight;
  }catch(e){}
}

async function sendConvMsg(toId,cid){
  const inp=document.getElementById('conv-inp');
  const content=inp?.value.trim();
  if(!content)return;
  try{
    await api('POST','/api/messages',{to_id:toId,content});
    inp.value='';
    const ctr=document.getElementById('conv-ctr');if(ctr)ctr.textContent='0/280';
    await loadConv(toId,toId,cid);
  }catch(e){toast(e.message,'err');}
}

function openNewMsg(cid){
  const contacts=S.contacts||[];
  if(!contacts.length){toast('Aucun contact disponible','info');return;}
  document.getElementById('new-msg-popup')?.remove();
  const div=document.createElement('div');
  div.id='new-msg-popup';
  div.style.cssText='position:fixed;top:50%;left:50%;transform:translate(-50%,-50%);background:var(--bg2);border:1px solid var(--border);border-radius:12px;padding:20px;width:340px;z-index:250;box-shadow:0 16px 50px rgba(0,0,0,.6);';
  div.innerHTML=`<h3 style="font-family:'Syne',sans-serif;font-size:15px;font-weight:700;margin-bottom:12px;">Nouveau message</h3>
    <div class="fgi"><label class="fl">Destinataire</label><select class="sel" id="new-msg-to">${contacts.map(c=>`<option value="${c.id}">${c.login} (${c.role})</option>`).join('')}</select></div>
    <div class="fgi"><label class="fl">Message (max 280 car.)</label><textarea class="mc-inp" id="new-msg-content" rows="3" placeholder="Votre message..." maxlength="280" oninput="updC('new-msg-content','new-msg-ctr')" style="width:100%;"></textarea><div class="mc-ctr" id="new-msg-ctr">0/280</div></div>
    <div style="display:flex;justify-content:flex-end;gap:7px;margin-top:12px;">
      <button class="btn bg" onclick="document.getElementById('new-msg-popup').remove()">Annuler</button>
      <button class="btn bp" onclick="sendNewMsg('${cid}')">Envoyer</button>
    </div>`;
  document.body.appendChild(div);
}

async function sendNewMsg(cid){
  const toId=document.getElementById('new-msg-to').value;
  const content=document.getElementById('new-msg-content').value.trim();
  if(!content){toast('Message vide','err');return;}
  try{
    await api('POST','/api/messages',{to_id:toId,content});
    document.getElementById('new-msg-popup')?.remove();
    toast('Message envoyé ✓','ok');
    await loadMsgs(cid);
  }catch(e){toast(e.message,'err');}
}

// ─── LOGS ─────────────────────────────────────────────────
async function loadLogs(){
  const el=document.getElementById('log-s');
  try{
    const logs=await api('GET','/api/logs?limit=100');
    if(!logs.length){el.innerHTML=emptyHtml('Aucun événement');return;}
    el.innerHTML=logs.map(l=>{
      const tp=l.event.includes('echec')||l.event.includes('error')?'err':l.event.includes('limit')||l.event.includes('delet')||l.event.includes('block')?'warn':l.event.includes('ok')||l.event.includes('created')||l.event.includes('generated')?'ok':'info';
      let detail='';try{const d=JSON.parse(l.detail||'{}');detail=d.badge||d.reason||d.action||'';}catch{}
      return`<div class="le"><span class="lt">${fmtDate(l.created_at,true)}</span><span class="lev ${tp}">${l.event}</span><span class="ld">${l.user_login||''} ${detail?'— '+detail:''}</span></div>`;
    }).join('');
  }catch(e){el.innerHTML=errHtml(e);}
}

// ─── SA PARAMS ────────────────────────────────────────────
async function loadSaParams(){
  const el=document.getElementById('c-sa-params');
  try{
    const cfg=await api('GET','/api/config');
    el.innerHTML=`<div class="g2">
    <div class="card"><div class="ct">Limites globales</div>
      <div style="display:flex;flex-direction:column;gap:11px;">
        <div><div class="fl">Badges max / utilisateur</div><div style="display:flex;gap:7px;align-items:center;"><input type="number" class="inp" id="cfg-quota" value="${cfg.badge_quota_default||5}" style="width:70px;"></div></div>
        <div><div class="fl">MCT max / 24h glissantes</div><div style="display:flex;gap:7px;align-items:center;"><input type="number" class="inp" id="cfg-mct" value="${cfg.mct_daily_limit||5}" style="width:70px;"></div></div>
        <div><div class="fl">Durée token JWT défaut</div><select class="sel" id="cfg-ttl"><option value="1" ${cfg.jwt_ttl_hours_default=='1'?'selected':''}>1 heure</option><option value="24" ${cfg.jwt_ttl_hours_default=='24'?'selected':''}>24 heures</option><option value="168" ${cfg.jwt_ttl_hours_default=='168'?'selected':''}>7 jours</option><option value="720" ${cfg.jwt_ttl_hours_default=='720'?'selected':''}>30 jours</option></select></div>
        <div><div class="fl">Validité badge VIGIK (heures)</div><div style="display:flex;gap:7px;align-items:center;"><input type="number" class="inp" id="cfg-vigik" value="${cfg.vigik_duration_hours||84}" style="width:70px;"></div></div>
        <div><div class="fl">Alerte disque (%)</div><div style="display:flex;gap:7px;align-items:center;"><input type="number" class="inp" id="cfg-disk" value="${cfg.disk_alert_threshold_pct||80}" style="width:70px;"></div></div>
        <button class="btn bp" onclick="saveConfig()">Sauvegarder</button>
      </div>
    </div>
    <div class="card"><div class="ct">Procédure d'urgence</div>
      <p style="font-size:11px;color:var(--text2);margin-bottom:12px;line-height:1.7;">Accès SSH uniquement en cas de perte d'accès.</p>
      <div style="background:var(--bg3);border:1px solid var(--border);border-radius:6px;padding:10px;font-family:'DM Mono',monospace;font-size:10px;color:var(--cyan);">ssh budgie@100.108.233.43<br>cd ~/Documents/Vigik_v2<br>python3 emergency_v2.py</div>
    </div></div>`;
  }catch(e){el.innerHTML=errHtml(e);}
}

async function saveConfig(){
  try{
    await api('PATCH','/api/config',{badge_quota_default:parseInt(document.getElementById('cfg-quota').value)||5,mct_daily_limit:parseInt(document.getElementById('cfg-mct').value)||5,jwt_ttl_hours_default:parseInt(document.getElementById('cfg-ttl').value)||24,vigik_duration_hours:parseInt(document.getElementById('cfg-vigik').value)||84,disk_alert_threshold_pct:parseInt(document.getElementById('cfg-disk').value)||80});
    toast('Configuration sauvegardée','ok');
  }catch(e){toast(e.message,'err');}
}

// ─── ADM DASH ─────────────────────────────────────────────
async function loadAdmDash(){
  const el=document.getElementById('c-adm-dash');
  try{
    const[stats,stock]=await Promise.all([
      api('GET','/api/dashboard'),
      api('GET','/api/stock').catch(()=>[]),
    ]);
    const received=stock.filter(b=>b.stock_status==='attributed'&&b.attributed_to===S.userId);
    const cols=window.innerWidth<=600?'grid-template-columns:1fr 1fr;':'';
    el.innerHTML=`<div class="g3" style="${cols}">
      <div class="kpi k1"><div class="kpi-l">Groupes</div><div class="kpi-v">${stats.group_count||0}</div></div>
      <div class="kpi k2"><div class="kpi-l">Utilisateurs</div><div class="kpi-v">${stats.user_count||0}</div></div>
      <div class="kpi k3"><div class="kpi-l">MCT aujourd'hui</div><div class="kpi-v">${stats.mct_today||0}</div></div>
    </div>
    ${stats.pending_requests>0?`<div class="card" style="margin-bottom:13px;"><div class="ct">Demandes en attente</div><div style="font-size:26px;font-family:'Syne',sans-serif;font-weight:800;color:var(--amber);">${stats.pending_requests}</div><button class="btn bw sm" style="margin-top:8px;" onclick="showP('adm-dem','adm-dem')">Voir →</button></div>`:''}
    ${received.length?`<div class="card" style="border-top:2px solid var(--purple);"><div class="ct">Badges reçus du superadmin — à dispatcher</div>
      ${received.map(b=>`<div class="stock-row">
        <span style="font-size:20px;">${b.icon}</span>
        <div class="stock-inf"><div class="stock-n">${b.name}</div><div class="stock-u">${b.uid}</div></div>
        <span class="chip c-attrib">Reçu</span>
        <div style="display:flex;gap:5px;flex-wrap:wrap;">
          <button class="btn bp2 sm" onclick="openDispatchBadge('${b.id}','${b.name} — ${b.uid}')">Dispatcher</button>
        </div>
      </div>`).join('')}
    </div>`:''}`;
  }catch(e){el.innerHTML=errHtml(e);}
}

// ─── ADM USERS ────────────────────────────────────────────
async function loadAdmUsers(){
  const el=document.getElementById('c-adm-users');
  try{
    const[users,groups]=await Promise.all([api('GET','/api/users'),api('GET','/api/groups')]);
    S.users=users;S.groups=groups;
    const byGrp={};
    users.forEach(u=>{const k=u.group_id||'__none__';(byGrp[k]=byGrp[k]||[]).push(u);});
    let html='';
    for(const[gid,list] of Object.entries(byGrp)){
      const grp=groups.find(g=>g.id===gid);
      html+=`<div class="card" style="margin-bottom:11px;"><div style="display:flex;align-items:center;gap:8px;margin-bottom:10px;"><div style="width:10px;height:10px;border-radius:50%;background:${grp?grp.color:'var(--text3)'}"></div><span style="font-size:12px;font-weight:600;">${grp?grp.name:'Sans groupe'}</span><span style="font-size:10px;color:var(--text3);font-family:'DM Mono',monospace;margin-left:auto;">${list.length} user(s)</span></div>${list.map(u=>renderUser(u,groups,false)).join('')}</div>`;
    }
    el.innerHTML=html||emptyHtml('Aucun utilisateur dans vos groupes');
  }catch(e){el.innerHTML=errHtml(e);}
}

// ─── ADM GROUPS ───────────────────────────────────────────
async function loadAdmGrps(){
  const el=document.getElementById('c-adm-grps');
  try{
    const[groups,users]=await Promise.all([api('GET','/api/groups'),api('GET','/api/users')]);
    S.groups=groups;
    if(!groups.length){el.innerHTML=emptyHtml('Aucun groupe — créez-en un avec le bouton ci-dessus');return;}
    el.innerHTML=groups.map(g=>{
      const ug=users.filter(u=>u.group_id===g.id);
      return`<div class="grp-card">
        <div class="grp-hd">
          <div class="grp-dot" style="background:${g.color}"></div>
          <span class="grp-nm">${g.name}</span>
          <span style="font-size:10px;color:var(--text3);font-family:'DM Mono',monospace;">${ug.length} user(s)</span>
          <div style="display:flex;gap:5px;margin-left:auto;">
            <button class="btn bg sm" onclick="openEditGrp('${g.id}','${g.name}','${g.color}')">✏️ Éditer</button>
            <button class="btn bd sm" onclick="confirmAction('Supprimer ${g.name} ?','Les utilisateurs seront suspendus.',()=>delGroup('${g.id}'))">🗑</button>
          </div>
        </div>
        ${ug.length?`<div class="grp-pills">${ug.map(u=>`<span class="grp-pill">${u.login}</span>`).join('')}</div>`:''}
      </div>`;
    }).join('');
  }catch(e){el.innerHTML=errHtml(e);}
}

// ─── USR BADGES ───────────────────────────────────────────
async function loadUsrBadges(){
  const el=document.getElementById('c-usr-badges');
  try{
    const[badges,dash]=await Promise.all([api('GET','/api/badges'),api('GET','/api/dashboard')]);
    const quota=dash.badge_quota||5;
    const pct=Math.min(100,Math.round(badges.length/quota*100));
    const now=Date.now();
    let html=`<div class="lim-w"><div class="lim-ls"><span>Badges utilisés</span><span>${badges.length} / ${quota}</span></div><div class="lim-b"><div class="lim-f ${pct>=100?'wa':'ok'}" style="width:${pct}%"></div></div></div>
    <div class="bg-grid">
    ${badges.map(b=>{
      const valid=b.last_encoded&&(new Date(b.last_encoded.endsWith('Z')?b.last_encoded:b.last_encoded+'Z').getTime()>now-84*3600*1000);
      const cls=b.last_encoded?(valid?'valid':'expired'):'';
      return`<div class="bgc ${cls}">
        <span class="bgc-i">${b.icon}</span><div class="bgc-n">${b.name}</div><div class="bgc-u">${b.uid}</div>
        <div class="bgc-s">${b.last_encoded?`<span class="chip ${valid?'c-ok':'c-err'}">${valid?'✓ Valide':'✗ Expiré'}</span>`:'<span class="chip c-info">Jamais encodé</span>'}</div>
        <div class="bgc-e">${b.last_encoded?fmtDate(b.last_encoded):''}</div>
        <div style="display:flex;gap:4px;justify-content:center;margin-top:8px;">
          <button class="btn bp xs" onclick="encodeBadge('${b.id}','${b.name}','${b.uid}')">⚡ Encoder</button>
          <button class="btn bg xs" onclick="openEditBadge('${b.id}','${b.name}','${b.uid}','${b.icon}')">✏️</button>
          <button class="btn bd xs" onclick="confirmAction('Supprimer ${b.name} ?','',()=>delBadge('${b.id}'))">🗑</button>
        </div>
      </div>`;
    }).join('')}
    ${badges.length<quota
      ?`<div class="bgc new-c" onclick="openMo('mo-new-badge')"><span style="font-size:22px;">+</span><div style="font-size:11px;margin-top:6px;">Nouveau badge</div><div style="font-size:9px;font-family:'DM Mono',monospace;margin-top:3px;">${quota-badges.length} restant(s)</div></div>`
      :`<div class="bgc new-c" onclick="openRequest('badge_quota','Demande de badges supplémentaires')"><span style="font-size:22px;">📨</span><div style="font-size:11px;margin-top:6px;">Quota atteint</div><div style="font-size:9px;font-family:'DM Mono',monospace;margin-top:3px;">Demander + de badges</div></div>`}
    </div>`;
    el.innerHTML=html;
  }catch(e){el.innerHTML=errHtml(e);}
}

// ─── USR MCT ──────────────────────────────────────────────
async function loadUsrMct(){
  const el=document.getElementById('c-usr-mct');
  try{
    const[quota,history]=await Promise.all([api('GET','/api/mct-quota'),api('GET','/api/mct-history')]);
    const pct=Math.min(100,Math.round(quota.used/quota.limit*100));
    el.innerHTML=`<div class="card" style="margin-bottom:11px;">
      <div class="lim-ls" style="display:flex;justify-content:space-between;font-size:10px;font-family:'DM Mono',monospace;color:var(--text3);margin-bottom:4px;"><span>MCT utilisés (24h glissantes)</span><span>${quota.used} / ${quota.limit} — ${quota.remaining} restant(s)</span></div>
      <div class="lim-b"><div class="lim-f ${pct>=100?'wa':'ok'}" style="width:${pct}%"></div></div>
    </div>
    <div class="card">
      <table class="tbl"><thead><tr><th>Badge</th><th>UID</th><th>Généré</th><th>Expire</th><th>Statut</th></tr></thead><tbody>
      ${history.length?history.map(m=>{const exp=new Date(m.expires_at.endsWith('Z')?m.expires_at:m.expires_at+'Z')<new Date();return`<tr><td>${m.badge_name||'?'}</td><td class="mc">${m.badge_uid||'?'}</td><td style="font-size:10px;color:var(--text2);">${fmtDate(m.created_at)}</td><td style="font-size:10px;color:${exp?'var(--red)':'var(--amber)'};">${fmtDate(m.expires_at)}</td><td><span class="chip ${exp?'c-err':'c-ok'}">${exp?'Expiré':'Valide'}</span></td></tr>`;}).join(''):'<tr><td colspan="5" style="text-align:center;color:var(--text3);">Aucun MCT généré</td></tr>'}
      </tbody></table>
    </div>
    ${quota.remaining===0?`<div style="text-align:center;margin-top:10px;"><button class="btn bw sm" onclick="openRequest('mct_rallonge','Demande de rallonge MCT')">📨 Demander une rallonge</button></div>`:''}`;
  }catch(e){el.innerHTML=errHtml(e);}
}

// ─── USR DEMANDES ─────────────────────────────────────────
async function loadUsrDem(){
  const el=document.getElementById('c-usr-dem');
  try{
    const reqs=await api('GET','/api/requests');
    if(!reqs.length){el.innerHTML=emptyHtml('Aucune demande en cours');return;}
    el.innerHTML=`<div class="card" style="max-width:500px;">${reqs.map(r=>`<div class="dm"><div class="dm-t">${reqTypeLabel(r.type)}</div><div class="dm-m">${r.motif||'Sans motif'}</div><div style="margin-top:8px;"><span class="chip ${r.status==='pending'?'c-warn':r.status==='approved'?'c-ok':'c-err'}">${{pending:'En attente',approved:'Approuvée',refused:'Refusée',cancelled:'Annulée'}[r.status]||r.status}</span></div><div style="font-size:9px;color:var(--text3);font-family:'DM Mono',monospace;margin-top:4px;">${fmtDate(r.created_at)}</div></div>`).join('')}</div>`;
  }catch(e){el.innerHTML=errHtml(e);}
}

// ─── USER ROW ─────────────────────────────────────────────
function renderUser(u,groups,isSa=true){
  const grp=groups.find(g=>g.id===u.group_id);
  const bpct=Math.min(100,Math.round((u.badges_count||0)/u.badge_quota*100));
  const st=u.is_deleted?'<span class="chip c-susp">Suspendu</span>':!u.is_active?'<span class="chip c-err">Bloqué</span>':'<span class="chip c-ok">Actif</span>';
  const admBtns=!isSa?`<button class="btn bg xs" onclick="openEditUser('${u.id}',${u.badge_quota},${u.jwt_ttl_hours},${u.is_active})" title="Éditer">✏️</button><button class="btn bp2 xs" onclick="openMoveGrp('${u.id}','${grp?grp.name:''}')" title="Changer groupe">🔄</button>`:'';
  return`<div class="ur">
    <div class="ur-av">👤</div>
    <div class="ur-inf">
      <div class="ur-n">${u.login}</div>
      <div class="ur-m">${grp?`<span style="display:inline-block;width:8px;height:8px;border-radius:50%;background:${grp.color};margin-right:4px;vertical-align:middle;"></span>${grp.name} · `:''}Badges ${u.badges_count||0}/${u.badge_quota}${miniBar(u.badges_count||0,u.badge_quota)} MCT ${u.mct_used||0}${u.must_change_pwd?` <span class="chip c-warn" style="margin-left:4px;">1ère cnx</span>`:''}</div>
    </div>
    ${st}
    <div class="ur-acts">
      ${admBtns}
      <button class="btn bg xs" onclick="openResetPwd('${u.id}','${u.login}')" title="Reset MDP">🔑</button>
      <button class="btn bw xs" onclick="toggleBlock('${u.id}',${u.is_active},false)">${u.is_active?'⛔':'✓'}</button>
      <button class="btn bd xs" onclick="confirmAction('Supprimer ${u.login} ?','Soft delete — validé par superadmin.',()=>delUser('${u.id}',false))">🗑</button>
    </div>
  </div>`;
}

// ─── ACTIONS : ADMINS ─────────────────────────────────────
async function createAdmin(){
  const login=document.getElementById('ma-login').value.trim();
  const pwd=document.getElementById('ma-pwd').value;
  const glim=parseInt(document.getElementById('ma-glim').value)||0;
  const ttl=parseInt(document.getElementById('ma-ttl').value)||24;
  if(!login||!pwd){toast('Remplissez tous les champs','err');return;}
  try{
    await api('POST','/api/admins',{login,password:pwd,group_limit:glim,jwt_ttl_hours:ttl});
    toast(`Admin ${login} créé`,'ok');closeMo('mo-new-admin');
    document.getElementById('ma-login').value='';document.getElementById('ma-pwd').value='';
    await loadSaAdmins();
  }catch(e){toast(e.message,'err');}
}

async function toggleBlock(uid,isActive,isAdmin){
  try{
    const path=isAdmin?`/api/admins/${uid}`:`/api/users/${uid}`;
    await api('PATCH',path,{is_active:isActive?0:1});
    toast(isActive?'Compte bloqué':'Compte débloqué','ok');
    isAdmin?await loadSaAdmins():S.role==='superadmin'?await loadSaUsers():await loadAdmUsers();
  }catch(e){toast(e.message,'err');}
}

async function delAdmin(uid){
  try{await api('DELETE',`/api/admins/${uid}`);toast('Admin supprimé','ok');closeMo('mo-confirm');await loadSaAdmins();}
  catch(e){toast(e.message,'err');}
}

// ─── ACTIONS : USERS ──────────────────────────────────────
async function createUser(){
  const login=document.getElementById('mu-login').value.trim();
  const pwd=document.getElementById('mu-pwd').value;
  const grpId=document.getElementById('mu-grp-sel').value||undefined;
  const quota=parseInt(document.getElementById('mu-quota').value)||5;
  const ttl=parseInt(document.getElementById('mu-ttl').value)||24;
  const adminSel=document.getElementById('mu-admin-sel');
  const adminId=adminSel&&!adminSel.closest('.hidden')&&adminSel.value?adminSel.value:undefined;
  if(!login||!pwd){toast('Remplissez tous les champs','err');return;}
  try{
    await api('POST','/api/users',{login,password:pwd,group_id:grpId,badge_quota:quota,jwt_ttl_hours:ttl,admin_id:adminId});
    toast(`Utilisateur ${login} créé`,'ok');closeMo('mo-new-user');
    document.getElementById('mu-login').value='';document.getElementById('mu-pwd').value='';
    S.role==='superadmin'?await loadSaUsers():await loadAdmUsers();
  }catch(e){toast(e.message,'err');}
}

async function openMoNewUser(){
  try{
    const groups=await api('GET','/api/groups');S.groups=groups;
    const grpSel=document.getElementById('mu-grp-sel');
    if(grpSel) grpSel.innerHTML='<option value="">— Aucun groupe —</option>'+groups.map(g=>`<option value="${g.id}">${g.name}</option>`).join('');
    if(S.role==='superadmin'){
      const admins=await api('GET','/api/admins');S.admins=admins;
      const adminWrap=document.getElementById('mu-admin-wrap');
      const adminSel=document.getElementById('mu-admin-sel');
      if(adminSel) adminSel.innerHTML='<option value="">— Aucun —</option>'+admins.map(a=>`<option value="${a.id}">${a.login}</option>`).join('');
      if(adminWrap) adminWrap.classList.remove('hidden');
    }
  }catch(e){}
  openMo('mo-new-user');
}

function openEditUser(uid,quota,ttl,isActive){
  document.getElementById('eu-id').value=uid;
  document.getElementById('eu-quota').value=quota;
  document.getElementById('eu-ttl').value=ttl;
  document.getElementById('eu-active').value=isActive;
  openMo('mo-edit-user');
}

function openEditAdmin(uid,login,ttl){
  // Réutiliser la modale mo-edit-user en l'adaptant dynamiquement
  document.getElementById('eu-id').value=uid;
  document.getElementById('eu-sub').textContent=login;
  document.getElementById('eu-quota').closest('.fgi').classList.add('hidden');
  document.getElementById('eu-ttl').value=ttl;
  document.getElementById('eu-active').value=1;
  // Changer le bouton sauvegarder
  document.getElementById('eu-save-btn').onclick=()=>saveEditAdmin(uid);
  openMo('mo-edit-user');
}

async function saveEditAdmin(uid){
  try{
    await api('PATCH',`/api/admins/${uid}`,{
      jwt_ttl_hours:parseInt(document.getElementById('eu-ttl').value),
      is_active:parseInt(document.getElementById('eu-active').value),
    });
    toast('Admin mis à jour','ok');
    closeMo('mo-edit-user');
    document.getElementById('eu-quota').closest('.fgi').classList.remove('hidden');
    await loadSaAdmins();
  }catch(e){toast(e.message,'err');}
}

async function saveEditUser(){
  const uid=document.getElementById('eu-id').value;
  try{
    await api('PATCH',`/api/users/${uid}`,{badge_quota:parseInt(document.getElementById('eu-quota').value),jwt_ttl_hours:parseInt(document.getElementById('eu-ttl').value),is_active:parseInt(document.getElementById('eu-active').value)});
    toast('Utilisateur mis à jour','ok');closeMo('mo-edit-user');
    S.role==='superadmin'?await loadSaUsers():await loadAdmUsers();
  }catch(e){toast(e.message,'err');}
}

function openMoveGrp(uid,fromName){
  document.getElementById('mg-uid').value=uid;
  document.getElementById('mg-from').value=fromName||'Sans groupe';
  const sel=document.getElementById('mg-to-sel');
  sel.innerHTML=S.groups.filter(g=>g.name!==fromName).map(g=>`<option value="${g.id}">${g.name}</option>`).join('');
  openMo('mo-move-grp');
}

async function moveUserGroup(){
  const uid=document.getElementById('mg-uid').value;
  const gid=document.getElementById('mg-to-sel').value;
  try{
    await api('POST',`/api/users/${uid}/move-group`,{user_id:uid,group_id:gid,notify:true});
    toast('Utilisateur déplacé — superadmin notifié','ok');closeMo('mo-move-grp');
    await loadAdmUsers();
  }catch(e){toast(e.message,'err');}
}

function openResetPwd(uid,login){
  document.getElementById('rp-uid').value=uid;
  document.getElementById('rp-login').value=login;
  document.getElementById('rp-pwd').value='';
  document.getElementById('rp-wipe').checked=false;
  openMo('mo-reset-pwd');
}

async function doResetPwd(){
  const uid=document.getElementById('rp-uid').value;
  const pwd=document.getElementById('rp-pwd').value;
  const wipe=document.getElementById('rp-wipe').checked;
  try{
    await api('POST',`/api/users/${uid}/reset-password`,{password:pwd,wipe_badges:wipe});
    toast('Mot de passe réinitialisé','ok');closeMo('mo-reset-pwd');
  }catch(e){toast(e.message,'err');}
}

async function delUser(uid,definitive=false){
  try{
    await api('DELETE',`/api/users/${uid}`);
    toast(definitive?'Utilisateur supprimé':'Suppression en attente de validation','ok');
    closeMo('mo-confirm');
    S.role==='superadmin'?await loadSaUsers():await loadAdmUsers();
  }catch(e){toast(e.message,'err');}
}

async function restoreUser(uid){
  try{await api('POST',`/api/users/${uid}/restore`);toast('Compte restauré','ok');await loadSaUsers();}
  catch(e){toast(e.message,'err');}
}

// ─── ACTIONS : GROUPES ────────────────────────────────────
async function openMoNewGrp(){
  if(S.role==='superadmin'){
    try{
      const admins=await api('GET','/api/admins');S.admins=admins;
      let wrap=document.getElementById('ng-admin-wrap');
      if(!wrap){
        const mo=document.querySelector('#mo-new-grp .mo');
        const div=document.createElement('div');div.className='fgi';div.id='ng-admin-wrap';
        div.innerHTML='<label class="fl">Admin responsable <span style="color:var(--red)">*</span></label><select class="sel" id="ng-admin-sel"></select><div class="fnote" id="ng-admin-note"></div>';
        mo.insertBefore(div,mo.querySelector('.mo-acts'));
      }
      const sel=document.getElementById('ng-admin-sel');
      const note=document.getElementById('ng-admin-note');
      if(!admins.length){
        sel.innerHTML='<option value="">Aucun admin disponible</option>';
        sel.disabled=true;
        if(note) note.innerHTML='<span style="color:var(--red);">Créez d\'abord un admin avant de créer un groupe.</span>';
      } else {
        sel.disabled=false;
        sel.innerHTML=admins.map(a=>`<option value="${a.id}">${a.login}</option>`).join('');
        if(note) note.textContent='Le groupe sera sous la responsabilité de cet admin.';
      }
    }catch(e){}
  }
  // Reset mode édition
  S._editGroupId=null;
  const acts=document.querySelector('#mo-new-grp .mo-acts');
  acts.innerHTML='<button class="btn bg" onclick="closeMo(\'mo-new-grp\')">Annuler</button><button class="btn bp" onclick="createGroup()">Créer</button>';
  document.getElementById('ng-name').value='';
  openMo('mo-new-grp');
}

async function createGroup(){
  const name=document.getElementById('ng-name').value.trim();
  if(!name){toast('Nom requis','err');return;}
  const adminSel=document.getElementById('ng-admin-sel');
  const admin_id=adminSel&&adminSel.value&&adminSel.value!==''?adminSel.value:undefined;
  // Règle : superadmin doit sélectionner un admin si des admins existent
  if(S.role==='superadmin'&&(S.admins||[]).length>0&&!admin_id){
    toast('Sélectionnez un admin responsable pour ce groupe','err');return;
  }
  try{
    await api('POST','/api/groups',{name,color:S.color,admin_id});
    toast(`Groupe "${name}" créé`,'ok');closeMo('mo-new-grp');
    document.getElementById('ng-name').value='';
    S.role==='superadmin'?await loadSaUsers():await loadAdmGrps();
  }catch(e){toast(e.message,'err');}
}

function openEditGrp(id,name,color){
  S._editGroupId=id;S.color=color;
  document.getElementById('ng-name').value=name;
  document.querySelectorAll('#ng-colors div').forEach(d=>{d.style.border=d.style.background===color||d.onclick?.toString().includes(color)?'2px solid var(--cyan)':'none';});
  // Masquer champ admin si présent
  document.getElementById('ng-admin-wrap')?.classList.add('hidden');
  // Changer bouton
  const acts=document.querySelector('#mo-new-grp .mo-acts');
  acts.innerHTML='<button class="btn bg" onclick="closeMo(\'mo-new-grp\');S._editGroupId=null;">Annuler</button><button class="btn bp" onclick="saveEditGrp()">Sauvegarder</button>';
  openMo('mo-new-grp');
}

async function saveEditGrp(){
  const id=S._editGroupId;const name=document.getElementById('ng-name').value.trim();
  if(!name||!id)return;
  try{
    await api('PATCH',`/api/groups/${id}`,{name,color:S.color});
    toast('Groupe mis à jour','ok');closeMo('mo-new-grp');S._editGroupId=null;
    await loadAdmGrps();
  }catch(e){toast(e.message,'err');}
}

async function delGroup(gid){
  try{await api('DELETE',`/api/groups/${gid}`);toast('Groupe supprimé','ok');closeMo('mo-confirm');await loadAdmGrps();}
  catch(e){toast(e.message,'err');}
}

// ─── ACTIONS : BADGES ─────────────────────────────────────
async function createBadge(){
  const name=document.getElementById('nb-name').value.trim();
  const uid=document.getElementById('nb-uid').value.trim();
  const err=validateUID(uid);
  if(!name||uid.length!==8){toast('Nom et UID (8 car.) requis','err');return;}
  if(err){toast(err,'err');return;}
  try{
    await api('POST','/api/badges',{name,uid,icon:S.icons.nb});
    toast(`Badge "${name}" créé`,'ok');closeMo('mo-new-badge');
    document.getElementById('nb-name').value='';document.getElementById('nb-uid').value='';
    await loadUsrBadges();
  }catch(e){toast(e.message,'err');}
}

function openEditBadge(id,name,uid,icon){
  document.getElementById('eb-id').value=id;
  document.getElementById('eb-name').value=name;
  document.getElementById('eb-uid').value=uid;
  S.icons.eb=icon;
  document.querySelectorAll('#eb-icons span').forEach(s=>{s.style.borderColor=s.dataset.icon===icon?'var(--cyan)':'var(--border)';s.style.background=s.dataset.icon===icon?'rgba(0,200,240,.08)':'';});
  openMo('mo-edit-badge');
}

async function saveEditBadge(){
  const id=document.getElementById('eb-id').value;
  const name=document.getElementById('eb-name').value.trim();
  const uid=document.getElementById('eb-uid').value.trim();
  if(uid){const err=validateUID(uid);if(err){toast(err,'err');return;}}
  try{
    await api('PATCH',`/api/badges/${id}`,{name,uid:uid||undefined,icon:S.icons.eb});
    toast('Badge mis à jour','ok');closeMo('mo-edit-badge');await loadUsrBadges();
  }catch(e){toast(e.message,'err');}
}

async function delBadge(bid){
  try{await api('DELETE',`/api/badges/${bid}`);toast('Badge supprimé','ok');closeMo('mo-confirm');await loadUsrBadges();}
  catch(e){toast(e.message,'err');}
}

// ─── ENCODE MCT ───────────────────────────────────────────
async function encodeBadge(bid,name,uid){
  const ov=document.getElementById('enc-ov');const tx=document.getElementById('enc-tx');
  ov.classList.remove('hidden');
  const steps=['Connexion serveur...','Wine → vigik_loader_cli...','Signature DSA...','Conversion MFD → MCT...','Téléchargement...'];
  let si=0;const iv=setInterval(()=>{tx.textContent=steps[si%steps.length];si++;},700);
  try{
    const resp=await api('POST',`/api/badges/${bid}/encode`,null,true);
    clearInterval(iv);ov.classList.add('hidden');
    if(!resp.ok){const d=await resp.json();throw new Error(d.detail||'Erreur encodage');}
    const blob=await resp.blob();
    const url=URL.createObjectURL(blob);
    const a=document.createElement('a');a.href=url;a.download=`badge_${name.replace(/\s+/g,'_')}_${uid}.mct`;
    document.body.appendChild(a);a.click();document.body.removeChild(a);URL.revokeObjectURL(url);
    toast('✓ MCT téléchargé','ok');await loadUsrBadges();
  }catch(e){clearInterval(iv);ov.classList.add('hidden');toast(e.message,'err');}
}

// ─── STOCK BADGES ─────────────────────────────────────────
async function createStockBadge(){
  const name=document.getElementById('sb-name').value.trim();
  const uid=document.getElementById('sb-uid').value.trim();
  const err=validateUID(uid);
  if(!name||uid.length!==8){toast('Nom et UID (8 car.) requis','err');return;}
  if(err){toast(err,'err');return;}
  try{
    await api('POST','/api/stock',{name,uid,icon:S.icons.sb});
    toast(`Badge "${name}" référencé`,'ok');closeMo('mo-stock-badge');
    document.getElementById('sb-name').value='';document.getElementById('sb-uid').value='';
    await loadSaBadges();
  }catch(e){toast(e.message,'err');}
}

async function openDispatchBadge(bid,label){
  // Admin dispatche un badge stock reçu vers l'un de ses users
  document.getElementById('at-bid').value=bid;
  document.getElementById('at-badge-name').value=label;
  const sel=document.getElementById('at-sel');
  try{
    const users=await api('GET','/api/users');
    sel.innerHTML=users.map(u=>`<option value="${u.id}">👤 ${u.login}</option>`).join('');
  }catch(e){sel.innerHTML='<option>Erreur chargement</option>';}
  openMo('mo-attrib');
}

async function openAttrib(bid,label){
  document.getElementById('at-bid').value=bid;
  document.getElementById('at-badge-name').value=label;
  const sel=document.getElementById('at-sel');
  try{
    const[admins,users]=await Promise.all([api('GET','/api/admins'),api('GET','/api/users')]);
    sel.innerHTML=admins.map(a=>`<option value="${a.id}">🛡️ ${a.login} (admin)</option>`).join('')+users.map(u=>`<option value="${u.id}">👤 ${u.login} (user)</option>`).join('');
  }catch(e){sel.innerHTML='<option>Erreur chargement</option>';}
  openMo('mo-attrib');
}

async function doAttrib(){
  const bid=document.getElementById('at-bid').value;
  const toId=document.getElementById('at-sel').value;
  try{
    await api('POST',`/api/stock/${bid}/attribute`,{badge_id:bid,attributed_to:toId});
    toast('Badge attribué — notification envoyée','ok');closeMo('mo-attrib');await loadSaBadges();
  }catch(e){toast(e.message,'err');}
}

async function reclaimStock(bid){
  try{await api('POST',`/api/stock/${bid}/reclaim`);toast('Badge remis en stock','ok');await loadSaBadges();}
  catch(e){toast(e.message,'err');}
}

async function delStock(bid){
  try{await api('DELETE',`/api/stock/${bid}`);toast('Badge supprimé','ok');closeMo('mo-confirm');await loadSaBadges();}
  catch(e){toast(e.message,'err');}
}

// ─── REQUESTS ─────────────────────────────────────────────
function openRequest(type,title){
  document.getElementById('req-type').value=type;
  document.getElementById('req-title').textContent=title;
  document.getElementById('req-motif').value='';
  openMo('mo-request');
}

async function submitRequest(){
  const type=document.getElementById('req-type').value;
  const motif=document.getElementById('req-motif').value.trim();
  try{
    await api('POST','/api/requests',{type,motif});
    toast('Demande envoyée','ok');closeMo('mo-request');
    type==='mct_rallonge'?await loadUsrMct():await loadUsrBadges();
  }catch(e){toast(e.message,'err');}
}

// ─── MODAL HELPERS ────────────────────────────────────────
function openMo(id){document.getElementById(id).classList.remove('hidden');}
function closeMo(id){document.getElementById(id).classList.add('hidden');}
function closeMoOv(e,id){if(e.target===document.getElementById(id))closeMo(id);}

function confirmAction(title,msg,fn){
  document.getElementById('confirm-title').textContent=title;
  document.getElementById('confirm-msg').textContent=msg;
  document.getElementById('confirm-btn').onclick=fn;
  openMo('mo-confirm');
}

function selIcon(el,prefix){
  document.querySelectorAll(`#${prefix}-icons span`).forEach(s=>{s.style.borderColor='var(--border)';s.style.background='';});
  el.style.borderColor='var(--cyan)';el.style.background='rgba(0,200,240,.08)';
  S.icons[prefix]=el.dataset.icon;
}

function selColor(el,color){
  document.querySelectorAll('#ng-colors div').forEach(d=>d.style.border='none');
  el.style.border='2px solid var(--cyan)';S.color=color;
}

// ─── INIT ─────────────────────────────────────────────────
document.addEventListener('DOMContentLoaded',()=>{
  // Relier la cloche au panel notifs
  const bell=document.getElementById('tb-bell');
  if(bell) bell.onclick=openNotifPanel;
  // Enter sur le champ mot de passe login
  const lp=document.getElementById('lp');
  if(lp) lp.onkeydown=(e)=>{if(e.key==='Enter')doLogin();};
});

console.log('[Badge Manager v2.2] Chargé ✓');
