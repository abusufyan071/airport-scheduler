let S=null,auto=null;
const $=id=>document.getElementById(id);
async function post(u,b){await fetch(u,{method:'POST',headers:{'Content-Type':'application/json'},body:b?JSON.stringify(b):'{}'});load()}
async function tick(){await post('/api/tick')}
function toggleAuto(){if(auto){clearInterval(auto);auto=null}else auto=setInterval(tick,1500);$('autoBtn').textContent='Auto: '+(auto?'ON':'OFF')}
document.querySelectorAll('#nav a').forEach(a=>a.onclick=()=>{
  document.querySelectorAll('#nav a,.tab').forEach(e=>e.classList.remove('on'));a.classList.add('on');$(a.dataset.t).classList.add('on')});
async function addAircraft(){
  const r=await fetch('/api/aircraft',{method:'POST',headers:{'Content-Type':'application/json'},
    body:JSON.stringify({callsign:$('f-call').value,type:$('f-type').value,operation:$('f-op').value,fuel:$('f-fuel').value})});
  const d=await r.json();$('f-msg').textContent=d.error||'';if(r.ok){$('f-call').value='';
  document.querySelector('[data-t=queue]').click()}load()}
async function del(id){await fetch('/api/aircraft/'+id,{method:'DELETE'});load()}
const tag=s=>`<span class="tag ${s}">${s}</span>`;
function table(h,rows){return rows.length?`<table><tr>${h.map(x=>`<th>${x}</th>`).join('')}</tr>${rows.map(r=>`<tr>${r.map(c=>`<td>${c}</td>`).join('')}</tr>`).join('')}</table>`:'<p class="muted">Nothing here yet.</p>'}
const box=r=>`<div class="box ${r.holder?'busy':'free'}"><b>${r.name}</b><br>${r.holder?'🔴 '+r.holder:'🟢 Available'}</div>`;
const waiting=()=>S.aircraft.filter(a=>a.status=='WAITING').sort((a,b)=>b.priority-a.priority||a.arrival_tick-b.arrival_tick||a.id-b.id);
function render(){
  $('clock').textContent='Tick '+S.clock;$('age').textContent=S.config.aging_every;
  if(!$('f-type').options.length)$('f-type').innerHTML=Object.entries(S.types).map(([k,v])=>`<option value="${k}">${k} (priority ${v})</option>`).join('');
  const R=S.resources,W=waiting(),dl=S.deadlock;
  $('d-runways').innerHTML=R.filter(r=>r.kind=='Runway').map(box).join('');
  $('d-res').innerHTML=R.filter(r=>r.kind!='Runway').map(box).join('');
  const dtxt=dl.safe?`<div class="safe">🟢 SAFE</div>`:`<div class="unsafe">🔴 DEADLOCK: ${dl.cycle.join(' → ')}</div>`;
  $('d-dead').innerHTML=dtxt+`<p class="muted">Resources checked: ${dl.resources_checked} · Aircraft checked: ${dl.aircraft_checked}</p>`;
  $('d-wait').innerHTML=table(['Aircraft','Type','Op','Priority'],W.map(a=>[a.callsign,a.type,a.operation,a.priority]));
  $('q-all').innerHTML=table(['ID','Callsign','Type','Operation','Priority','Fuel','Arrived','Wait','Status','Resources',''],
    S.aircraft.map(a=>[a.id,a.callsign,a.type,a.operation,a.priority,a.fuel+'%',a.arrival_tick,a.wait,tag(a.status),
    a.status=='RUNNING'?`${a.runway}, ${a.gate}, ${a.crew}`:'-',`<button class="x" onclick="del(${a.id})">Delete</button>`]));
  $('r-all').innerHTML=table(['Resource','Kind','Status','Held by'],R.map(r=>[r.name,r.kind,r.holder?'🔴 Busy':'🟢 Available',r.holder||'-']));
  $('s-queue').innerHTML=table(['Rank','Aircraft','Priority','Base','Waiting (ticks)'],W.map((a,i)=>[i+1,a.callsign,a.priority,a.base_priority,a.wait]));
  $('s-log').innerHTML=S.history.map(h=>`<div>[t${h.tick}] <b>${h.event}</b> ${h.detail}</div>`).join('')||'<p class="muted">No events yet.</p>';
  $('k-live').innerHTML=dtxt+`<p>Waiting aircraft hold <b>no</b> resources (all-or-nothing), and resources are always requested in order Runway → Gate → Crew, so a circular wait cannot form.</p>`+
    `<p class="muted">Wait-for graph: ${JSON.stringify(dl.waiting_graph)}</p>`;
  const st=S.stats;
  $('st-sum').innerHTML=table(['Metric','Value'],[['Total aircraft',st.total],['Waiting',st.by_status.WAITING],['Running',st.by_status.RUNNING],
    ['Completed',st.by_status.COMPLETED],['Average wait (ticks)',st.avg_wait],['Max wait (ticks)',st.max_wait]]);
  const mx=Math.max(1,...Object.values(st.usage));
  $('st-use').innerHTML=Object.entries(st.usage).map(([k,v])=>`${k}: ${v}<div class="bar"><i style="width:${v/mx*100}%"></i></div>`).join('');
}
async function runDemo(){
  const d=await (await fetch('/api/deadlock/demo')).json();
  $('k-demo').innerHTML=`<ol class="demo">${d.steps.map(s=>`<li>${s}</li>`).join('')}</ol>
  <p class="unsafe">⚠ Naive cycle detected: ${d.naive_cycle.join(' → ')}</p><p class="safe">✔ Circular wait prevented: A101 → RUNNING, A102 → WAITING, resources safely retained.</p>`}
async function load(){S=await (await fetch('/api/state')).json();render()}
load();
