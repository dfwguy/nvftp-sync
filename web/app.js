const API = '/api/v1';

const demo = {
  overview: { commits: 1842, pipelines: 27, merge_requests: 8, forks: 14, artifacts: 386 },
  pipelines: [
    {id:67914627,name:'nvftp-sync / main',ref:'main · 9f2c15a',stage:'security_scan',status:'success',progress:100,duration:'2m 14s',actor:'GitLab CI'},
    {id:67914911,name:'rack-status-pythoncm',ref:'import/nscale-tx-16k',stage:'integration_test',status:'running',progress:67,duration:'4m 31s',actor:'NVIS operator'},
    {id:67914782,name:'validation-toolkit',ref:'feat/h100-health',stage:'artifact_publish',status:'success',progress:100,duration:'6m 08s',actor:'GitLab CI'},
    {id:67914203,name:'nvis-deployment',ref:'hotfix/manifest-v2',stage:'policy_gate',status:'failed',progress:82,duration:'1m 42s',actor:'CI Service'}
  ],
  activity: [
    {who:'OP',name:'NVIS operator',action:'opened merge request',target:'rack-status-pythoncm !41',time:'2 min'},
    {who:'CI',name:'GitLab CI',action:'published artifact',target:'nvftp-sync 2026.09.15',time:'14 min'},
    {who:'RV',name:'Authorized reviewer',action:'approved import',target:'H100 validation bundle',time:'31 min'},
    {who:'CI',name:'Policy bot',action:'blocked pipeline',target:'manifest-v2 · missing attestation',time:'46 min'},
    {who:'OP',name:'NVIS operator',action:'forked repository',target:'nvis-deployment',time:'1 hr'}
  ],
  repos: [
    {name:'rack-status-pythoncm',description:'Rack status validation and reporting for PythonCM.',branch:'main',commits:312,forks:4,mrs:2,status:'healthy',lang:'Python'},
    {name:'nvftp-sync',description:'Secure bidirectional artifact transport and intake.',branch:'main',commits:68,forks:2,mrs:1,status:'healthy',lang:'Python'},
    {name:'validation-toolkit',description:'Reusable validation agents and cluster checks.',branch:'main',commits:441,forks:3,mrs:3,status:'healthy',lang:'Shell'},
    {name:'nvis-deployment',description:'OVA deployment workflows, manifests and release specs.',branch:'stable',commits:229,forks:2,mrs:1,status:'warning',lang:'YAML'},
    {name:'gpu-firmware-audit',description:'Firmware inventory and compliance evidence.',branch:'main',commits:173,forks:1,mrs:0,status:'healthy',lang:'Python'},
    {name:'cluster-log-replay',description:'Captured validation sessions and deterministic replay.',branch:'main',commits:619,forks:2,mrs:1,status:'healthy',lang:'Go'}
  ],
  approvals: [
    {title:'Import NscaleTX-16K rack status bundle',detail:'211 files · 17,024 additions · secret scan passed',risk:'Medium',owner:'NVIS operator',age:'12m'},
    {title:'Rotate GitLab group access token',detail:'Scopes: api, read_repository, write_repository · expires in 3d',risk:'High',owner:'Platform Security',age:'2h'}
  ],
  audit: [
    ['2026-09-15 11:42:08','NVIS operator','merge_request.create','rack-status-pythoncm !41','allowed'],
    ['2026-09-15 11:40:51','nvis-worker','artifact.verify','NscaleTX-16K.tar.gz','allowed'],
    ['2026-09-15 11:39:26','nvis-worker','nvftp.download','sha256:a1c7…93e2','allowed'],
    ['2026-09-15 11:38:13','Slack Bot','intake.request','nvidia-space/shared/NscaleTX-16K','allowed'],
    ['2026-09-15 10:54:03','Policy Bot','pipeline.publish','manifest-v2','denied'],
    ['2026-09-15 10:27:44','Security admin','credential.rotate','nvftp/production','allowed']
  ],
  services: [
    {name:'Control Plane API',key:'nvis-api.service',status:'healthy',value:'42 ms',label:'p95 latency',usage:22},
    {name:'Slack Command Agent',key:'nvis-slack.service',status:'healthy',value:'0.3s',label:'last heartbeat',usage:14},
    {name:'Pipeline Worker',key:'nvis-worker.service',status:'healthy',value:'3 / 8',label:'active workers',usage:38},
    {name:'Audit Store',key:'nvis-audit.service',status:'healthy',value:'18.4 GB',label:'disk used of 120 GB',usage:15}
  ]
};

let state = {data: demo, mode:'connecting', route:'overview', session:null};
const workspace = document.querySelector('#workspace');
const banner = document.querySelector('#dataBanner');
const loginDialog = document.querySelector('#loginDialog');
const accountMenuButton = document.querySelector('#accountMenuButton');
const accountMenu = document.querySelector('#accountMenu');

const esc = value => String(value == null ? '' : value).replace(/[&<>'"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;',"'":'&#39;','"':'&quot;'}[c]));
const bytes = value => {const n=Number(value)||0;const units=['B','KB','MB','GB','TB'];let i=0,v=n;while(v>=1024&&i<units.length-1){v/=1024;i++}return `${v.toFixed(i>1?1:0)} ${units[i]}`};
const percent = (used,total) => total?Math.round(Number(used)*100/Number(total)):0;
const status = value => `<span class="badge ${esc(value)}"><i class="status-dot ${esc(value)}"></i>${esc(value)}</span>`;
const head = (eyebrow,title,copy,actions='') => `<header class="page-head"><div><p class="eyebrow">${eyebrow}</p><h1>${title}</h1><p>${copy}</p></div><div class="button-row">${actions}</div></header>`;
const btn = (label,action,kind='') => `<button class="btn ${kind}" data-action="${action}">${label}</button>`;

async function loadData(){
  banner.className='data-banner';
  banner.innerHTML='<span>CONNECTING</span> Checking the local control-plane API…';
  const paths=['overview','pipelines','activity','repositories','approvals','audit','health'];
  try{
    const sessionResponse=await fetch(`${API}/auth/session`,{headers:{Accept:'application/json'}});
    if(sessionResponse.status===401){showLogin();return}
    if(!sessionResponse.ok)throw new Error(`session: HTTP ${sessionResponse.status}`);
    state.session=await sessionResponse.json();
    const responses=await Promise.all(paths.map(async path=>{
      const response=await fetch(`${API}/${path}`,{headers:{Accept:'application/json'},signal:AbortSignal.timeout(20000)});
      if(!response.ok) throw new Error(`${path}: HTTP ${response.status}`);
      return [path,await response.json()];
    }));
    const live=Object.fromEntries(responses);
    live.repos=live.repositories;
    live.services=live.health.services||[];
    state.data={...demo,...live}; state.mode='live';
    const navCounts=document.querySelectorAll('.nav-count');
    if(navCounts[0])navCounts[0].textContent=String(live.overview.pipelines);
    if(navCounts[1])navCounts[1].textContent=String(live.approvals.length);
    const sessionName=state.session.display_name||state.session.user;
    document.querySelector('.avatar').textContent=String(sessionName).split(/\s+/).map(part=>part[0]).join('').slice(0,2).toUpperCase();
    document.querySelector('#accountName').textContent=sessionName;
    document.querySelector('#accountEmail').textContent=state.session.user;
    document.querySelector('#accountRole').textContent=state.session.role;
    document.querySelector('.mini-health strong').textContent='Hub API operational';
    document.querySelector('.mini-health small').textContent=`${live.services.filter(item=>item.status==='healthy').length} of ${live.services.length} integrations healthy`;
    banner.className='data-banner live';
    banner.innerHTML=`<span>LIVE DATA</span> Connected as ${esc(sessionName)} · ${esc(state.session.role)}. <button id="hideBanner">Dismiss</button>`;
    document.querySelector('#hideBanner').onclick=()=>banner.classList.add('hidden');
  }catch(error){
    state.data=demo; state.mode='demo';
    banner.className='data-banner';
    banner.innerHTML='<span>DEMO DATA</span> Live API is unavailable. Actions are simulated and no credentials are stored. <button id="retryApi">Retry connection</button>';
    document.querySelector('#retryApi').onclick=loadData;
  }
  renderRoute();
}

function showLogin(){
  state.mode='locked';
  state.session=null;
  closeAccountMenu();
  banner.className='data-banner';
  banner.innerHTML='<span>AUTH REQUIRED</span> Sign in to connect to the protected control plane.';
  if(!loginDialog.open)loginDialog.showModal();
  setTimeout(()=>document.querySelector('#loginPassword').focus(),0);
}

document.querySelector('#loginForm').addEventListener('submit',async event=>{
  event.preventDefault();
  const error=document.querySelector('#loginError');
  error.textContent='Authenticating…';
  try{
    const response=await fetch(`${API}/auth/login`,{
      method:'POST',headers:{'Content-Type':'application/json'},
      body:JSON.stringify({username:document.querySelector('#loginUser').value,password:document.querySelector('#loginPassword').value})
    });
    if(!response.ok)throw new Error('Invalid username or password');
    state.session=await response.json();
    document.querySelector('#loginPassword').value='';
    loginDialog.close();
    await loadData();
  }catch(reason){error.textContent=reason.message||'Sign-in failed'}
});

function overview(){
  const k=state.data.overview;
  const live=state.mode==='live';
  const welcome=state.session?.display_name?`Welcome, ${esc(state.session.display_name)}.`:'Welcome to NVIS-OVA.';
  return head('Control plane',welcome,'Here is what is moving through your delivery system.',`${btn('⇧ New intake','intake')} ${btn('⌁ Run pipeline','run','primary')}`)+
  `<section class="kpi-grid" aria-label="Key metrics">
    ${[['Commits',k.commits,live?'Across managed repositories':'+124 this week'],['Active pipelines',k.pipelines,live?'Running or pending now':'3 running now'],['Merge requests',k.merge_requests,live?'Open in GitLab':'2 need review'],['Managed forks',k.forks,live?'Reported by GitLab':'All synchronized'],['Artifacts',k.artifacts,live?'Recorded intake jobs':'29.6 GB indexed']].map(([a,b,c],i)=>`<article class="card kpi"><div class="kpi-label">${a}</div><div class="kpi-value">${b}</div><div class="delta ${i===2?'warn':''}">${c}</div></article>`).join('')}
  </section>
  <section class="grid two">
    <article class="card panel"><div class="panel-head"><h2>Pipeline activity</h2><a href="#pipelines">View all pipelines →</a></div>${pipelineRows(state.data.pipelines.slice(0,4))}</article>
    <article class="card panel"><div class="panel-head"><h2>Live activity</h2><button class="text-button">● Streaming</button></div>${activityRows(state.data.activity)}</article>
    <article class="card panel"><div class="panel-head"><h2>Delivery path</h2><span class="sub">Live control-plane totals</span></div><div class="flow"><div class="flow-node"><strong>NVFTP intake</strong><small>${esc(k.artifacts)} jobs recorded</small></div><div class="flow-arrow">→</div><div class="flow-node"><strong>Policy &amp; validation</strong><small>${esc(k.pipelines)} pipelines active</small></div><div class="flow-arrow">→</div><div class="flow-node"><strong>GitLab delivery</strong><small>${esc(k.merge_requests)} merge requests open</small></div></div></article>
    <article class="card panel"><div class="panel-head"><h2>Evidence posture</h2><span class="badge success">live</span></div><div class="sub">${esc(state.data.audit.length)} audit events loaded · ${esc(k.commits)} commits indexed</div><div class="spark" aria-label="Repository activity index">${state.data.repos.slice(0,14).map(r=>`<i style="height:${Math.max(8,Math.min(100,Number(r.commits)||8))}%"></i>`).join('')}</div></article>
  </section>`;
}

function pipelineRows(items){return `<div class="pipeline-list">${items.map(p=>`<div class="pipeline-row"><div class="pipeline-icon">${p.status==='success'?'✓':p.status==='failed'?'!':'↻'}</div><div class="pipeline-name"><strong>${esc(p.name)}</strong><span class="sub mono">#${esc(p.id)} · ${esc(p.ref)}</span></div><span class="sub">${esc(p.stage)}</span>${status(p.status)}<span class="sub mono">${esc(p.duration)}</span><div><div class="progress"><span style="width:${Number(p.progress)||0}%"></span></div><span class="sub">${esc(p.progress)}%</span></div></div>`).join('')}</div>`}
function activityRows(items){return items.length?`<div class="activity-list">${items.map(a=>`<div class="activity"><div class="person">${esc(a.who)}</div><p><strong>${esc(a.name)}</strong> ${esc(a.action)}<br><span class="sub">${esc(a.target)}</span></p><time>${esc(a.time)}</time></div>`).join('')}</div>`:`<div class="empty-state"><div class="empty-icon">≡</div><h2>No intake activity yet</h2><p>The first approved Slack or portal intake will appear here.</p></div>`}

function pipelines(){return head('Delivery','Pipelines','Observe validations, policy gates, and delivery in real time.',`${btn('Filter','filter')} ${btn('▶ Run pipeline','run','primary')}`)+`<article class="card panel"><div class="panel-head"><h2>All pipelines</h2><span class="sub">Auto-refreshing every 15 seconds</span></div>${pipelineRows(state.data.pipelines)}</article><section class="grid equal" style="margin-top:14px"><article class="card panel"><div class="panel-head"><h2>Runner capacity</h2><span class="badge success">healthy</span></div><div class="kpi-value">3 / 8</div><div class="meter"><i style="width:38%"></i></div><p class="sub">5 executors ready · median queue time 4s</p></article><article class="card panel"><div class="panel-head"><h2>Success rate</h2><span class="sub">Past 30 days</span></div><div class="kpi-value">96.4%</div><div class="spark">${[80,100,82,100,100,94,100,91,100,100,88,100].map(n=>`<i style="height:${n}%"></i>`).join('')}</div></article></section>`}

function intake(){return head('Secure transport','Artifact intake','Stage a signed bundle from your workstation or an authorized NVFTP path.',btn('View intake contract','contract'))+`<section class="grid two"><article class="card panel"><div id="dropzone" class="intake-zone" tabindex="0" role="button" aria-label="Upload artifact bundle"><input type="file" id="fileInput" multiple><div class="upload-icon">⇧</div><h2>Drop a release bundle here</h2><p>.tar.gz, .bundle, .zip, manifest.json · maximum 2 GB</p>${btn('Choose files','choose','primary')}<div class="intake-meta"><span>✓ Private staging</span><span>✓ Immutable audit record</span><span>✓ Policy scan before publish</span></div></div></article><article class="card panel"><div class="panel-head"><h2>Import from NVFTP</h2><span class="badge success">connected</span></div><form id="intakeForm" class="form-grid"><div class="field full"><label for="nvpath">NVFTP path</label><input id="nvpath" required value="/nvidia-space/shared/NscaleTX-16K" spellcheck="false"><span class="hint">Must be inside an authorized workspace prefix</span></div><div class="field"><label for="destination">Destination project</label><select id="destination"><option>rack-status-pythoncm</option><option>nvftp-sync</option><option>validation-toolkit</option></select></div><div class="field"><label for="strategy">Integration strategy</label><select id="strategy"><option>Open merge request</option><option>Create/update fork</option><option>Stage only</option></select></div><div class="field full"><label for="notes">Release notes / intent</label><textarea id="notes" rows="3" placeholder="What changed and why?"></textarea></div><div class="field full"><button class="btn primary" type="submit">Prepare Slack approval command →</button></div></form></article></section><article class="card panel" style="margin-top:14px"><div class="panel-head"><h2>Recent intakes</h2><a href="#audit">Open audit trail →</a></div>${activityRows(state.data.activity.slice(0,3))}</article>`}

function repositories(){return head('GitLab inventory','Repositories','Live view of canonical projects, managed forks, commits, and open work.',`${btn('Sync all','sync')} ${btn('+ Create project','create-project','primary')}`)+`<section class="repo-grid">${state.data.repos.map(r=>`<article class="card repo-card"><div class="repo-top"><div class="repo-icon">⑂</div>${status(r.status)}</div><h3>${esc(r.name)}</h3><p>${esc(r.description)}</p><span class="branch">⑂ ${esc(r.branch)} · ${esc(r.lang)}</span><div class="repo-stats"><span>● ${r.commits} commits</span><span>⑂ ${r.forks} forks</span><span>⌁ ${r.mrs} MRs</span></div></article>`).join('')}</section>`}

function lineage(){return head('Provenance','Artifact lineage','Trace every artifact from source bytes to review and release.',btn('Verify checksums','verify','primary'))+`<article class="card panel table-wrap"><div class="panel-head"><h2>NscaleTX-16K · release 20260914</h2><span class="badge success">chain verified</span></div><div class="lineage-canvas"><div class="lineage-node"><small>SOURCE</small><strong>NVFTP bundle</strong><div class="checksum">a1c7b029…93e2</div></div><div class="lineage-node"><small>STAGED</small><strong>Secure workspace</strong><div class="checksum">manifest v2 · scanned</div></div><div class="lineage-node"><small>VERSIONED</small><strong>Integration commit</strong><div class="checksum">cf68dfb2b1b2…</div></div><div class="lineage-node"><small>REVIEW</small><strong>Merge request !41</strong><div class="checksum">2 approvals pending</div></div></div></article><article class="card panel" style="margin-top:14px"><div class="panel-head"><h2>Evidence</h2><span class="sub">Immutable, append-only records</span></div><div class="table-wrap"><table class="data-table"><thead><tr><th>Control</th><th>Result</th><th>Attestation</th><th>Timestamp</th></tr></thead><tbody><tr><td>Archive safety</td><td>${status('success')}</td><td class="mono">policy/archive@v3</td><td>11:39:42</td></tr><tr><td>Secret scan</td><td>${status('success')}</td><td class="mono">gitleaks/8.21</td><td>11:39:47</td></tr><tr><td>Export classification</td><td>${status('warning')}</td><td>Human attestation required</td><td>pending</td></tr></tbody></table></div></article>`}

function approvals(){return head('Policy gates','Approvals','Human decisions that stand between staged work and canonical branches.',btn('Approval policy','policy'))+`<section class="grid two"><article class="card panel"><div class="panel-head"><h2>Waiting on you</h2><span class="badge warning">${state.data.approvals.length} pending</span></div><div class="approval-list">${state.data.approvals.length?state.data.approvals.map((a,i)=>`<div class="approval"><div><h3>${esc(a.title)}</h3><p>${esc(a.detail)}</p><span class="sub">Owner: ${esc(a.owner)} · ${esc(a.age)} · Risk: ${esc(a.risk)}</span></div><div class="approval-actions">${btn('Inspect',`inspect-${i}`)}</div></div>`).join(''):'<div class="empty-state"><div class="empty-icon">✓</div><h2>No pending approvals</h2><p>Approval actions are signed in Slack, where requester separation is enforced.</p></div>'}</div></article><article class="card panel"><div class="panel-head"><h2>Guardrails</h2><span class="badge success">enforced</span></div><div class="service-list"><div class="activity"><span class="status-dot healthy"></span><p><strong>No self-approval</strong><br><span class="sub">Authors cannot approve their own imports or branch operations</span></p></div><div class="activity"><span class="status-dot healthy"></span><p><strong>Protected main branch</strong><br><span class="sub">The agent never force-pushes, deletes, approves, or merges</span></p></div><div class="activity"><span class="status-dot healthy"></span><p><strong>Admin-only credential rotation</strong><br><span class="sub">Write-only replacement plus tamper-evident audit event</span></p></div></div></article></section>`}

function audit(){return head('Governance','Audit log','Tamper-evident record of every human and agent action.',`${btn('Filters','filter')} ${btn('Export evidence','export','primary')}`)+`<article class="card panel table-wrap"><table class="data-table"><thead><tr><th>Timestamp</th><th>Principal</th><th>Action</th><th>Resource</th><th>Decision</th></tr></thead><tbody>${state.data.audit.map(r=>`<tr><td class="mono">${esc(r[0])}</td><td>${esc(r[1])}</td><td class="mono">${esc(r[2])}</td><td>${esc(r[3])}</td><td>${status(r[4]==='allowed'?'success':'failed')}</td></tr>`).join('')}</tbody></table></article>`}

function access(){const user=state.session?.user||'Signed-in user';const displayName=state.session?.display_name||user;const role=state.session?.role||'viewer';const initials=displayName.split(/\s+/).map(part=>part[0]).join('').slice(0,2).toUpperCase();return head('Identity & access','RBAC','Least-privilege roles for people, bots, and automation.')+`<article class="card panel table-wrap"><div class="panel-head"><h2>Permission matrix</h2><span class="sub">Enforced by the local control plane</span></div><div class="role-matrix"><div class="head">Capability</div><div class="head">Viewer</div><div class="head">Operator</div><div class="head">Approver</div><div class="head">Admin</div>${[['View pipeline','✓','✓','✓','✓'],['Stage artifact','—','✓','✓','✓'],['Create feature branch / MR','—','✓','✓','✓'],['Approve release','—','—','✓','✓'],['Rotate credentials','—','—','—','✓'],['Change RBAC','—','—','—','✓']].flatMap(row=>row.map((v,i)=>`<div class="${i&&v==='✓'?'check':''}">${v}</div>`)).join('')}</div></article><article class="card panel" style="margin-top:14px"><div class="panel-head"><h2>Current session</h2><span class="badge success">authenticated</span></div><div class="table-wrap"><table class="data-table"><tbody><tr><td><div class="person">${esc(initials)}</div></td><td><strong>${esc(displayName)}</strong><br><span class="sub">${esc(user)}</span></td><td>${esc(role)}</td><td>${status('success')}</td><td>Now</td></tr><tr><td><div class="person">SB</div></td><td><strong>NVIS Slack Bot</strong><br><span class="sub">service principal</span></td><td>Operator</td><td>${status(state.data.health?.integrations?.slack?.status==='configured'?'success':'warning')}</td><td>${esc(state.data.health?.integrations?.slack?.status||'not configured')}</td></tr></tbody></table></div></article>`}

const integrationData=[['GL','GitLab Master','gitlab-master.nvidia.com','Live · read-only status API','gitlab'],['NF','NVFTP','transfer.nvftp.nvidia.com · SFTP','Dedicated key · expires Mar 13, 2027','nvftp'],['#','Slack Agent','Socket Mode','Awaiting workspace credentials','slack'],['VA','Local credential store','Mode-0600 files','Write-only API · 3 managed credentials','vault']];
function integrations(){return head('Connections','Integrations','Manage connectivity and rotate credentials without exposing secret values.',btn('Test all connections','test-all','primary'))+`<section class="integration-grid">${integrationData.map(i=>`<article class="card integration"><div class="integration-head"><div class="integration-logo">${i[0]}</div><div><h3>${i[1]}</h3><p>${i[2]}</p></div><span style="margin-left:auto">${status(i[4]==='slack'?'warning':'success')}</span></div><div class="status-line"><span>${i[3]}</span><span>Live health view available</span></div><div class="integration-actions">${btn('Test',`test-${i[4]}`)} ${btn('Rotate credential',`rotate-${i[4]}`)}</div></article>`).join('')}</section><article class="card panel" style="margin-top:14px"><div class="panel-head"><h2>Secret handling</h2><span class="badge success">OS protected</span></div><p class="sub">Credentials are write-only in the portal. Existing values never return to the browser. Rotation atomically replaces a local mode-0600 file and appends a hash-chained audit event. Production deployment should place this directory on encrypted storage.</p></article>`}

function health(){const n=state.data.health?.node||{};const disk=n.disk||{},memory=n.memory||{};const diskPct=percent(disk.used,disk.total),memoryPct=percent(memory.used,memory.total);return head('Staging node','Node & service health','Local resources, agents, audit, and external dependencies.',btn('Refresh health','refresh','primary'))+`<section class="health-grid">${state.data.services.map(s=>`<article class="card service-card"><header><div><h3>${esc(s.name)}</h3><span class="sub mono">${esc(s.key)}</span></div>${status(s.status)}</header><div class="metric">${esc(s.value)}</div><span class="sub">${esc(s.label)}</span><div class="meter" style="margin-top:12px"><i style="width:${Number(s.usage)||0}%"></i></div></article>`).join('')}</section><section class="grid equal" style="margin-top:14px"><article class="card panel"><div class="panel-head"><h2>Node resources</h2><span class="sub mono">${esc(n.hostname||'local staging VM')}</span></div><div class="table-wrap"><table class="data-table"><tbody><tr><td>CPU capacity</td><td>${esc(n.cpu_count||'—')} cores</td><td>${status('success')}</td></tr><tr><td>Memory</td><td>${bytes(memory.used)} / ${bytes(memory.total)}</td><td><div class="meter"><i style="width:${memoryPct}%"></i></div></td></tr><tr><td>Data disk</td><td>${bytes(disk.used)} / ${bytes(disk.total)}</td><td><div class="meter"><i style="width:${diskPct}%"></i></div></td></tr><tr><td>Load average</td><td>${esc((n.load_average||[]).join(' / '))}</td><td>${status('success')}</td></tr></tbody></table></div></article><article class="card panel"><div class="panel-head"><h2>Recent audit events</h2><a href="#audit">Open full chain →</a></div>${activityRows(state.data.activity.slice(0,5))}</article></section>`}

const views={overview,pipelines,intake,repositories,lineage,approvals,audit,access,integrations,health};
function renderRoute(){
  const raw=location.hash.slice(1)||'overview'; state.route=views[raw]?raw:'overview';
  document.querySelectorAll('[data-route]').forEach(a=>a.classList.toggle('active',a.dataset.route===state.route));
  const routeLabel=document.querySelector(`[data-route="${state.route}"] span:nth-child(2)`); document.querySelector('#pageCrumb').textContent=routeLabel?routeLabel.textContent:'Overview';
  workspace.innerHTML=views[state.route](); workspace.focus({preventScroll:true}); bindView();
  document.querySelector('#sidebar').classList.remove('open'); document.querySelector('#scrim').classList.remove('open');
}

function bindView(){
  workspace.querySelectorAll('[data-action]').forEach(el=>el.addEventListener('click',()=>action(el.dataset.action)));
  const dz=document.querySelector('#dropzone'), input=document.querySelector('#fileInput');
  if(dz){['dragenter','dragover'].forEach(e=>dz.addEventListener(e,x=>{x.preventDefault();dz.classList.add('dragover')}));['dragleave','drop'].forEach(e=>dz.addEventListener(e,x=>{x.preventDefault();dz.classList.remove('dragover');if(e==='drop')stageFiles(x.dataTransfer.files)}));dz.addEventListener('click',e=>{if(!e.target.closest('[data-action]'))input.click()});dz.addEventListener('keydown',e=>{if(e.key==='Enter'||e.key===' ')input.click()});input.onchange=()=>stageFiles(input.files)}
  const intakeForm=document.querySelector('#intakeForm'); if(intakeForm) intakeForm.addEventListener('submit',e=>{e.preventDefault();const path=document.querySelector('#nvpath').value;const target=document.querySelector('#destination').value;showModal('Approval command ready',`Send this to the Slack bot:<br><br><code>/nvis import nvftp=${esc(path)} artifact=&lt;bundle-basename&gt; target=nvis-ova/${esc(target)}</code><br><br>The bot will inspect and stage it, then request a separate approval before any GitLab write.`,`Close`)});
}
async function stageFiles(files){
  if(!files.length)return;
  if(state.mode!=='live'){toast('Live sign-in required','Files were not uploaded.');return}
  for(const file of files){
    try{
      const response=await fetch(`${API}/uploads?filename=${encodeURIComponent(file.name)}`,{method:'POST',headers:{'Content-Type':'application/octet-stream','X-CSRF-Token':state.session.csrf_token},body:file});
      if(!response.ok)throw new Error(`HTTP ${response.status}`);
      const result=await response.json();toast('Artifact staged',`${result.filename} · ${Number(result.bytes).toLocaleString()} bytes · ${result.upload_id}`);
    }catch(error){toast('Upload rejected',`${file.name}: ${error.message}`)}
  }
}
function action(name){
  if(name==='intake'){location.hash='intake';return} if(name==='choose'){const fileInput=document.querySelector('#fileInput');if(fileInput)fileInput.click();return}
  if(name==='refresh'){loadData();return}
  if(name.startsWith('rotate-')){const key={gitlab:'gitlab_token',slack:'slack_bot_token'}[name.slice(7)];if(!key){toast('Guided rotation required','NVFTP keys and the local vault use a dedicated key ceremony; no secret was changed.');return}showModal(`Rotate ${name.slice(7).toUpperCase()} credential`,'The current credential is never displayed. The replacement is atomically written to its mode-0600 local file.',`Rotate credential`,true,async value=>{const response=await fetch(`${API}/credentials/${key}`,{method:'POST',headers:{'Content-Type':'application/json','X-CSRF-Token':state.session.csrf_token},body:JSON.stringify({value})});if(!response.ok)throw new Error(`rotation rejected: HTTP ${response.status}`)});return}
  if(name.startsWith('approve-')){showModal('Confirm approval','Your signed decision will be appended to the audit chain. This approves the gate; it does not merge automatically.','Sign approval');return}
  if(name==='create-project'){showModal('Create managed project','Create a new canonical project or managed fork in the NVIS-OVA namespace.','Create project',true);return}
  toast('Action queued',`${name.replaceAll('-',' ')} is simulated while the API is unavailable.`)
}
function showModal(title,copy,label,field=false,onConfirm=null){const d=document.querySelector('#modal'),c=document.querySelector('#modalContent');c.innerHTML=`<form method="dialog" class="modal-body"><h2>${title}</h2><p>${copy}</p>${field?`<div class="field"><label for="secureInput">New credential</label><input id="secureInput" type="password" autocomplete="new-password" placeholder="Value is write-only" required><span class="hint">Stored in a mode-0600 file; never returned by the API or written to logs.</span></div>`:''}<div class="modal-actions"><button class="btn" value="cancel">Cancel</button><button class="btn primary" value="confirm">${label}</button></div></form>`;d.showModal();d.addEventListener('close',async()=>{if(d.returnValue!=='confirm')return;try{if(onConfirm)await onConfirm(document.querySelector('#secureInput')?.value||'');toast('Request accepted','The operation was recorded in the tamper-evident audit ledger.')}catch(error){toast('Request rejected',error.message)}},{once:true})}
function toast(title,copy){const box=document.createElement('div');box.className='toast success';box.innerHTML=`<span class="status-dot healthy"></span><div><strong>${esc(title)}</strong><span class="sub">${esc(copy)}</span></div>`;document.querySelector('#toasts').append(box);setTimeout(()=>box.remove(),5000)}

const commandItems=[['⇧','Import from NVFTP','Open secure artifact intake','intake'],['▶','Run a pipeline','Choose project and ref','pipelines'],['＋','Create a managed fork','Configure upstream synchronization','repositories'],['⌁','Review pending approvals','2 gates waiting','approvals'],['♡','Check integration health','All systems operational','health'],['≡','Search audit evidence','386 retained events','audit']];
function openCommand(){const d=document.querySelector('#commandDialog');d.showModal();document.querySelector('#commandInput').value='';renderCommands('');setTimeout(()=>document.querySelector('#commandInput').focus(),0)}
function renderCommands(q){const list=commandItems.filter(x=>x.join(' ').toLowerCase().includes(q.toLowerCase()));document.querySelector('#commandResults').innerHTML=`<div class="command-group">Commands &amp; destinations</div>${list.map((x,i)=>`<div class="command-item ${i===0?'selected':''}" data-command="${x[3]}"><span>${x[0]}</span><strong>${x[1]}</strong><small>${x[2]}</small></div>`).join('')||`<div class="empty-state"><div class="empty-icon">⌕</div><h2>No matching commands</h2><p>Try a project name, pipeline ID, or “import”.</p></div>`}`;document.querySelectorAll('[data-command]').forEach(x=>x.onclick=()=>{document.querySelector('#commandDialog').close();location.hash=x.dataset.command})}
document.querySelector('#commandTrigger').onclick=openCommand;document.querySelector('#commandInput').oninput=e=>renderCommands(e.target.value);document.addEventListener('keydown',e=>{if((e.metaKey||e.ctrlKey)&&e.key.toLowerCase()==='k'){e.preventDefault();openCommand()}});
document.querySelector('#themeToggle').onclick=()=>{const root=document.documentElement;root.dataset.theme=root.dataset.theme==='dark'?'light':'dark';localStorage.setItem('nvis-theme',root.dataset.theme)};
function closeAccountMenu({restoreFocus=false}={}){accountMenu.hidden=true;accountMenuButton.setAttribute('aria-expanded','false');if(restoreFocus)accountMenuButton.focus()}
function toggleAccountMenu(){const opening=accountMenu.hidden;if(opening&&!state.session)return;accountMenu.hidden=!opening;accountMenuButton.setAttribute('aria-expanded',String(opening));if(opening)setTimeout(()=>accountMenu.querySelector('[role="menuitem"]')?.focus(),0)}
async function logout(){
  if(!state.session)return;
  const response=await fetch(`${API}/auth/logout`,{method:'POST',headers:{'X-CSRF-Token':state.session.csrf_token}});
  if(!response.ok)throw new Error(`Sign out failed: HTTP ${response.status}`);
  state.session=null;
  closeAccountMenu();
  document.querySelector('#loginForm').reset();
  showLogin();
}
accountMenuButton.onclick=event=>{event.stopPropagation();toggleAccountMenu()};
accountMenu.addEventListener('click',async event=>{
  const item=event.target.closest('[data-account-action]');if(!item)return;
  const accountAction=item.dataset.accountAction;
  if(accountAction==='profile'){location.hash='access';closeAccountMenu();return}
  if(accountAction==='theme'){document.querySelector('#themeToggle').click();closeAccountMenu({restoreFocus:true});return}
  if(accountAction==='logout'){item.disabled=true;try{await logout()}catch(error){item.disabled=false;toast('Sign out failed',error.message)}}
});
document.addEventListener('click',event=>{if(!accountMenu.hidden&&!event.target.closest('.account-control'))closeAccountMenu()});
document.addEventListener('keydown',event=>{if(event.key==='Escape'&&!accountMenu.hidden){event.preventDefault();closeAccountMenu({restoreFocus:true})}});
const saved=localStorage.getItem('nvis-theme');if(saved)document.documentElement.dataset.theme=saved;
document.querySelector('#menuToggle').onclick=()=>{const s=document.querySelector('#sidebar');s.classList.toggle('open');document.querySelector('#scrim').classList.toggle('open');document.querySelector('#menuToggle').setAttribute('aria-expanded',s.classList.contains('open'))};document.querySelector('#scrim').onclick=()=>document.querySelector('#menuToggle').click();
window.addEventListener('hashchange',renderRoute);
loadData();
