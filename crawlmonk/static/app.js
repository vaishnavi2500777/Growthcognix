const $ = s => document.querySelector(s);
const app = $('#app');
const esc = s => String(s ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const safeUrl = u => /^https?:\/\//i.test(u || '') ? esc(u) : '#';
let token = localStorage.getItem('cm_token');
let timer = null;

async function api(path, opts = {}) {
  const r = await fetch(path, {...opts, headers: {'content-type': 'application/json', ...(token ? {authorization: 'Bearer ' + token} : {}), ...(opts.headers || {})}});
  if (r.status === 401 && path !== '/auth/login') { logout(); throw new Error('Session expired, please log in'); }
  const ct = r.headers.get('content-type') || '';
  const d = ct.includes('json') ? await r.json() : await r.blob();
  if (!r.ok) throw new Error((d && d.error) || ('HTTP ' + r.status));
  return d;
}
function logout() { token = null; localStorage.removeItem('cm_token'); route(); }
$('#logout').onclick = logout;

function authView() {
  $('#nav').hidden = true;
  app.innerHTML = `<div class="auth card"><h1>CrawlMonk</h1><p class="sub">Find the right business leads city-wise across India. Scrape, crawl and extract any website.</p>
  <div class="tabs"><button id="tl" class="on">Log in</button><button id="ts">Sign up</button></div>
  <form id="af"><label>Email</label><input id="em" type="email" required autocomplete="email">
  <label style="margin-top:10px">Password</label><input id="pw" type="password" required minlength="8" autocomplete="current-password">
  <div class="row" style="margin-top:14px"><button id="ab">Log in</button><span id="ae" class="err"></span></div></form></div>`;
  let mode = 'login';
  $('#tl').onclick = () => { mode = 'login'; $('#tl').className = 'on'; $('#ts').className = ''; $('#ab').textContent = 'Log in'; };
  $('#ts').onclick = () => { mode = 'signup'; $('#ts').className = 'on'; $('#tl').className = ''; $('#ab').textContent = 'Create account'; };
  $('#af').onsubmit = async e => {
    e.preventDefault(); $('#ae').textContent = '';
    try { const d = await api('/auth/' + mode, {method: 'POST', body: JSON.stringify({email: $('#em').value, password: $('#pw').value})});
      token = d.token; localStorage.setItem('cm_token', token); location.hash = '#leads'; route();
    } catch (x) { $('#ae').textContent = x.message; }
  };
}

// ---------------- Lead Finder ----------------
function leadsView(jobId) {
  app.innerHTML = `<h1>Lead Finder</h1><p class="sub">Real businesses from OpenStreetMap and the open web, verified on their own websites, scored for fit.</p>
  <form class="card" id="lf"><div class="grid">
   <div><label>Cities (one per line, optional ", State")</label><textarea id="cities" required placeholder="Bengaluru, Karnataka&#10;Vadodara, Gujarat">Bengaluru, Karnataka</textarea></div>
   <div><label>Business category / keywords</label><input id="cat" required placeholder="clinic · restaurant · chemical manufacturer · PTFE" value="clinic">
     <label style="margin-top:10px">Goal</label><select id="goal"><option value="agency">Sell marketing/digital services (score weak online presence)</option><option value="buyer">Find buyers/partners (score relevance)</option></select></div>
   <div><label>What you sell (optional, for AI fit reasons)</label><input id="offer" placeholder="e.g. Instagram + Google Business management">
     <label style="margin-top:10px">Max leads per city</label><input id="max" type="number" min="5" max="300" value="60"></div>
   <div><label>Sources</label><label class="muted" style="font-weight:400"><input type="checkbox" id="s_osm" checked style="width:auto"> OpenStreetMap</label>
     <label class="muted" style="font-weight:400"><input type="checkbox" id="s_web" checked style="width:auto"> Web search (verified on site)</label>
     <label class="muted" style="font-weight:400"><input type="checkbox" id="enr" checked style="width:auto"> Crawl websites for emails/phones/socials</label></div>
  </div><div class="row" style="margin-top:12px"><button id="go">Find leads</button><span id="le" class="err"></span></div></form>
  <div id="res"></div>`;
  $('#lf').onsubmit = async e => {
    e.preventDefault(); $('#le').textContent = '';
    const cities = $('#cities').value.split('\n').map(l => l.trim()).filter(Boolean).map(l => { const [c, ...s] = l.split(','); return {city: c.trim(), state: s.join(',').trim() || null}; });
    const sources = [$('#s_osm').checked && 'osm', $('#s_web').checked && 'web'].filter(Boolean);
    try { $('#go').disabled = true;
      const d = await api('/v1/leads', {method: 'POST', body: JSON.stringify({cities, category: $('#cat').value, goal: $('#goal').value, offer: $('#offer').value || null, max_leads: +$('#max').value, sources, enrich: $('#enr').checked})});
      location.hash = '#leads/' + d.id;
    } catch (x) { $('#le').textContent = x.message; } finally { $('#go').disabled = false; }
  };
  if (jobId) pollLeads(jobId);
}

async function pollLeads(id) {
  clearTimeout(timer);
  let d; try { d = await api('/v1/leads/' + id); } catch (x) { $('#res').innerHTML = `<p class="err">${esc(x.message)}</p>`; return; }
  const p = d.progress || {}, running = ['queued', 'running'].includes(d.status);
  const cities = (p.cities || []).map(c => `<span class="pill">${esc(c.city)}: ${c.error ? 'error – ' + esc(c.error) : esc(c.leads) + ' leads' + (c.osm_error ? ' (OSM: ' + esc(c.osm_error) + ')' : '')}</span>`).join(' ');
  let html = `<div class="card"><div class="row" style="justify-content:space-between"><div><b>${esc(d.params.category)}</b> in ${esc(d.params.cities.map(c => c.city).join(', '))} · <span class="${d.status === 'failed' ? 'err' : 'ok'}">${esc(d.status)}</span> · ${esc(p.stage || '')}</div>
   <div class="row">${running ? '<button class="ghost" id="cx">Cancel</button>' : ''}<button id="csv" ${d.leads.length ? '' : 'disabled'}>Download CSV (${d.leads.length})</button></div></div>
   ${running ? '<div class="bar" style="margin-top:10px"><i style="width:' + Math.min(95, 10 + (p.cities || []).length / d.params.cities.length * 85) + '%"></i></div>' : ''}
   <div style="margin-top:8px">${cities}</div>${d.error ? `<p class="err">${esc(d.error)}</p>` : ''}</div>`;
  if (d.leads.length) {
    html += `<div class="tablewrap"><table><thead><tr><th>Score</th><th>Business</th><th>City</th><th>Contact</th><th>Online presence</th><th>Why</th></tr></thead><tbody>` +
      d.leads.map(l => { const s = l.signals || {};
        const soc = Object.entries(l.socials || {}).map(([k, v]) => `<a class="pill" href="${safeUrl(v)}" target="_blank" rel="noopener">${esc(k)}</a>`).join('');
        const phones = [...new Set([l.phone, ...(l.phones || [])].filter(Boolean))].slice(0, 3);
        return `<tr><td><span class="score">${l.score}</span></td>
        <td><b>${esc(l.name)}</b><div class="hint">${esc(l.category)}</div><div class="hint">${esc(l.address)}</div></td><td>${esc(l.city)}</td>
        <td>${phones.map(p => `<div><a href="tel:${esc(p)}">${esc(p)}</a></div>`).join('')}${(l.emails || []).slice(0, 2).map(m => `<div><a href="mailto:${esc(m)}">${esc(m)}</a></div>`).join('')}</td>
        <td>${l.website ? `<a href="${safeUrl(l.website)}" target="_blank" rel="noopener">${esc(l.website.replace(/^https?:\/\//, '').slice(0, 40))}</a>` : '<span class="muted">no website</span>'}
          <div>${soc}</div><div class="hint">${s.website_ok === false ? 'site down/blocked · ' : ''}${s.https === false ? 'no https · ' : ''}${s.mobile_meta === false ? 'not mobile · ' : ''}${s.copyright_year ? '© ' + s.copyright_year : ''}</div></td>
        <td><div class="hint">${esc(l.reason)}</div>${l.ai_reason ? `<div><b>AI:</b> ${esc(l.ai_reason)}</div>` : ''}<a class="hint" href="${safeUrl(l.source_ref)}" target="_blank" rel="noopener">source: ${esc(l.source)}</a></td></tr>`; }).join('') + `</tbody></table></div>`;
  }
  $('#res').innerHTML = html;
  if ($('#cx')) $('#cx').onclick = () => api('/v1/leads/' + id, {method: 'DELETE'}).then(() => pollLeads(id));
  $('#csv').onclick = async () => { const b = await api('/v1/leads/' + id + '/csv'); const a = document.createElement('a'); a.href = URL.createObjectURL(b); a.download = 'crawlmonk-leads.csv'; a.click(); };
  if (running) timer = setTimeout(() => pollLeads(id), 3000);
}

// ---------------- Playground ----------------
function playView() {
  app.innerHTML = `<h1>Scrape &amp; Crawl playground</h1><p class="sub">Same engine as the API. Results are live from the web.</p>
  <div class="tabs" id="pt">${['scrape', 'crawl', 'map', 'search', 'extract', 'agent', 'parse'].map((t, i) => `<button data-t="${t}" class="${i ? '' : 'on'}">${t}</button>`).join('')}</div>
  <form class="card" id="pf"></form><div id="pr"></div>`;
  let tab = 'scrape';
  const forms = {
    scrape: `<label>URL</label><input id="u" required value="https://www.python.org/about/"><div class="grid" style="margin-top:10px">
      <div><label>Formats</label>${['markdown', 'html', 'rawHtml', 'links', 'images', 'contacts', 'screenshot', 'summary', 'changeTracking'].map(f => `<label class="muted" style="font-weight:400;display:inline-block;margin-right:8px"><input type="checkbox" class="fm" value="${f}" ${f === 'markdown' ? 'checked' : ''} style="width:auto"> ${f}</label>`).join('')}</div>
      <div><label>Options</label><label class="muted" style="font-weight:400"><input type="checkbox" id="om" checked style="width:auto"> only main content</label><label class="muted" style="font-weight:400"><input type="checkbox" id="mob" style="width:auto"> mobile</label>
      <label>Engine</label><select id="eng"><option>auto</option><option>static</option><option>browser</option></select></div>
      <div><label>JSON extraction prompt (optional, uses Gemini)</label><input id="jp" placeholder="e.g. company name, products, contact email"></div></div>`,
    crawl: `<label>Start URL</label><input id="u" required value="https://www.python.org/about/"><div class="grid" style="margin-top:10px"><div><label>Page limit</label><input id="lim" type="number" value="10" max="200"></div><div><label>Max depth</label><input id="dep" type="number" value="2"></div><div><label>Include paths (regex, comma)</label><input id="inc"></div><div><label>Exclude paths (regex, comma)</label><input id="exc"></div></div>`,
    map: `<label>Website</label><input id="u" required value="https://www.python.org"><label style="margin-top:10px">Search filter (optional)</label><input id="q">`,
    search: `<label>Query</label><input id="q" required value="PTFE gasket manufacturers Vadodara"><div class="row" style="margin-top:10px"><label class="muted" style="font-weight:400"><input type="checkbox" id="news" style="width:auto"> include news</label><label class="muted" style="font-weight:400"><input type="checkbox" id="scr" style="width:auto"> scrape results</label></div>`,
    extract: `<label>URLs (one per line; end with /* to include the site)</label><textarea id="us">https://www.python.org/psf/</textarea><label>Prompt</label><input id="q" required value="What is this organisation, what does it do and how can it be contacted?">`,
    agent: `<label>What do you want to find?</label><textarea id="q" required>Find 5 PTFE product manufacturers in Gujarat with their websites and cities.</textarea>`,
    parse: `<label>File (PDF, DOCX, XLSX, HTML, TXT – max 15 MB)</label><input id="file" type="file" required>`,
  };
  const draw = () => { $('#pf').innerHTML = forms[tab] + `<div class="row" style="margin-top:12px"><button id="run">Run ${tab}</button><span id="pe" class="err"></span></div>`; };
  draw();
  $('#pt').onclick = e => { if (!e.target.dataset.t) return; tab = e.target.dataset.t; [...$('#pt').children].forEach(b => b.className = b.dataset.t === tab ? 'on' : ''); draw(); $('#pr').innerHTML = ''; };
  $('#pf').onsubmit = async e => {
    e.preventDefault(); $('#pe').textContent = ''; $('#run').disabled = true; $('#pr').innerHTML = '<p class="muted">Working…</p>';
    const list = s => (s || '').split(',').map(x => x.trim()).filter(Boolean);
    try {
      let d;
      if (tab === 'scrape') {
        const formats = [...document.querySelectorAll('.fm:checked')].map(x => x.value);
        if ($('#jp').value) formats.push({type: 'json', prompt: $('#jp').value});
        d = await api('/v1/scrape', {method: 'POST', body: JSON.stringify({url: $('#u').value, formats, onlyMainContent: $('#om').checked, mobile: $('#mob').checked, engine: $('#eng').value})});
        showScrape(d.data);
      } else if (tab === 'map') { d = await api('/v1/map', {method: 'POST', body: JSON.stringify({url: $('#u').value, search: $('#q').value || null})}); out(`${d.links.length} URLs\n\n` + d.links.map(l => l.url + (l.title ? '  — ' + l.title : '')).join('\n'));
      } else if (tab === 'search') { d = await api('/v1/search', {method: 'POST', body: JSON.stringify({query: $('#q').value, limit: 8, sources: $('#news').checked ? ['web', 'news'] : ['web'], scrapeOptions: $('#scr').checked ? {formats: ['markdown']} : null})}); out(JSON.stringify(d, null, 2));
      } else if (tab === 'crawl') { d = await api('/v1/crawl', {method: 'POST', body: JSON.stringify({url: $('#u').value, limit: +$('#lim').value, maxDiscoveryDepth: +$('#dep').value, includePaths: list($('#inc').value), excludePaths: list($('#exc').value)})}); pollJob('/v1/crawl/' + d.id);
      } else if (tab === 'extract') { d = await api('/v1/extract', {method: 'POST', body: JSON.stringify({urls: $('#us').value.split('\n').map(x => x.trim()).filter(Boolean), prompt: $('#q').value})}); pollJob('/v1/extract/' + d.id);
      } else if (tab === 'agent') { d = await api('/v1/agent', {method: 'POST', body: JSON.stringify({prompt: $('#q').value})}); pollJob('/v1/agent/' + d.id);
      } else if (tab === 'parse') { const fd = new FormData(); fd.append('file', $('#file').files[0]);
        const r = await fetch('/v1/parse', {method: 'POST', body: fd, headers: {authorization: 'Bearer ' + token}}); d = await r.json(); if (!r.ok) throw new Error(d.error); out(d.data.markdown); }
    } catch (x) { $('#pe').textContent = x.message; $('#pr').innerHTML = ''; } finally { $('#run').disabled = false; }
  };
}
function out(s) { $('#pr').innerHTML = `<pre>${esc(s)}</pre>`; }
function showScrape(d) {
  const m = d.metadata || {};
  let h = `<div class="card"><b>${esc(m.title || m.url)}</b> <span class="hint">HTTP ${esc(m.statusCode)} · ${esc(m.engine)} · ${esc(m.elapsedMs)} ms</span>${d.warning ? `<p class="err">${esc(d.warning)}</p>` : ''}`;
  if (d.screenshot) h += `<p><a href="${safeUrl(d.screenshot)}" target="_blank"><img src="${safeUrl(d.screenshot)}" style="max-width:100%;border:1px solid #ddd;border-radius:6px"></a></p>`;
  if (d.summary) h += `<h2>Summary</h2><p>${esc(d.summary)}</p>`;
  h += '</div>';
  const rest = {...d}; delete rest.screenshot; delete rest.summary;
  $('#pr').innerHTML = h + `<pre>${esc(rest.markdown ?? '')}</pre><pre>${esc(JSON.stringify({...rest, markdown: undefined}, null, 2))}</pre>`;
}
async function pollJob(path) {
  clearTimeout(timer);
  const d = await api(path);
  $('#pr').innerHTML = `<div class="card">Status: <b>${esc(d.jobStatus)}</b> · ${esc(d.completed ?? '')} done ${d.progress && d.progress.stage ? '· ' + esc(d.progress.stage) : ''} ${d.error ? `<p class="err">${esc(d.error)}</p>` : ''}</div>`
    + `<pre>${esc(JSON.stringify(d.data, null, 2))}</pre>` + (d.sources ? `<pre>Sources:\n${esc(d.sources.join('\n'))}</pre>` : '');
  if (['queued', 'running'].includes(d.jobStatus)) timer = setTimeout(() => pollJob(path), 3000);
}

// ---------------- Jobs ----------------
async function jobsView() {
  app.innerHTML = '<h1>Jobs</h1><p class="sub">Your recent lead searches, crawls and extractions.</p><div id="jl" class="muted">Loading…</div>';
  const d = await api('/v1/jobs');
  const link = j => j.kind === 'leads' ? `#leads/${j.id}` : null;
  $('#jl').innerHTML = d.jobs.length ? `<div class="tablewrap"><table><thead><tr><th>When</th><th>Type</th><th>What</th><th>Status</th><th>Result</th></tr></thead><tbody>` + d.jobs.map(j => {
    const p = j.params, pr = j.progress || {};
    const what = j.kind === 'leads' ? `${p.category} · ${p.cities.map(c => c.city).join(', ')}` : (p.url || (p.urls || []).join(', ') || p.prompt || '');
    const res = j.kind === 'leads' ? `${pr.leads ?? 0} leads` : (pr.completed != null ? `${pr.completed} pages` : '');
    return `<tr><td>${esc(new Date(j.created_at).toLocaleString())}</td><td>${esc(j.kind)}</td><td>${link(j) ? `<a href="${link(j)}">${esc(what)}</a>` : esc(what).slice(0, 120)}</td><td>${esc(j.status)}${j.error ? `<div class="err hint">${esc(j.error)}</div>` : ''}</td><td>${esc(res)}</td></tr>`; }).join('') + '</tbody></table></div>' : '<p>No jobs yet.</p>';
}

// ---------------- Monitors ----------------
async function monitorsView() {
  app.innerHTML = `<h1>Monitors</h1><p class="sub">Re-scrape a page on a schedule and record what changed (diff). Note: the free server sleeps when idle, so checks run while it is awake.</p>
  <form class="card row" id="mf"><input id="mu" required placeholder="https://competitor.com/pricing" style="flex:2"><select id="mi" style="flex:1"><option value="60">every hour</option><option value="360">every 6 hours</option><option value="1440">daily</option></select><button>Add monitor</button><span id="me" class="err"></span></form><div id="ml"></div>`;
  $('#mf').onsubmit = async e => { e.preventDefault(); try { await api('/v1/monitor', {method: 'POST', body: JSON.stringify({url: $('#mu').value, intervalMinutes: +$('#mi').value})}); monitorsView(); } catch (x) { $('#me').textContent = x.message; } };
  const d = await api('/v1/monitor');
  $('#ml').innerHTML = d.monitors.map(m => `<div class="card"><div class="row" style="justify-content:space-between"><div><b>${esc(m.url)}</b> <span class="hint">every ${m.interval_minutes} min · last: ${esc(m.last_change || 'pending')}</span></div>
    <div class="row"><button class="ghost" data-run="${m.id}">Check now</button><button class="link" data-del="${m.id}">Delete</button></div></div><div id="c${m.id}"></div></div>`).join('') || '<p class="muted">No monitors yet.</p>';
  $('#ml').onclick = async e => {
    const r = e.target.dataset.run, x = e.target.dataset.del;
    if (x) { await api('/v1/monitor/' + x, {method: 'DELETE'}); return monitorsView(); }
    if (r) { e.target.disabled = true; const c = await api(`/v1/monitor/${r}/run`, {method: 'POST'}); e.target.disabled = false;
      $('#c' + r).innerHTML = c.checks.slice(0, 5).map(k => `<div class="hint">${esc(new Date(k.at).toLocaleString())} · ${esc(k.change_status || k.status)} ${k.error ? esc(k.error) : ''}</div>${k.diff ? `<pre>${esc(k.diff.slice(0, 3000))}</pre>` : ''}`).join(''); }
  };
}

// ---------------- API & keys ----------------
async function apiView() {
  const me = await api('/auth/me'), keys = await api('/v1/keys');
  const base = location.origin;
  app.innerHTML = `<h1>API &amp; keys</h1><p class="sub">Firecrawl-compatible endpoints under <code>${esc(base)}/v1</code> (also <code>/v2</code>). Daily credits: ${me.usedToday} / ${me.dailyCredits} used.</p>
  <div class="card"><div class="row"><input id="kn" placeholder="key name" style="max-width:240px"><button id="kc">Create API key</button></div><div id="kv" style="margin-top:8px"></div>
  <table style="margin-top:10px"><tbody>${keys.keys.map(k => `<tr><td><code>${esc(k.prefix)}…</code></td><td>${esc(k.name)}</td><td>${esc(new Date(k.created_at).toLocaleDateString())}</td><td><button class="link" data-k="${k.id}">Revoke</button></td></tr>`).join('')}</tbody></table>
  <p class="hint">Webhook signing secret (HMAC-SHA256 of the raw body, header <code>X-CrawlMonk-Signature: sha256=…</code>): <code>${esc(me.user.webhook_secret)}</code></p></div>
  <div class="card"><h2>Endpoints</h2><pre>${esc(`POST /v1/scrape        {url, formats:[markdown|html|rawHtml|links|images|contacts|screenshot|summary|changeTracking|{type:"json",prompt,schema}],
                         onlyMainContent, includeTags, excludeTags, waitFor, timeout, mobile, headers, maxAge, actions, engine}
POST /v1/crawl         {url, limit, maxDiscoveryDepth, includePaths, excludePaths, allowExternalLinks, allowSubdomains,
                         crawlEntireDomain, ignoreQueryParameters, delay, maxConcurrency, sitemap, scrapeOptions, webhook}
GET  /v1/crawl/{id}    status + data (paginated with next)     DELETE /v1/crawl/{id}  cancel
POST /v1/batch/scrape  {urls, formats, ..., webhook}           GET /v1/batch/scrape/{id}
POST /v1/map           {url, search, includeSubdomains, limit, sitemap}
POST /v1/search        {query, limit, sources:["web","news"], tbs, scrapeOptions}
POST /v1/extract       {urls, prompt, schema, enableWebSearch}  GET /v1/extract/{id}   (needs Gemini key on server)
POST /v1/agent         {prompt, schema, urls}                   GET /v1/agent/{id}     (needs Gemini key on server)
POST /v1/parse         multipart file (pdf, docx, xlsx, html, txt)
POST /v1/leads         {cities:[{city,state}], category, keywords, goal:"agency"|"buyer", offer, max_leads, sources:["osm","web"]}
GET  /v1/leads/{id}    GET /v1/leads/{id}/csv
POST /v1/monitor       {url, intervalMinutes, webhook}          GET /v1/monitor/{id}/checks
POST /v1/interact      {url} -> live browser session            POST /v1/interact/{sessionId} {actions}   DELETE ...
GET  /v1/team/credit-usage
POST /mcp              MCP server (JSON-RPC: tools/list, tools/call) with the same Bearer key
Interactive schema: ${base}/docs`)}</pre>
  <h2>curl</h2><pre>${esc(`curl -X POST ${base}/v1/scrape -H "Authorization: Bearer cm-YOUR_KEY" -H "Content-Type: application/json" \\
  -d '{"url":"https://example.com","formats":["markdown","contacts"]}'`)}</pre>
  <h2>Python</h2><pre>${esc(`import requests, time
H = {"Authorization": "Bearer cm-YOUR_KEY"}
job = requests.post("${base}/v1/leads", headers=H, json={"cities":[{"city":"Vadodara","state":"Gujarat"}],"category":"chemical manufacturer","goal":"buyer"}).json()
while True:
    r = requests.get(f"${base}/v1/leads/{job['id']}", headers=H).json()
    if r["status"] not in ("queued","running"): break
    time.sleep(5)
for l in r["leads"][:10]: print(l["score"], l["name"], l["phone"], l["emails"], l["website"])
# Endpoints mirror Firecrawl v1/v2 request shapes; pointing a Firecrawl SDK at api_url="${base}" may work (untested).`)}</pre>
  <h2>JavaScript</h2><pre>${esc(`const r = await fetch("${base}/v1/scrape", {method: "POST",
  headers: {Authorization: "Bearer cm-YOUR_KEY", "Content-Type": "application/json"},
  body: JSON.stringify({url: "https://example.com", formats: ["markdown"]})});
console.log((await r.json()).data.markdown);`)}</pre>
  <h2>MCP (Claude Desktop / Cursor)</h2><pre>${esc(`{"mcpServers": {"crawlmonk": {"url": "${base}/mcp", "headers": {"Authorization": "Bearer cm-YOUR_KEY"}}}}`)}</pre></div>`;
  $('#kc').onclick = async () => { const d = await api('/v1/keys', {method: 'POST', body: JSON.stringify({name: $('#kn').value || 'default'})}); $('#kv').innerHTML = `<p class="ok">New key (copy now, shown once): <code>${esc(d.key)}</code></p>`; };
  app.querySelectorAll('[data-k]').forEach(b => b.onclick = async () => { await api('/v1/keys/' + b.dataset.k, {method: 'DELETE'}); apiView(); });
}

function route() {
  clearTimeout(timer);
  if (!token) return authView();
  $('#nav').hidden = false;
  const [page, id] = (location.hash.slice(1) || 'leads').split('/');
  document.querySelectorAll('nav a').forEach(a => a.classList.toggle('on', a.getAttribute('href') === '#' + page));
  const views = {leads: () => leadsView(id), play: playView, jobs: jobsView, monitors: monitorsView, api: apiView};
  Promise.resolve((views[page] || views.leads)()).catch(e => { app.innerHTML = `<p class="err">${esc(e.message)}</p>`; });
}
window.addEventListener('hashchange', route);
route();
