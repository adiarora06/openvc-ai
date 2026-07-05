// Treat bare ISO strings from the backend as UTC (no trailing Z) so the
// browser converts them correctly to the user's local timezone.
function utcDate(str) {
  if (!str) return null;
  return new Date(str.endsWith('Z') || str.includes('+') ? str : str + 'Z');
}

// === TAB NAVIGATION ===
document.querySelectorAll('.nav-tab').forEach(tab => {
  tab.addEventListener('click', () => {
    document.querySelectorAll('.nav-tab').forEach(t => t.classList.remove('active'));
    document.querySelectorAll('.tab-content').forEach(c => c.classList.remove('active'));
    tab.classList.add('active');
    document.getElementById('tab-' + tab.dataset.tab).classList.add('active');
    if (tab.dataset.tab === 'topology') initTopology();
    if (tab.dataset.tab === 'audit') loadAuditLog();
    if (tab.dataset.tab === 'memory') { loadSTM(); loadLTM(); }
  });
});

// === HELPERS ===
function el(tag, cls, txt) { const e = document.createElement(tag); if (cls) e.className = cls; if (txt) e.textContent = txt; return e; }

const TOP_TICKERS = [
  {t:'AAPL',name:'Apple'},{t:'MSFT',name:'Microsoft'},{t:'AMZN',name:'Amazon'},
  {t:'NVDA',name:'NVIDIA'},{t:'GOOGL',name:'Alphabet'},{t:'TSLA',name:'Tesla'},
  {t:'META',name:'Meta'},{t:'JPM',name:'JPMorgan'},{t:'BAC',name:'BofA'},
  {t:'WMT',name:'Walmart'},{t:'DIS',name:'Disney'},{t:'NFLX',name:'Netflix'},
  {t:'PYPL',name:'PayPal'},{t:'INTC',name:'Intel'},{t:'CSCO',name:'Cisco'},
  {t:'ADBE',name:'Adobe'},{t:'ORCL',name:'Oracle'},{t:'CRM',name:'Salesforce'},
  {t:'KO',name:'Coca-Cola'},{t:'PEP',name:'PepsiCo'},{t:'NKE',name:'Nike'},
  {t:'TSM',name:'TSMC'},{t:'BABA',name:'Alibaba'},{t:'UBER',name:'Uber'}
];

// === FORECAST ===
async function postForecast(ticker) {
  const horizon = parseInt(document.getElementById('horizon').value || '30');
  const body = {
    task_type: 'forecast_stock',
    session_id: 'ui-' + Date.now(),
    input: {
      ticker,
      horizon_days: horizon,
      include_news: document.getElementById('include_news').checked,
      include_memo: document.getElementById('include_memo')?.checked ?? false,
    }
  };
  const target = document.getElementById('forecast');
  const ct = document.getElementById('chart-title');
  target.innerHTML = '<div class="empty-state"><p>Loading ' + ticker + '...</p></div>';
  if (ct) ct.textContent = 'Loading ' + ticker + '...';
  sbSetActivity('Forecasting ' + ticker + '…', true);
  try {
    const resp = await fetch('/a2a/execute', { method: 'POST', headers: { 'content-type': 'application/json' }, body: JSON.stringify(body) });
    const raw = await resp.text();
    if (!resp.ok) { let d = raw; try { d = JSON.parse(raw).detail || raw; } catch(_) {} sbSetActivity('Error: ' + d.slice(0, 60), false); throw new Error(d || 'HTTP ' + resp.status); }
    const result = JSON.parse(raw);
    if (result.status === 'failed') { throw new Error(result.error || 'Forecast failed'); }
    renderForecast(result.output);
    sbSetActivity('Forecast ready — ' + ticker, false);
    refreshStatusBar();
  } catch (err) { target.innerHTML = '<div class="empty-state" style="color:var(--danger)"><p>' + err.message + '</p></div>'; sbSetActivity('Error — ' + ticker, false); }
}

function renderForecast(data) {
  const target = document.getElementById('forecast');
  const ct = document.getElementById('chart-title');
  if (ct) ct.textContent = data.ticker + ' \u2014 ' + data.horizon_days + 'd Forecast';
  const up = data.expected_price > data.current_price;
  let h = '<div class="forecast-header"><span class="forecast-ticker">' + data.ticker + '</span><span class="forecast-horizon">' + data.horizon_days + 'd</span></div>';
  h += '<div class="metric-grid"><div class="metric-box"><div class="metric-label">Current</div><div class="metric-value">$' + (data.current_price?.toFixed(2) ?? 'N/A') + '</div></div>';
  h += '<div class="metric-box"><div class="metric-label">Expected</div><div class="metric-value ' + (up ? 'positive' : 'negative') + '">$' + (data.expected_price?.toFixed(2) ?? 'N/A') + '</div></div>';
  h += '<div class="metric-box"><div class="metric-label">Low (10th)</div><div class="metric-value">$' + (data.lower_bound?.toFixed(2) ?? 'N/A') + '</div></div>';
  h += '<div class="metric-box"><div class="metric-label">High (90th)</div><div class="metric-value">$' + (data.upper_bound?.toFixed(2) ?? 'N/A') + '</div></div></div>';
  h += '<div class="metric-box"><div class="metric-label">Confidence</div><div class="metric-value">' + (data.confidence * 100).toFixed(1) + '%</div></div>';
  if (data.explanation) h += '<div class="forecast-section-title">Analysis</div><div class="forecast-explanation">' + data.explanation + '</div>';
  if (data.risks?.length) { h += '<div class="forecast-section-title">Risks</div><ul class="forecast-list">'; data.risks.slice(0,6).forEach(r => h += '<li>' + r + '</li>'); h += '</ul>'; }
  if (data.investment_memo) h += '<div class="forecast-section-title">Investment Memo</div><div class="forecast-explanation">' + data.investment_memo + '</div>';
  if (data.elapsed_ms != null) h += '<div class="forecast-meta">Generated in ' + (data.elapsed_ms/1000).toFixed(2) + 's</div>';
  target.innerHTML = h;
  try { updateChart(data); } catch(e) { console.warn(e); }
}

function renderTickers(filter) {
  const c = document.getElementById('tickers'); c.innerHTML = '';
  const q = (filter||'').trim().toLowerCase();
  const m = TOP_TICKERS.filter(t => !q || t.t.toLowerCase().includes(q) || t.name.toLowerCase().includes(q));
  if (q && !m.find(x => x.t.toLowerCase() === q)) {
    const card = el('div','stock-card'); card.appendChild(el('div','card-ticker',q.toUpperCase())); card.appendChild(el('div','card-company','Custom'));
    const btn = el('button','card-btn','Forecast'); btn.onclick = () => postForecast(q.toUpperCase()); card.appendChild(btn); c.appendChild(card);
  }
  m.forEach(t => { const card = el('div','stock-card'); card.appendChild(el('div','card-ticker',t.t)); card.appendChild(el('div','card-company',t.name)); const btn = el('button','card-btn','Forecast'); btn.onclick = () => postForecast(t.t); card.appendChild(btn); c.appendChild(card); });
}

async function renderTopStocks() {
  const c = document.getElementById('top-stocks'); if (!c) return; c.innerHTML = '';
  const results = [];
  for (const t of TOP_TICKERS.slice(0,10)) {
    try { const r = await fetch('/quote?ticker=' + t.t); if (!r.ok) continue; const j = await r.json(); if (j.current != null) results.push({...t, current: j.current, previous: j.previous, source: j.source, as_of: j.as_of}); } catch(e) {}
  }
  results.forEach(item => {
    const card = el('div','ticker-card'); card.appendChild(el('div','ticker-symbol',item.t)); card.appendChild(el('div','ticker-name',item.name));
    const p = el('div','ticker-price','$' + item.current.toFixed(2));
    if (item.previous != null) p.classList.add(item.current > item.previous ? 'up' : 'down');
    card.appendChild(p);
    if (item.source === 'demo') card.appendChild(el('div','ticker-source demo','DEMO'));
    else if (item.as_of) card.appendChild(el('div','ticker-source','As of ' + item.as_of));
    card.onclick = () => postForecast(item.t); c.appendChild(card);
  });
}

// === CHART ===
let forecastChart = null, lastPayload = null;
function updateChart(data) {
  lastPayload = data;
  const ctx = document.getElementById('forecastChart').getContext('2d');
  const history = (data.price_history||[]).map(p => ({x: new Date(p.timestamp??p.date), y: p.close}));
  const forecast = (data.forecast_series||[]).map(s => ({x: new Date(s.date), y: s.p50??s.expected}));
  const lower = (data.forecast_series||[]).map(s => ({x: new Date(s.date), y: s.p10??s.lower}));
  const upper = (data.forecast_series||[]).map(s => ({x: new Date(s.date), y: s.p90??s.upper}));
  const sH = document.getElementById('toggle-history')?.checked ?? true;
  const sM = document.getElementById('toggle-median')?.checked ?? true;
  const sB = document.getElementById('toggle-band')?.checked ?? true;
  const sP = document.getElementById('toggle-simpaths')?.checked ?? true;
  const ds = [];
  if (history.length && sH) ds.push({label:'Historical',data:history,borderColor:'#111827',backgroundColor:'rgba(17,24,39,0.04)',tension:0.3,pointRadius:0,borderWidth:2,fill:true});
  if (data.forecast_paths && sP) { const dates = (data.forecast_series||[]).map(s=>s.date); (data.forecast_paths||[]).slice(0,8).forEach((path,i) => ds.push({label:i===0?'Simulations':'',data:dates.map((d,j)=>({x:new Date(d),y:path[j]})),borderColor:'rgba(0,0,0,0.06)',borderWidth:1,pointRadius:0,tension:0.2,fill:false})); }
  if (sB && lower.length) { ds.push({label:'10th %',data:lower,borderColor:'rgba(220,38,38,0.4)',borderWidth:1.5,borderDash:[4,4],pointRadius:0,tension:0.3,fill:false}); ds.push({label:'90th %',data:upper,borderColor:'rgba(5,150,105,0.4)',backgroundColor:'rgba(5,150,105,0.04)',borderWidth:1.5,borderDash:[4,4],pointRadius:0,tension:0.3,fill:'-1'}); }
  if (forecast.length && sM) ds.push({label:'Median Forecast',data:forecast,borderColor:'#059669',backgroundColor:'rgba(5,150,105,0.06)',tension:0.3,pointRadius:0,borderWidth:2.5,borderDash:[6,4],fill:true});
  if (data.current_price && history.length && sH) ds.push({label:'Current',data:[{x:history[history.length-1].x,y:data.current_price}],backgroundColor:'#111827',borderColor:'#fff',pointRadius:7,pointBorderWidth:2,showLine:false});
  if (data.expected_price && forecast.length && sM) ds.push({label:'Target',data:[{x:forecast[forecast.length-1].x,y:data.expected_price}],backgroundColor:'#059669',borderColor:'#fff',pointRadius:7,pointBorderWidth:2,showLine:false});

  const opts = {maintainAspectRatio:false,responsive:true,animation:{duration:500},interaction:{mode:'index',intersect:false},
    scales:{x:{type:'time',time:{unit:'day',displayFormats:{day:'MMM d'}},ticks:{color:'#9ca3af',font:{size:10}},grid:{color:'rgba(0,0,0,0.04)'}},y:{ticks:{color:'#9ca3af',font:{size:10},callback:v=>'$'+v.toFixed(0)},grid:{color:'rgba(0,0,0,0.04)'}}},
    plugins:{legend:{position:'top',align:'end',labels:{color:'#6b7280',font:{size:10},filter:i=>i.text&&i.text.trim()!=='',boxWidth:10,usePointStyle:true}},tooltip:{backgroundColor:'#111827',titleColor:'#fff',bodyColor:'#d1d5db',padding:10,cornerRadius:6,bodyFont:{size:11},callbacks:{label:c=>{let l=c.dataset.label||'';return l?' '+l+': $'+c.parsed.y.toFixed(2):null;}}}}};
  if (forecastChart) { forecastChart.data.datasets = ds; forecastChart.update(); return; }
  forecastChart = new Chart(ctx, {type:'line',data:{datasets:ds},options:opts});
}

// === BACKTEST ===
let backtestChart = null;

function isoDate(d) {
  return d.toISOString().slice(0, 10);
}

function fmtMoney(v) {
  return v == null || Number.isNaN(v) ? 'N/A' : '$' + Number(v).toFixed(2);
}

function fmtPct(v) {
  return v == null || Number.isNaN(v) ? 'N/A' : (Number(v) * 100).toFixed(1) + '%';
}

function initBacktest() {
  const end = new Date();
  end.setDate(end.getDate() - 14);
  const start = new Date(end);
  start.setMonth(start.getMonth() - 6);
  const startEl = document.getElementById('bt-start');
  const endEl = document.getElementById('bt-end');
  if (startEl && !startEl.value) startEl.value = isoDate(start);
  if (endEl && !endEl.value) endEl.value = isoDate(end);
  document.getElementById('backtest-run')?.addEventListener('click', runBacktest);
  document.getElementById('backtest-run-top')?.addEventListener('click', runBacktest);
  document.getElementById('bt-ticker')?.addEventListener('keydown', e => {
    if (e.key === 'Enter') runBacktest();
  });
}

function backtestPayload() {
  const ticker = document.getElementById('bt-ticker').value.trim().toUpperCase();
  const start = document.getElementById('bt-start').value;
  const end = document.getElementById('bt-end').value;
  if (!ticker) throw new Error('Ticker is required');
  if (!start || !end) throw new Error('Start and end dates are required');
  return {
    ticker,
    start_date: start,
    end_date: end,
    horizon_days: parseInt(document.getElementById('bt-horizon').value || '10'),
    training_window_days: parseInt(document.getElementById('bt-training').value || '60'),
    stride_days: parseInt(document.getElementById('bt-stride').value || '10'),
    max_windows: parseInt(document.getElementById('bt-windows').value || '12'),
  };
}

async function runBacktest() {
  const summary = document.getElementById('backtest-summary');
  const table = document.getElementById('backtest-table');
  try {
    const payload = backtestPayload();
    summary.innerHTML = '<div class="empty-state"><p>Running backtest for ' + payload.ticker + '...</p></div>';
    table.innerHTML = '<div class="empty-state"><p>Loading windows...</p></div>';
    sbSetActivity('Backtesting ' + payload.ticker + '...', true);
    const resp = await fetch('/backtest', {
      method: 'POST',
      headers: { 'content-type': 'application/json' },
      body: JSON.stringify(payload),
    });
    const raw = await resp.text();
    if (!resp.ok) {
      let detail = raw;
      try { detail = JSON.parse(raw).detail || raw; } catch (_) {}
      throw new Error(detail || 'HTTP ' + resp.status);
    }
    const data = JSON.parse(raw);
    renderBacktest(data);
    sbSetActivity('Backtest ready - ' + data.ticker, false);
  } catch (err) {
    summary.innerHTML = '<div class="empty-state" style="color:var(--danger)"><p>' + err.message + '</p></div>';
    table.innerHTML = '<div class="empty-state"><p>No windows available.</p></div>';
    sbSetActivity('Backtest error', false);
  }
}

function renderBacktest(data) {
  const summary = document.getElementById('backtest-summary');
  const table = document.getElementById('backtest-table');
  const directionClass = data.directional_accuracy >= 0.5 ? 'positive' : 'negative';
  const coverageClass = data.interval_coverage >= 0.7 ? 'positive' : 'negative';
  summary.innerHTML =
    '<div class="metric-grid backtest-metrics">' +
      '<div class="metric-box"><div class="metric-label">Ticker</div><div class="metric-value">' + data.ticker + '</div></div>' +
      '<div class="metric-box"><div class="metric-label">Windows</div><div class="metric-value">' + data.windows + '</div></div>' +
      '<div class="metric-box"><div class="metric-label">MAE</div><div class="metric-value">' + fmtMoney(data.mae) + '</div></div>' +
      '<div class="metric-box"><div class="metric-label">RMSE</div><div class="metric-value">' + fmtMoney(data.rmse) + '</div></div>' +
      '<div class="metric-box"><div class="metric-label">MAPE</div><div class="metric-value">' + fmtPct(data.mape) + '</div></div>' +
      '<div class="metric-box"><div class="metric-label">Direction</div><div class="metric-value ' + directionClass + '">' + fmtPct(data.directional_accuracy) + '</div></div>' +
      '<div class="metric-box"><div class="metric-label">Coverage</div><div class="metric-value ' + coverageClass + '">' + fmtPct(data.interval_coverage) + '</div></div>' +
      '<div class="metric-box"><div class="metric-label">Avg Actual Return</div><div class="metric-value ' + (data.average_actual_return >= 0 ? 'positive' : 'negative') + '">' + fmtPct(data.average_actual_return) + '</div></div>' +
    '</div>' +
    '<div class="backtest-note">Evaluated forecast dates from ' + (data.first_forecast_date || 'N/A') + ' to ' + (data.last_forecast_date || 'N/A') + ' using ' + data.data_points + ' historical price points.</div>';

  const rows = data.window_results || [];
  if (!rows.length) {
    table.innerHTML = '<div class="empty-state"><p>No evaluation windows returned.</p></div>';
  } else {
    table.innerHTML = '<table class="backtest-table"><thead><tr><th>Forecast</th><th>Target</th><th>Start</th><th>Predicted</th><th>Actual</th><th>Error</th><th>Dir</th><th>Band</th></tr></thead><tbody>' +
      rows.map(w => '<tr>' +
        '<td>' + w.forecast_date + '</td>' +
        '<td>' + w.target_date + '</td>' +
        '<td>' + fmtMoney(w.start_price) + '</td>' +
        '<td>' + fmtMoney(w.predicted_price) + '</td>' +
        '<td>' + fmtMoney(w.actual_price) + '</td>' +
        '<td>' + fmtPct(w.percentage_error) + '</td>' +
        '<td><span class="bt-pill ' + (w.direction_correct ? 'ok' : 'bad') + '">' + (w.direction_correct ? 'Hit' : 'Miss') + '</span></td>' +
        '<td><span class="bt-pill ' + (w.interval_hit ? 'ok' : 'bad') + '">' + (w.interval_hit ? 'Inside' : 'Outside') + '</span></td>' +
      '</tr>').join('') +
    '</tbody></table>';
  }
  updateBacktestChart(data);
}

function updateBacktestChart(data) {
  const canvas = document.getElementById('backtestChart');
  if (!canvas) return;
  const rows = data.window_results || [];
  document.getElementById('backtest-chart-title').textContent = data.ticker + ' backtest - predicted vs actual';
  const actual = rows.map(w => ({x: new Date(w.target_date), y: w.actual_price}));
  const predicted = rows.map(w => ({x: new Date(w.target_date), y: w.predicted_price}));
  const lower = rows.map(w => ({x: new Date(w.target_date), y: w.lower_bound}));
  const upper = rows.map(w => ({x: new Date(w.target_date), y: w.upper_bound}));
  const ds = [
    {label:'Actual', data:actual, borderColor:'#111827', backgroundColor:'#111827', pointRadius:4, borderWidth:2, tension:0.2},
    {label:'Predicted', data:predicted, borderColor:'#059669', backgroundColor:'#059669', pointRadius:4, borderWidth:2, borderDash:[6,4], tension:0.2},
    {label:'10th %', data:lower, borderColor:'rgba(220,38,38,0.45)', pointRadius:0, borderWidth:1.5, borderDash:[4,4], tension:0.2},
    {label:'90th %', data:upper, borderColor:'rgba(5,150,105,0.45)', backgroundColor:'rgba(5,150,105,0.04)', pointRadius:0, borderWidth:1.5, borderDash:[4,4], fill:'-1', tension:0.2},
  ];
  const opts = {maintainAspectRatio:false,responsive:true,interaction:{mode:'index',intersect:false},
    scales:{x:{type:'time',time:{unit:'day'},ticks:{color:'#9ca3af',font:{size:10}},grid:{color:'rgba(0,0,0,0.04)'}},y:{ticks:{color:'#9ca3af',font:{size:10},callback:v=>'$'+v.toFixed(0)},grid:{color:'rgba(0,0,0,0.04)'}}},
    plugins:{legend:{position:'top',align:'end',labels:{color:'#6b7280',font:{size:10},boxWidth:10,usePointStyle:true}},tooltip:{backgroundColor:'#111827',titleColor:'#fff',bodyColor:'#d1d5db',padding:10,cornerRadius:6,callbacks:{label:c=>' ' + c.dataset.label + ': $' + c.parsed.y.toFixed(2)}}}};
  if (backtestChart) {
    backtestChart.data.datasets = ds;
    backtestChart.options = opts;
    backtestChart.update();
    return;
  }
  backtestChart = new Chart(canvas.getContext('2d'), {type:'line',data:{datasets:ds},options:opts});
}

// === CHIP SYNC ===
function syncChips() { document.querySelectorAll('.chip').forEach(c => { const i = c.querySelector('input'); if(!i)return; const u=()=>c.classList.toggle('active',i.checked); i.addEventListener('change',u); u(); }); }

// === STATUS ===
async function loadStatus() {
  const dot = document.getElementById('status-dot'), txt = document.getElementById('status-text'), panel = document.getElementById('status-panel');
  try {
    const r = await fetch('/status'); if(!r.ok) throw new Error(); const s = await r.json();
    dot.className = 'status-dot ' + (s.status==='ok'?'ok':s.status==='degraded'||s.status==='unconfigured'?'degraded':'error');
    txt.textContent = s.status.toUpperCase() + ' v' + s.version;
    panel.innerHTML = '';
    const ac = el('div','diag-card'); ac.appendChild(el('h4',null,'Agents'));
    (s.agents||[]).forEach(a => { const row = el('div','diag-row'); row.appendChild(el('span',null,a.name)); row.appendChild(el('span','diag-pill pill-'+(a.status||'ready'),a.status||'ready')); ac.appendChild(row); });
    panel.appendChild(ac);
    const dc = el('div','diag-card'); dc.appendChild(el('h4',null,'Dependencies'));
    (s.dependencies||[]).forEach(d => { const row = el('div','diag-row'); row.appendChild(el('span',null,d.name)); row.appendChild(el('span','diag-pill pill-'+d.status,d.status)); dc.appendChild(row); });
    panel.appendChild(dc);
    const rc = el('div','diag-card'); rc.appendChild(el('h4',null,'Runtime'));
    const r1 = el('div','diag-row'); r1.appendChild(el('span',null,'LLM')); r1.appendChild(el('span',null,s.primary_llm_provider)); rc.appendChild(r1);
    const r2 = el('div','diag-row'); r2.appendChild(el('span',null,'Uptime')); r2.appendChild(el('span',null,Math.round(s.uptime_seconds)+'s')); rc.appendChild(r2);
    panel.appendChild(rc);
  } catch(e) { dot.className='status-dot error'; txt.textContent='Offline'; }
}

// === AUDIT LOG ===
// ─── AUDIT LOG ───────────────────────────────────────────────────────────────

let _auditFilter = 'all';

function auditStatusClass(s) {
  if (!s) return 'status-unknown';
  const m = { SUCCEEDED:'status-ok', FAILED:'status-err', RUNNING:'status-running',
               QUEUED:'status-queued', CANCELLED:'status-cancelled' };
  return m[s] || 'status-unknown';
}

function auditEventDir(msg) {
  if (!msg) return { dir: '', cls: '' };
  if (msg.startsWith('SEND →')) return { dir: 'SEND →', cls: 'ev-send' };
  if (msg.startsWith('RECV ←')) return { dir: 'RECV ←', cls: 'ev-recv' };
  if (msg.toUpperCase().includes('SUCCEEDED') || msg.toUpperCase().includes('COMPLETED')) return { dir: 'DONE', cls: 'ev-done' };
  if (msg.toUpperCase().includes('FAIL') || msg.toUpperCase().includes('ERROR')) return { dir: 'ERR', cls: 'ev-err' };
  return { dir: 'INFO', cls: 'ev-info' };
}

function auditEventAgentLabel(msg, fallbackAgent) {
  // Extract "AgentName" from "SEND → AgentName: ..." or "RECV ← AgentName: ..."
  const m = msg && msg.match(/(?:SEND →|RECV ←)\s+([\w]+):/);
  return m ? m[1] : (fallbackAgent || 'Orchestrator');
}

function buildAgentChain(task) {
  const agents = [];
  // Always starts at User → API
  agents.push({ label: 'User', cls: 'chain-user' });
  agents.push({ label: 'API', cls: 'chain-api' });
  agents.push({ label: 'Orchestrator', cls: 'chain-core' });

  // Collect unique agents seen in events
  const seen = new Set(['CentralA2AOrchestrator']);
  (task.events || []).forEach(ev => {
    const m = ev.message && ev.message.match(/(?:SEND →|RECV ←)\s+([\w]+):/);
    if (m && !seen.has(m[1])) {
      seen.add(m[1]);
      const name = m[1];
      let cls = 'chain-agent';
      if (name.includes('Quant')) cls = 'chain-quant';
      else if (name.includes('News')) cls = 'chain-news';
      else if (name.includes('Memo')) cls = 'chain-memo';
      else if (name.includes('Market') || name.includes('Data')) cls = 'chain-data';
      agents.push({ label: name.replace('Agent','').replace('Market','Mkt'), cls });
    }
  });
  return agents;
}

function renderAgentChain(agents) {
  return '<div class="agent-chain">' +
    agents.map((a, i) =>
      `<span class="chain-node ${a.cls}">${a.label}</span>` +
      (i < agents.length - 1 ? '<span class="chain-arrow">→</span>' : '')
    ).join('') +
  '</div>';
}

function renderAuditTask(task) {
  const statusCls = auditStatusClass(task.status);
  const created = task.created_at ? utcDate(task.created_at) : null;
  const updated = task.updated_at ? utcDate(task.updated_at) : null;
  const durationMs = (created && updated) ? (updated - created) : null;
  const durationStr = durationMs != null ? (durationMs < 1000 ? durationMs + 'ms' : (durationMs/1000).toFixed(1) + 's') : '—';
  const ticker = (task.input && task.input.ticker) ? task.input.ticker : '';
  const horizon = (task.input && task.input.horizon_days) ? task.input.horizon_days + 'd' : '';
  const agents = buildAgentChain(task);
  const events = (task.events || []);

  // Endpoint labels
  const startAgent = 'User';
  const endAgent = task.assigned_agent || 'CentralA2AOrchestrator';

  const cardId = 'audit-card-' + task.task_id;
  const evId = 'audit-ev-' + task.task_id;

  return `<div class="audit-card" id="${cardId}">
    <div class="audit-card-header" onclick="toggleAuditCard('${evId}')">
      <div class="audit-card-left">
        <span class="audit-task-id">${(task.task_id||'').slice(0,8)}</span>
        <span class="audit-task-type">${task.task_type || '—'}</span>
        ${ticker ? `<span class="audit-ticker">${ticker}${horizon ? ' · ' + horizon : ''}</span>` : ''}
      </div>
      <div class="audit-card-right">
        <span class="audit-endpoints">
          <span class="ep ep-start">${startAgent}</span>
          <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><path d="M5 12h14m-7-7 7 7-7 7"/></svg>
          <span class="ep ep-end">${endAgent}</span>
        </span>
        <span class="audit-duration">${durationStr}</span>
        <span class="audit-status ${statusCls}">${task.status || '—'}</span>
        <span class="audit-time">${created ? created.toLocaleTimeString() : '—'}</span>
        <svg class="audit-chevron" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="m6 9 6 6 6-6"/></svg>
      </div>
    </div>
    <div class="audit-card-body" id="${evId}" style="display:none">
      ${renderAgentChain(agents)}
      <div class="audit-events">
        ${events.length === 0 ? '<div class="audit-ev-empty">No events recorded for this task.</div>' :
          events.map(ev => {
            const { dir, cls } = auditEventDir(ev.message);
            const agentLabel = auditEventAgentLabel(ev.message, ev.agent);
            const ts = ev.timestamp ? utcDate(ev.timestamp).toLocaleTimeString() : '';
            // Strip the "SEND → AgentName:" / "RECV ← AgentName:" prefix for cleaner display
            const msgBody = (ev.message || '').replace(/^(?:SEND →|RECV ←)\s+[\w]+:\s*/,'');
            return `<div class="audit-ev ${cls}">
              <span class="ev-ts">${ts}</span>
              <span class="ev-agent">${agentLabel}</span>
              <span class="ev-dir-badge ${cls}">${dir}</span>
              <span class="ev-status ${auditStatusClass(ev.status)}">${ev.status || ''}</span>
              <span class="ev-msg">${msgBody}</span>
            </div>`;
          }).join('')
        }
      </div>
    </div>
  </div>`;
}

function toggleAuditCard(evId) {
  const el = document.getElementById(evId);
  if (!el) return;
  const isOpen = el.style.display !== 'none';
  el.style.display = isOpen ? 'none' : 'block';
  // rotate chevron
  const card = el.closest('.audit-card');
  if (card) card.classList.toggle('open', !isOpen);
}

async function loadAuditLog() {
  const list = document.getElementById('audit-list');
  list.innerHTML = '<div class="muted" style="padding:2rem">Loading…</div>';
  try {
    const r = await fetch('/tasks?limit=100');
    let tasks = await r.json();
    if (!Array.isArray(tasks) || !tasks.length) {
      list.innerHTML = '<div class="audit-empty"><svg width="40" height="40" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><rect x="3" y="3" width="18" height="18" rx="2"/><path d="M9 9h6M9 12h6M9 15h4"/></svg><p>No tasks recorded yet.<br>Run a forecast to see agent activity here.</p></div>';
      return;
    }
    tasks = tasks.slice().reverse();
    if (_auditFilter !== 'all') tasks = tasks.filter(t => t.status === _auditFilter);
    if (!tasks.length) {
      list.innerHTML = '<div class="audit-empty"><p>No tasks match the current filter.</p></div>';
      return;
    }
    list.innerHTML = tasks.map(renderAuditTask).join('');
    // Auto-expand the most recent task
    const first = tasks[0];
    if (first) {
      const firstEv = document.getElementById('audit-ev-' + first.task_id);
      if (firstEv) {
        firstEv.style.display = 'block';
        const card = firstEv.closest('.audit-card');
        if (card) card.classList.add('open');
      }
    }
  } catch(e) {
    list.innerHTML = '<div class="muted" style="padding:2rem">Failed to load tasks: ' + e.message + '</div>';
  }
}

// === MEMORY ===
async function loadSTM() {
  const list = document.getElementById('stm-list'); list.innerHTML = '<div class="muted">Loading...</div>';
  try {
    const r = await fetch('/memory/stats'); const stats = await r.json();
    if (!stats.sessions.length) { list.innerHTML = '<div class="muted">No sessions yet</div>'; return; }
    list.innerHTML = '';
    for (const sid of stats.sessions.slice(-5)) {
      const rr = await fetch('/memory/' + sid + '?limit=10'); const records = await rr.json();
      records.forEach(rec => {
        const item = el('div','memory-item');
        item.innerHTML = '<div class="mem-kind">' + rec.kind + ' &middot; ' + sid.slice(0,12) + '</div><div class="mem-content">' + rec.content.slice(0,200) + '</div><div class="mem-time">' + (utcDate(rec.created_at)?.toLocaleString() ?? '') + '</div>';
        list.appendChild(item);
      });
    }
    if (!list.children.length) list.innerHTML = '<div class="muted">No records</div>';
  } catch(e) { list.innerHTML = '<div class="muted">Failed to load</div>'; }
}

async function loadLTM() {
  const list = document.getElementById('ltm-list'); list.innerHTML = '<div class="muted">Loading...</div>';
  try {
    const r = await fetch('/memory/long-term?limit=50'); const records = await r.json();
    if (!records.length) { list.innerHTML = '<div class="muted">No long-term memories yet</div>'; return; }
    list.innerHTML = '';
    records.forEach(rec => {
      const item = el('div','memory-item');
      item.innerHTML = '<div class="mem-kind">' + rec.kind + '</div><div class="mem-content">' + rec.content + '</div><div class="mem-time">' + (utcDate(rec.created_at)?.toLocaleString() ?? '') + '</div>';
      list.appendChild(item);
    });
  } catch(e) { list.innerHTML = '<div class="muted">Failed to load</div>'; }
}

async function addLTM() {
  const input = document.getElementById('ltm-input'); const content = input.value.trim(); if (!content) return;
  await fetch('/memory/long-term', {method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({kind:'insight',content})});
  input.value = ''; loadLTM();
}

// === INIT ===
document.addEventListener('DOMContentLoaded', () => {
  renderTopStocks(); syncChips(); initBacktest(); loadStatus(); setInterval(loadStatus, 30000);
  ['toggle-history','toggle-median','toggle-band','toggle-simpaths'].forEach(id => { const e = document.getElementById(id); if(e) e.addEventListener('change', () => { if(lastPayload) updateChart(lastPayload); }); });
  document.getElementById('search').addEventListener('input', e => {});
  document.getElementById('search').addEventListener('keydown', e => { if(e.key==='Enter'){const v=e.target.value.trim().toUpperCase();if(v)postForecast(v);} });
  document.getElementById('audit-refresh')?.addEventListener('click', loadAuditLog);
  document.querySelectorAll('.audit-filter-btn').forEach(btn => {
    btn.addEventListener('click', () => {
      document.querySelectorAll('.audit-filter-btn').forEach(b => b.classList.remove('active'));
      btn.classList.add('active');
      _auditFilter = btn.dataset.filter || 'all';
      loadAuditLog();
    });
  });
  document.getElementById('stm-refresh')?.addEventListener('click', loadSTM);
  document.getElementById('ltm-refresh')?.addEventListener('click', loadLTM);
  document.getElementById('ltm-add')?.addEventListener('click', addLTM);
  document.getElementById('ltm-input')?.addEventListener('keydown', e => { if(e.key==='Enter') addLTM(); });
});

// === LIVE STATUS BAR ===
let sbDot, sbStatus, sbLlm, sbAgents, sbTasks, sbMemory, sbUptime, sbActivity;

function sbSetActivity(msg, busy = false) {
  if (!sbActivity) return;
  sbActivity.textContent = msg;
  sbActivity.className = 'sb-activity' + (busy ? ' busy' : '');
}

function sbFmtUptime(secs) {
  if (secs < 60) return Math.round(secs) + 's';
  if (secs < 3600) return Math.floor(secs / 60) + 'm ' + (Math.round(secs) % 60) + 's';
  return Math.floor(secs / 3600) + 'h ' + Math.floor((secs % 3600) / 60) + 'm';
}

async function refreshStatusBar() {
  try {
    const r = await fetch('/status');
    if (!r.ok) throw new Error('status ' + r.status);
    const s = await r.json();

    const ok = s.status === 'ok';
    const deg = s.status === 'degraded' || s.status === 'unconfigured';
    if (sbDot) sbDot.className = 'sb-dot ' + (ok ? 'ok' : deg ? 'deg' : 'err');
    if (sbStatus) sbStatus.textContent = (s.status || 'unknown').toUpperCase();
    if (sbLlm) sbLlm.textContent = 'LLM: ' + (s.primary_llm_provider || '—');

    const readyCount  = (s.agents || []).filter(a => a.status === 'ready').length;
    const totalAgents = (s.agents || []).length;
    if (sbAgents) sbAgents.textContent = readyCount + '/' + totalAgents + ' agents';
    if (sbTasks)  sbTasks.textContent  = (s.active_tasks ?? 0) + ' tasks';
    if (sbMemory) sbMemory.textContent = (s.memory_records ?? 0) + ' records';
    if (sbUptime) sbUptime.textContent = 'up ' + sbFmtUptime(s.uptime_seconds || 0);
    if (!sbActivity || sbActivity.textContent === 'Idle' || sbActivity.textContent === 'Connecting…') {
      sbSetActivity('Idle', false);
    }
  } catch(_) {
    if (sbDot)    sbDot.className = 'sb-dot err';
    if (sbStatus) sbStatus.textContent = 'OFFLINE';
  }
}

document.addEventListener('DOMContentLoaded', () => {
  sbDot      = document.getElementById('sb-dot');
  sbStatus   = document.getElementById('sb-status');
  sbLlm      = document.getElementById('sb-llm');
  sbAgents   = document.getElementById('sb-agents');
  sbTasks    = document.getElementById('sb-tasks');
  sbMemory   = document.getElementById('sb-memory');
  sbUptime   = document.getElementById('sb-uptime');
  sbActivity = document.getElementById('sb-activity');
  refreshStatusBar();
  setInterval(refreshStatusBar, 10000);
});

// === TOPOLOGY (HTML + SVG node graph) ===
const NODE_W = 148, NODE_H = 56;

const TOPO_ICONS = {
  core:     '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="2" y="3" width="20" height="14" rx="2"/><path d="M8 21h8M12 17v4"/></svg>',
  agent:    '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="8" r="4"/><path d="M4 20c0-4 3.6-7 8-7s8 3 8 7"/></svg>',
  service:  '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M12 2L2 7l10 5 10-5-10-5z"/><path d="M2 17l10 5 10-5"/><path d="M2 12l10 5 10-5"/></svg>',
  external: '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"/><path d="M2 12h20M12 2a15.3 15.3 0 0 1 4 10 15.3 15.3 0 0 1-4 10 15.3 15.3 0 0 1-4-10 15.3 15.3 0 0 1 4-10z"/></svg>',
};

// Fixed layout columns (px from stage left), rows assigned per column
const COL = { user: 40, api: 240, orchestrator: 470, agents: 700, services: 940 };

let topoNodes = [], topoEdges = [], topoInited = false;

function getTopoLayout(agentNames) {
  const nodes = [];
  // Column 0 — user
  nodes.push({ id: 'user',         label: 'Browser',      sub: 'Client',          type: 'external', cx: COL.user,          cy: 280 });
  // Column 1 — API
  nodes.push({ id: 'api',          label: 'FastAPI',       sub: 'port 5050',       type: 'core',     cx: COL.api,           cy: 200 });
  nodes.push({ id: 'planner',      label: 'Planner',       sub: 'Capability',      type: 'service',  cx: COL.api,           cy: 320 });
  // Column 2 — orchestrator
  nodes.push({ id: 'orchestrator', label: 'Orchestrator',  sub: 'A2A Router',      type: 'core',     cx: COL.orchestrator,  cy: 260 });
  // Column 3 — agents (dynamic)
  const agStep = Math.max(72, 380 / Math.max(agentNames.length, 1));
  const agStart = 260 - ((agentNames.length - 1) * agStep) / 2;
  agentNames.forEach((name, i) => {
    nodes.push({ id: 'agent-' + name, label: name.replace(/Agent$/, ''), sub: 'Agent · ready', type: 'agent', cx: COL.agents, cy: agStart + i * agStep });
  });
  // Column 4 — services / external
  nodes.push({ id: 'memory',       label: 'Memory',        sub: 'SQLite + STM',    type: 'service',  cx: COL.services,      cy: 120 });
  nodes.push({ id: 'tools',        label: 'Tools',         sub: 'Tool registry',   type: 'service',  cx: COL.services,      cy: 210 });
  nodes.push({ id: 'llm',          label: 'LLM Router',    sub: 'Groq / OpenAI',   type: 'service',  cx: COL.services,      cy: 300 });
  nodes.push({ id: 'alphavantage', label: 'Alpha Vantage', sub: 'Price data',      type: 'external', cx: COL.services,      cy: 390 });
  nodes.push({ id: 'finnhub',      label: 'Finnhub',       sub: 'News feed',       type: 'external', cx: COL.services,      cy: 480 });
  return nodes;
}

function getTopoEdges(agentNames) {
  const edges = [];
  edges.push({ from: 'user',         to: 'api',           label: 'HTTP',     animated: true  });
  edges.push({ from: 'api',          to: 'orchestrator',  label: 'Dispatch', animated: false });
  edges.push({ from: 'api',          to: 'planner',       label: 'Plan',     animated: false });
  edges.push({ from: 'planner',      to: 'tools',         label: 'Resolve',  animated: false });
  edges.push({ from: 'orchestrator', to: 'memory',        label: 'Store',    animated: false });
  edges.push({ from: 'orchestrator', to: 'tools',         label: 'Invoke',   animated: false });
  agentNames.forEach(name => {
    const id = 'agent-' + name;
    edges.push({ from: 'orchestrator', to: id, label: 'Task', animated: true });
    if (name.includes('News'))                          edges.push({ from: id, to: 'finnhub',      label: 'Feed'   });
    if (name.includes('Market') && !name.includes('News')) edges.push({ from: id, to: 'alphavantage', label: 'Data'   });
    if (name.includes('Quant') || name.includes('Forecast')) edges.push({ from: id, to: 'alphavantage', label: 'Prices' });
    if (name.includes('Memo')  || name.includes('News')) edges.push({ from: id, to: 'llm',          label: 'LLM'    });
  });
  return edges;
}

function renderTopoNode(node, highlighted) {
  const hl = highlighted === node.id;
  const div = document.createElement('div');
  div.className = 'topo-node type-' + node.type + (hl ? ' hovered' : '');
  div.id = 'tn-' + node.id;
  div.style.left = (node.cx - NODE_W / 2) + 'px';
  div.style.top  = (node.cy - NODE_H / 2) + 'px';
  div.innerHTML = `
    <div class="topo-node-icon">${TOPO_ICONS[node.type] || ''}</div>
    <div class="topo-node-body">
      <div class="topo-node-label">${node.label}</div>
      <div class="topo-node-sub">${node.sub}</div>
    </div>`;
  return div;
}

function nodePort(node, side) {
  // Returns {x, y} of the left or right connector port of a node
  if (side === 'right') return { x: node.cx + NODE_W / 2, y: node.cy };
  return { x: node.cx - NODE_W / 2, y: node.cy };
}

function renderTopoEdges(nodes, edges, highlighted) {
  const edgeGroup = document.getElementById('topo-edges');
  edgeGroup.innerHTML = '';
  edges.forEach(edge => {
    const from = nodes.find(n => n.id === edge.from);
    const to   = nodes.find(n => n.id === edge.to);
    if (!from || !to) return;

    const p1 = nodePort(from, 'right');
    const p2 = nodePort(to, 'left');
    const dx = Math.abs(p2.x - p1.x) * 0.45;
    const d  = `M${p1.x},${p1.y} C${p1.x + dx},${p1.y} ${p2.x - dx},${p2.y} ${p2.x},${p2.y}`;

    const isHl  = highlighted && (edge.from === highlighted || edge.to === highlighted);
    const color = isHl ? '#111827' : edge.animated ? '#059669' : '#d1d5db';
    const marker = isHl ? 'arrow-active' : edge.animated ? 'arrow-animated' : 'arrow-default';

    const path = document.createElementNS('http://www.w3.org/2000/svg', 'path');
    path.setAttribute('d', d);
    path.setAttribute('fill', 'none');
    path.setAttribute('stroke', color);
    path.setAttribute('stroke-width', isHl ? '2' : '1.5');
    path.setAttribute('marker-end', `url(#${marker})`);
    if (edge.animated && !isHl) {
      path.classList.add('topo-edge-animated');
    }
    if (isHl) path.classList.add('topo-edge-hl');
    edgeGroup.appendChild(path);

    // Edge label on hover only
    if (isHl && edge.label) {
      const mx = (p1.x + p2.x) / 2, my = (p1.y + p2.y) / 2 - 9;
      const text = document.createElementNS('http://www.w3.org/2000/svg', 'text');
      text.setAttribute('x', mx); text.setAttribute('y', my);
      text.setAttribute('text-anchor', 'middle');
      text.setAttribute('font-size', '10');
      text.setAttribute('font-family', 'Inter, sans-serif');
      text.setAttribute('fill', '#6b7280');
      text.textContent = edge.label;
      edgeGroup.appendChild(text);
    }
  });
}

async function initTopology() {
  if (topoInited) { await refreshTopology(); return; }
  topoInited = true;
  await refreshTopology();
  document.getElementById('topology-refresh')?.addEventListener('click', refreshTopology);
}

async function refreshTopology() {
  let agentNames = [];
  try {
    const r = await fetch('/status'); const s = await r.json();
    agentNames = (s.agents || []).filter(a => a.name !== 'CentralA2AOrchestrator').map(a => a.name);
  } catch (_) {}

  topoNodes = getTopoLayout(agentNames);
  topoEdges = getTopoEdges(agentNames);

  // Size the SVG & stage to fit all nodes
  const maxX = Math.max(...topoNodes.map(n => n.cx + NODE_W / 2)) + 40;
  const maxY = Math.max(...topoNodes.map(n => n.cy + NODE_H / 2)) + 40;

  const svg   = document.getElementById('topo-svg');
  const stage = document.getElementById('topo-stage');
  svg.setAttribute('width', maxX); svg.setAttribute('height', maxY);
  svg.style.width  = maxX + 'px'; svg.style.height = maxY + 'px';
  stage.style.minWidth  = maxX + 'px'; stage.style.minHeight = maxY + 'px';

  // Render edges first (behind nodes)
  renderTopoEdges(topoNodes, topoEdges, null);

  // Render nodes
  const nodeContainer = document.getElementById('topo-nodes');
  nodeContainer.innerHTML = '';
  topoNodes.forEach(node => {
    const div = renderTopoNode(node, null);
    div.addEventListener('mouseenter', () => {
      renderTopoEdges(topoNodes, topoEdges, node.id);
      document.querySelectorAll('.topo-node').forEach(el => el.classList.remove('hovered'));
      div.classList.add('hovered');
    });
    div.addEventListener('mouseleave', () => {
      renderTopoEdges(topoNodes, topoEdges, null);
      div.classList.remove('hovered');
    });
    nodeContainer.appendChild(div);
  });
}

// === CHATBOT WITH REAL STREAMING ===
document.addEventListener('DOMContentLoaded', () => {
  const toggle = document.getElementById('chat-toggle');
  const win    = document.getElementById('chat-window');
  const close  = document.getElementById('chat-close');
  const clear  = document.getElementById('chat-clear');
  const msgs   = document.getElementById('chat-messages');
  const input  = document.getElementById('chat-input');
  const send   = document.getElementById('chat-send');
  const connDot = document.getElementById('chat-conn-dot');

  let isOpen = false;
  let history = [];
  let sessionId = 'chat-' + Date.now();
  let retryCount = 0;
  const MAX_RETRIES = 2;

  function setConnStatus(status) {
    // status: 'online' | 'connecting' | 'error'
    if (!connDot) return;
    connDot.className = 'chat-conn-dot ' + status;
    connDot.title = status.charAt(0).toUpperCase() + status.slice(1);
  }

  function openChat() {
    isOpen = true;
    win.classList.add('open');
    input.focus();
    toggle.setAttribute('aria-expanded', 'true');
  }

  function closeChat() {
    isOpen = false;
    win.classList.remove('open');
    toggle.setAttribute('aria-expanded', 'false');
  }

  toggle.addEventListener('click', () => isOpen ? closeChat() : openChat());
  close.addEventListener('click', closeChat);

  // ESC to close
  document.addEventListener('keydown', e => {
    if (e.key === 'Escape' && isOpen) closeChat();
  });

  // Clear history
  if (clear) {
    clear.addEventListener('click', () => {
      history = [];
      msgs.innerHTML = '<div class="chat-message assistant"><div class="msg-bubble">Chat cleared. Ask me anything about stocks or forecasts.</div></div>';
    });
  }

  send.addEventListener('click', doSend);
  input.addEventListener('keydown', e => {
    if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); doSend(); }
  });
  input.addEventListener('input', () => {
    input.style.height = 'auto';
    input.style.height = Math.min(input.scrollHeight, 90) + 'px';
  });

  function addMsg(role, text) {
    history.push({ role, content: text });
    const m = el('div', 'chat-message ' + role);
    const bubble = el('div', 'msg-bubble', '');
    bubble.textContent = text;
    m.appendChild(bubble);
    msgs.appendChild(m);
    msgs.scrollTop = msgs.scrollHeight;
    return m;
  }

  function addStreamBubble() {
    const m = el('div', 'chat-message assistant');
    const bubble = el('div', 'msg-bubble', '');
    m.appendChild(bubble);
    msgs.appendChild(m);
    msgs.scrollTop = msgs.scrollHeight;
    return bubble;
  }

  function showTyping() {
    const id = 't-' + Date.now();
    const m = el('div', 'chat-message assistant'); m.id = id;
    const d = el('div', 'typing-indicator');
    d.innerHTML = '<div class="typing-dot"></div><div class="typing-dot"></div><div class="typing-dot"></div>';
    m.appendChild(d); msgs.appendChild(m); msgs.scrollTop = msgs.scrollHeight;
    return id;
  }

  async function doSend(retry = 0) {
    const text = input.value.trim();
    if (!text) return;
    if (retry === 0) {
      addMsg('user', text);
      input.value = '';
      input.style.height = 'auto';
    }
    send.disabled = true;
    setConnStatus('connecting');
    const tid = showTyping();

    try {
      const recent = history.slice(-6).map(m => ({ role: m.role === 'user' ? 'user' : 'assistant', content: m.content }));
      // Ensure last message is the user's current text
      if (!recent.length || recent[recent.length - 1].content !== text) {
        recent.push({ role: 'user', content: text });
      }
      const ctx = {
        session_id: sessionId,
        last_forecast: lastPayload ? { ticker: lastPayload.ticker, current_price: lastPayload.current_price } : null,
      };

      const resp = await fetch('/chat/stream', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ messages: recent, context: ctx }),
      });
      document.getElementById(tid)?.remove();

      if (!resp.ok) {
        const e = await resp.json().catch(() => ({ detail: 'Request failed' }));
        throw new Error(e.detail || 'HTTP ' + resp.status);
      }

      const bubble = addStreamBubble();
      const reader  = resp.body.getReader();
      const decoder = new TextDecoder();
      let fullContent = '';
      let buffer = '';

      setConnStatus('online');

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split('\n');
        buffer = lines.pop() || '';
        for (const line of lines) {
          if (!line.startsWith('data: ')) continue;
          try {
            const data = JSON.parse(line.slice(6));
            if (data.token) {
              fullContent += data.token;
              bubble.textContent = fullContent;
              msgs.scrollTop = msgs.scrollHeight;
            }
            if (data.error) {
              bubble.textContent = 'Error: ' + data.error;
              bubble.parentElement.className = 'chat-message error';
              setConnStatus('error');
            }
            if (data.done && fullContent) {
              history.push({ role: 'assistant', content: fullContent });
            }
          } catch (_) {}
        }
      }
      retryCount = 0;
      if (fullContent) {
        fetch('/memory/' + sessionId, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ kind: 'chat', content: 'User: ' + text + '\nAI: ' + fullContent }),
        }).catch(() => {});
      }
    } catch (err) {
      document.getElementById(tid)?.remove();
      setConnStatus('error');
      if (retryCount < MAX_RETRIES) {
        retryCount++;
        const m = el('div', 'chat-message assistant');
        m.innerHTML = '<div class="msg-bubble retry-notice">Connection issue, retrying (' + retryCount + '/' + MAX_RETRIES + ')…</div>';
        msgs.appendChild(m);
        msgs.scrollTop = msgs.scrollHeight;
        await new Promise(r => setTimeout(r, 1200 * retryCount));
        m.remove();
        return doSend(retryCount);
      }
      addMsg('error', 'Error: ' + err.message + ' (Retries exhausted)');
    } finally {
      send.disabled = false;
    }
  }

  // Probe connection on open
  fetch('/health').then(() => setConnStatus('online')).catch(() => setConnStatus('error'));
});
