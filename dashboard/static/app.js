(() => {
  'use strict';

  const tokenKey = 'morpheus-control-tower-token';
  const trackedRunKey = 'morpheus-control-tower-tracked-run';
  const tokenLabels = { ACCEPTED:'Angenommen', BASELINING:'Baseline wird erstellt', RESEARCHING:'Recherche läuft', PLANNING:'Planung läuft', PLAN_BLOCKED:'Planung blockiert', BUILDING:'Build läuft', VERIFYING:'Verifikation läuft', REVIEWING:'Review läuft', DECIDING:'Entscheidung läuft', RUNNING:'Läuft', ACTIVE:'Aktiv', WAITING:'Wartet', QUEUED:'Eingereiht', DONE:'Abgeschlossen', COMPLETED:'Abgeschlossen', FAILED:'Fehlgeschlagen', BLOCKED:'Blockiert', SPLIT_REQUIRED:'Aufteilung erforderlich', UNKNOWN:'Unbekannt' };
  const jobLabels = { baseline:'Baseline', research:'Recherche', plan:'Planung', build:'Build', verify:'Verifikation', review:'Review', decision:'Entscheidung', terminal:'Abschluss' };
  const decisionLabels = { DONE:'Abgeschlossen', BLOCKED:'Blockiert', RETRY:'Erneut versuchen', FIX:'Korrektur erforderlich', SPLIT:'Aufteilen', SPLIT_REQUIRED:'Aufteilung erforderlich', UNKNOWN:'Unbekannt' };
  const healthLabels = { HEALTHY:'OK', DEGRADED:'Eingeschränkt', UNAVAILABLE:'Nicht verfügbar', UNKNOWN:'Unbekannt', STALE:'Veraltet' };
  const severityLabels = { CRITICAL:'Kritisch', HIGH:'Hoch', WARNING:'Warnung', INFO:'Information' };
  const eventLabels = { ATTEMPT_STARTED:'Versuch gestartet', ATTEMPT_FINISHED:'Versuch beendet', JOB_COMPLETED:'Schritt abgeschlossen', JOB_FAILED:'Schritt fehlgeschlagen' };
  const reasonLabels = { INTAKE_OK:'Aufgabe angenommen', START_BASELINE:'Baseline gestartet', BASELINE_OK:'Baseline erfolgreich', RESEARCH_OK:'Recherche erfolgreich', START_PLAN:'Planung gestartet', PLAN_MISSING:'Plan fehlt', BUILD_FAILED:'Build fehlgeschlagen', VERIFY_FAILED:'Verifikation fehlgeschlagen' };
  const alertLabels = { FREE_POOL_BELOW_MIN:'Weniger als zwei kostenlose Anbieter sind verfügbar.', PAID_ESCALATION_ENABLED:'Automatische kostenpflichtige Eskalation ist aktiviert.', N8N_UNAVAILABLE:'n8n ist nicht verfügbar.', ADAPTER_UNAVAILABLE:'Der Harness-Adapter ist nicht verfügbar.', STALE_ACTIVE_RUN:'Ein aktiver Lauf wurde seit längerer Zeit nicht aktualisiert.' };
  const activeStates = new Set(['ACCEPTED','BASELINING','RESEARCHING','PLANNING','PLAN_BLOCKED','BUILDING','VERIFYING','REVIEWING','DECIDING','RUNNING','ACTIVE']);
  const terminalStates = new Set(['DONE','COMPLETED','FAILED','BLOCKED','SPLIT_REQUIRED']);

  // Trusted, version-controlled topology. Live values only select known nodes/classes below.
  const FLOW_TOPOLOGY = Object.freeze({
    system: `flowchart LR
      SYS_USER["Auftrag / API"] --> SYS_START["00 Start"]
      SYS_START --> SYS_ORCH["01 Orchestrator"]
      SYS_ORCH <--> SYS_RUN[("Run- / Attempt-Daten")]
      SYS_ORCH --> SYS_BASE["10 Baseline"]
      SYS_BASE --> SYS_RESEARCH["20 Recherche"]
      SYS_RESEARCH --> SYS_PLAN["30 Planung"]
      SYS_PLAN --> SYS_GATE["Plan-Gate"]
      SYS_GATE --> SYS_BUILD["40 Build"]
      SYS_BUILD --> SYS_VERIFY["50 Verifikation"]
      SYS_VERIFY --> SYS_REVIEW["60 Review"]
      SYS_REVIEW --> SYS_DECIDE["70 Entscheidung"]
      SYS_DECIDE -->|FIX| SYS_FIX["80 Korrektur"]
      SYS_FIX --> SYS_VERIFY
      SYS_DECIDE -->|SPLIT| SYS_SPLIT["90 Aufteilung"]
      SYS_DECIDE -->|DONE| SYS_GITHUB["GitHub Issue"]
      SYS_GITHUB --> SYS_BRANCH["Feature Branch"]
      SYS_BRANCH --> SYS_PR["Pull Request"]
      SYS_PR --> SYS_MERGE["Automatischer Merge"]
      SYS_MERGE --> SYS_POST["Post-Merge Verify"]
      SYS_BUILD --> SYS_ADAPTER["Harness Adapter"]
      SYS_VERIFY --> SYS_ADAPTER
      SYS_REVIEW --> SYS_ADAPTER
      SYS_ADAPTER --> SYS_CT["CT8001"]
      SYS_CT --> SYS_OC["OpenCode"]
      SYS_OC --> SYS_ROUTER{"Provider-Routing"}
      SYS_ROUTER --> SYS_OPENROUTER["OpenRouter"]
      SYS_ROUTER --> SYS_OLLAMA["Ollama"]
      SYS_ROUTER --> SYS_LMSTUDIO["LM Studio"]
      SYS_RUN -. read-only .-> SYS_DASH["Morpheus Leitstand"]
      SYS_ADAPTER -. read-only .-> SYS_DASH
      classDef current stroke:#f4c95d,stroke-width:4px,fill:#5b4714
      classDef blocked stroke:#ff6f79,stroke-width:4px,fill:#57202a
      classDef failed stroke:#ff6f79,stroke-width:4px,fill:#57202a`,
    data: `flowchart LR
      DF_REQUEST["User Request"] --> DF_INTAKE["Intake Payload"]
      DF_INTAKE --> DF_RUN[("Run Record")]
      DF_RUN --> DF_BASE["Baseline Result"]
      DF_BASE --> DF_RESEARCH["Research Result"]
      DF_RESEARCH --> DF_PLAN["autodev.plan.v1"]
      DF_PLAN --> DF_GATE["Plan Gate"]
      DF_GATE --> DF_BUILD_INPUT["Build Input"]
      DF_BUILD_INPUT --> DF_BUILD_RESULT["autodev.build-result.v1"]
      DF_BUILD_RESULT --> DF_PROVENANCE["Build Provenance Manifest"]
      DF_BUILD_RESULT --> DF_VERIFY["Verify Result"]
      DF_VERIFY --> DF_REVIEW["Review Results"]
      DF_REVIEW --> DF_DECISION["Decision Result"]
      DF_DECISION --> DF_DELTA["Git Delta"]
      DF_DELTA --> DF_MANIFEST["Delivery Manifest"]
      DF_MANIFEST --> DF_PR["Pull Request"]
      DF_PR --> DF_MERGE["Merge Commit"]
      DF_MERGE --> DF_POST["Post-Merge Result"]
      DF_POST --> DF_TERMINAL["Terminal Run State"]
      DF_TERMINAL --> DF_RUN
      DF_RUN -. read-only .-> DF_PROJECTION["Control-Tower-Projektion"]
      DF_PROVENANCE -. read-only .-> DF_PROJECTION
      classDef current stroke:#f4c95d,stroke-width:4px,fill:#5b4714
      classDef blocked stroke:#ff6f79,stroke-width:4px,fill:#57202a
      classDef failed stroke:#ff6f79,stroke-width:4px,fill:#57202a`
  });

  const SYSTEM_STAGE = Object.freeze({ ACCEPTED:'SYS_START', BASELINING:'SYS_BASE', RESEARCHING:'SYS_RESEARCH', PLANNING:'SYS_PLAN', PLAN_BLOCKED:'SYS_GATE', BUILDING:'SYS_BUILD', VERIFYING:'SYS_VERIFY', REVIEWING:'SYS_REVIEW', DECIDING:'SYS_DECIDE', SPLIT_REQUIRED:'SYS_SPLIT', DONE:'SYS_POST', COMPLETED:'SYS_POST' });
  const DATA_STAGE = Object.freeze({ ACCEPTED:'DF_INTAKE', BASELINING:'DF_BASE', RESEARCHING:'DF_RESEARCH', PLANNING:'DF_PLAN', PLAN_BLOCKED:'DF_GATE', BUILDING:'DF_BUILD_RESULT', VERIFYING:'DF_VERIFY', REVIEWING:'DF_REVIEW', DECIDING:'DF_DECISION', SPLIT_REQUIRED:'DF_DECISION', DONE:'DF_TERMINAL', COMPLETED:'DF_TERMINAL' });
  const JOB_STAGE = Object.freeze({ baseline:'SYS_BASE', research:'SYS_RESEARCH', plan:'SYS_PLAN', build:'SYS_BUILD', verify:'SYS_VERIFY', review:'SYS_REVIEW', decision:'SYS_DECIDE', terminal:'SYS_POST' });
  const DATA_JOB_STAGE = Object.freeze({ baseline:'DF_BASE', research:'DF_RESEARCH', plan:'DF_PLAN', build:'DF_BUILD_RESULT', verify:'DF_VERIFY', review:'DF_REVIEW', decision:'DF_DECISION', terminal:'DF_TERMINAL' });
  const STAGE_LABELS = Object.freeze({ SYS_START:'00 Start / Orchestrator', SYS_BASE:'10 Baseline', SYS_RESEARCH:'20 Recherche', SYS_PLAN:'30 Planung', SYS_GATE:'Plan-Gate', SYS_BUILD:'40 Build', SYS_VERIFY:'50 Verifikation', SYS_REVIEW:'60 Review', SYS_DECIDE:'70 Entscheidung', SYS_FIX:'80 Korrektur', SYS_SPLIT:'90 Aufteilung', SYS_POST:'Post-Merge Verify', SYS_STATUS:'Letzter beobachteter Schritt', DF_INTAKE:'Intake Payload', DF_BASE:'Baseline Result', DF_RESEARCH:'Research Result', DF_PLAN:'autodev.plan.v1', DF_GATE:'Plan Gate', DF_BUILD_INPUT:'Build Input', DF_BUILD_RESULT:'autodev.build-result.v1', DF_PROVENANCE:'Build Provenance Manifest', DF_VERIFY:'Verify Result', DF_REVIEW:'Review Results', DF_DECISION:'Decision Result', DF_DELTA:'Git Delta', DF_MANIFEST:'Delivery Manifest', DF_PR:'Pull Request', DF_MERGE:'Merge Commit', DF_POST:'Post-Merge Result', DF_TERMINAL:'Terminaler Lauf', DF_PROJECTION:'Control-Tower-Projektion' });
  const PROVIDER_NODES = Object.freeze({ openrouter:'SYS_OPENROUTER', ollama:'SYS_OLLAMA', lmstudio:'SYS_LMSTUDIO', 'lm-studio':'SYS_LMSTUDIO' });

  let token = sessionStorage.getItem(tokenKey);
  let timer;
  let latestOverview = null;
  let rendering = false;
  const diagrams = { system: { rendered:false, promise:null, container:'system-map-diagram', fallback:'system-map-fallback' }, data: { rendered:false, promise:null, container:'data-flow-diagram', fallback:'data-flow-fallback' } };
  const $ = id => document.getElementById(id);
  const esc = s => String(s ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const translate = (map, value, prefix='Technischer Wert') => { const raw = String(value ?? 'UNKNOWN'); return map[raw] || `${prefix}: ${raw}`; };
  const state = value => translate(tokenLabels, value);
  const job = value => translate(jobLabels, value);
  const decision = value => translate(decisionLabels, value);
  const health = value => translate(healthLabels, value);
  const boolean = value => value === true ? 'Ja' : value === false ? 'Nein' : 'Nicht bekannt';
  const reason = value => translate(reasonLabels, value, 'Technischer Grund');
  const event = value => translate(eventLabels, value, 'Technisches Ereignis');
  const severity = value => translate(severityLabels, value, 'Technische Einstufung');
  const formatTimestamp = value => { if (!value) return 'Nicht bekannt'; const date = new Date(value); return Number.isNaN(date.getTime()) ? 'Nicht bekannt' : new Intl.DateTimeFormat('de-DE', {dateStyle:'medium', timeStyle:'medium', hour12:false, timeZone:'Europe/Berlin'}).format(date); };
  const api = async path => { const response = await fetch(path, {headers:{'X-Control-Tower-Token':token}}); if (response.status === 401) throw Error('AUTH'); return response.json(); };
  const badge = (label, value) => `<span class="badge ${String(value).toLowerCase()}">${esc(label)}: ${esc(value)}</span>`;
  const cell = (value, key) => key === 'state' ? state(value) : key === 'current_job' || key === 'job' ? job(value) : key === 'decision' ? decision(value || 'UNKNOWN') : key === 'health' ? health(value) : key === 'free_eligible' || key === 'promoted' || key === 'quarantined' ? boolean(value) : key === 'updated_at' || key === 'timestamp' ? formatTimestamp(value) : key === 'event' ? event(value) : String(value ?? 'Nicht bekannt');
  const table = (rows, cols) => `<div class="table-wrap"><table><thead><tr>${cols.map(c => `<th scope="col">${esc(c[1])}</th>`).join('')}</tr></thead><tbody>${rows.map(row => `<tr>${cols.map(c => `<td>${esc(cell(row[c[0]], c[0]))}</td>`).join('')}</tr>`).join('')}</tbody></table></div>`;
  const timestamp = run => { const value = run && (run.updated_at || run.ended_at || run.created_at); const parsed = value ? Date.parse(value) : NaN; return Number.isNaN(parsed) ? -Infinity : parsed; };
  const isActive = run => activeStates.has(String(run?.state || '').toUpperCase());
  const chooseTrackedRun = runs => { const list = Array.isArray(runs) ? runs : []; const saved = sessionStorage.getItem(trackedRunKey); const explicit = list.find(run => run.run_id === saved); if (explicit) return explicit; const active = list.filter(isActive).sort((a,b) => timestamp(b) - timestamp(a))[0]; if (active) return active; return list.filter(run => terminalStates.has(String(run.state || '').toUpperCase())).sort((a,b) => timestamp(b) - timestamp(a))[0] || list.slice().sort((a,b) => timestamp(b) - timestamp(a))[0] || null; };
  const providerNode = run => { const raw = String(run?.actual_provider || run?.selected_provider || '').toLowerCase().replace(/\s+/g, ''); return Object.entries(PROVIDER_NODES).find(([key]) => raw.includes(key))?.[1] || null; };
  const systemNodeFor = run => { const stateValue = String(run?.state || '').toUpperCase(); const currentJob = String(run?.current_job || run?.job || '').toLowerCase(); return SYSTEM_STAGE[stateValue] || JOB_STAGE[currentJob] || 'SYS_STATUS'; };
  const dataNodeFor = run => { const stateValue = String(run?.state || '').toUpperCase(); const currentJob = String(run?.current_job || run?.job || '').toLowerCase(); return DATA_STAGE[stateValue] || DATA_JOB_STAGE[currentJob] || 'DF_RUN'; };
  const statusClass = run => { const value = String(run?.state || '').toUpperCase(); return value === 'BLOCKED' || value === 'PLAN_BLOCKED' ? 'blocked' : value === 'FAILED' ? 'failed' : ''; };
  const positionText = (run, node, kind) => { const status = statusClass(run); const prefix = status === 'blocked' ? 'Blockiert' : status === 'failed' ? 'Fehlgeschlagen' : 'Aktuelle Position'; const provider = run?.actual_provider || run?.selected_provider; const model = run?.actual_model || run?.selected_model || run?.resolved_model; const worker = provider ? ` · Anbieter: ${provider}${model ? ` · Modell: ${model}` : ''}` : ''; return `${prefix}: ${STAGE_LABELS[node] || (kind === 'system' ? state(run?.state) : 'Run Record')}${worker}`; };

  function show(view) { document.querySelectorAll('.view').forEach(x => { x.hidden = x.id !== `${view}-view`; }); document.querySelectorAll('.tabs button').forEach(x => x.setAttribute('aria-current', x.dataset.view === view ? 'page' : 'false')); }
  async function detail(id) { const d = await api(`/api/v1/runs/${encodeURIComponent(id)}`); $('detail').hidden = false; $('detail').innerHTML = `<h2>Lauf ${esc(d.run_id)}</h2><p>${badge('Status', state(d.state))} ${badge('Entscheidung', decision(d.decision || 'UNKNOWN'))}</p><p>Grund: ${esc(reason(d.reason_code || 'NOT_RECORDED'))}</p><h3>Beobachteter Versuchsverlauf</h3><p class="warn">Für nicht beobachtete Übergänge ist kein exakter Zeitpunkt gespeichert.</p>${table(d.timeline || [], [['event','Ereignis'],['timestamp','Zeitpunkt'],['job_id','Schritt'],['attempt_id','Versuch'],['provider','Anbieter'],['model','Modell'],['status','Status']])}`; show('runs'); $('detail').scrollIntoView({block:'start'}); }
  function renderCounts(counts) { const labels = {running:'Läuft', waiting:'Wartet', done_24h:'Abgeschlossen · 24 Std.', failed_24h:'Fehlgeschlagen/Blockiert · 24 Std.'}; return Object.entries(counts).map(([key,value]) => `<div><strong>${esc(value)}</strong><span>${esc(labels[key] || `Technischer Wert: ${key}`)}</span></div>`).join(''); }

  function updateRunSelectors(runs, selected) { ['system-map-run','data-flow-run'].forEach(id => { const select = $(id); const before = select.value; select.innerHTML = ''; (runs || []).forEach(run => { const option = document.createElement('option'); option.value = String(run.run_id || ''); option.textContent = `${run.run_id || 'Unbekannter Lauf'} · ${state(run.state)}`; select.appendChild(option); }); select.value = selected?.run_id || before || ''; }); }
  function svgNode(svg, nodeId) { return Array.from(svg.querySelectorAll('g.node')).find(node => node.id.includes(nodeId)); }
  function applyDiagramState(kind, run) { const diagram = diagrams[kind]; const svg = $(diagram.container)?.querySelector('svg'); if (!svg || !run) return; const stageNode = kind === 'system' ? systemNodeFor(run) : dataNodeFor(run); const ids = new Set([stageNode]); const provider = kind === 'system' ? providerNode(run) : null; if (provider) ['SYS_ADAPTER','SYS_CT','SYS_OC',provider].forEach(id => ids.add(id)); Array.from(svg.querySelectorAll('g.node')).forEach(node => { node.classList.remove('current','blocked','failed'); node.removeAttribute('aria-label'); node.removeAttribute('data-current'); }); ids.forEach(id => { const node = svgNode(svg, id); if (!node) return; node.classList.add('current'); const status = statusClass(run); if (status) node.classList.add(status); node.setAttribute('aria-label', positionText(run, id, kind)); node.setAttribute('data-current', 'true'); }); const context = $(`${diagram.container.replace('-diagram','-context')}`); if (context) context.textContent = `Verfolgter Lauf: ${run.run_id || 'Nicht bekannt'} · ${positionText(run, stageNode, kind)}`; }
  async function renderDiagram(kind) { const diagram = diagrams[kind]; if (diagram.rendered) return; if (diagram.promise) return diagram.promise; diagram.promise = (async () => { try { if (!window.mermaid) throw Error('Lokale Mermaid-Runtime nicht verfügbar.'); window.mermaid.initialize({startOnLoad:false, securityLevel:'strict', theme:'dark', deterministicIds:true, maxTextSize:100000}); const output = await window.mermaid.render(`morpheus-${kind}-diagram`, FLOW_TOPOLOGY[kind]); $(diagram.container).innerHTML = output.svg; diagram.rendered = true; $(diagram.fallback).hidden = true; if (latestOverview) applyDiagramState(kind, chooseTrackedRun(latestOverview.recent_runs)); } catch (error) { $(diagram.fallback).hidden = false; $(diagram.fallback).textContent = `Diagramm konnte nicht geladen werden: ${error.message}`; } finally { diagram.promise = null; } })(); return diagram.promise; }
  async function updateFlowMaps(data) { latestOverview = data; const run = chooseTrackedRun(data?.recent_runs || []); updateRunSelectors(data?.recent_runs || [], run); ['system','data'].forEach(kind => { if (diagrams[kind].rendered) applyDiagramState(kind, run); }); await Promise.all(['system','data'].map(renderDiagram)); }
  function selectTrackedRun(value) { if (value) sessionStorage.setItem(trackedRunKey, value); else sessionStorage.removeItem(trackedRunKey); if (latestOverview) updateFlowMaps(latestOverview); }

  async function render() { if (rendering) return; rendering = true; try { const data = await api('/api/v1/overview'); latestOverview = data; $('login').hidden = true; $('dashboard').hidden = false; $('freshness').textContent = `Live-Quellen · aktualisiert ${formatTimestamp(data.generated_at)}`; $('health').innerHTML = Object.entries(data.system_health).map(([key,value]) => `<article class="health panel">${badge(key === 'provider_pool' ? 'Anbieter-Pool' : key, health(value.status))}<small>${esc(formatTimestamp(value.checked_at))}</small></article>`).join(''); $('counts').innerHTML = renderCounts(data.run_counts); $('pool').innerHTML = data.free_pool.providers.length ? data.free_pool.providers.map(p => `<p>${badge('Anbieter', p.provider)} ${badge('Zustand', health(p.health || 'UNKNOWN'))} <code>${esc(p.model)}</code></p>`).join('') : '<p class="warn">Kein geeigneter kostenloser Anbieter verfügbar</p>'; $('recent').innerHTML = table(data.recent_runs, [['run_id','Lauf-ID'],['state','Status'],['current_job','Aktueller Schritt'],['decision','Entscheidung'],['selected_provider','Anbieter'],['updated_at','Aktualisiert']]) + '<p><button class="run-link" data-run="run-mt6unuge-agsdu4">Referenzlauf „Golden Journey“</button> <button class="run-link" data-run="run-mt6uony8-jjp9hf">Referenzlauf „Fehlerbehebung“</button></p>'; $('alerts').innerHTML = data.alerts.length ? data.alerts.map(a => `<p>${badge('Einstufung', severity(a.severity))} ${esc(alertLabels[a.code] || `Technischer Grund: ${a.code || a.message}`)}</p>`).join('') : '<p class="ok">Keine aktiven Warnungen</p>'; const runtime = await api('/api/v1/runtime'); $('providers').innerHTML = table(runtime.providers || [], [['provider','Anbieter'],['model','Modell'],['health','Zustand'],['cost_class','Kostenklasse'],['free_eligible','Kostenfrei zulässig'],['promoted','Freigegeben'],['quarantined','In Quarantäne']]); $('runs').innerHTML = table(data.recent_runs, [['run_id','Lauf-ID'],['state','Status'],['current_job','Schritt'],['attempt_count','Versuche'],['selected_provider','Anbieter'],['updated_at','Aktualisiert']]); document.querySelectorAll('.run-link').forEach(button => button.addEventListener('click', () => detail(button.dataset.run))); await updateFlowMaps(data); } catch (error) { if (error.message === 'AUTH') { sessionStorage.removeItem(tokenKey); $('login').hidden = false; $('dashboard').hidden = true; $('login-error').textContent = 'Authentifizierung fehlgeschlagen.'; } else $('freshness').textContent = 'Eingeschränkt: Quelldaten nicht verfügbar'; } finally { rendering = false; } }

  $('login-form').addEventListener('submit', eventObject => { eventObject.preventDefault(); token = $('token').value; sessionStorage.setItem(tokenKey, token); render(); clearInterval(timer); timer = setInterval(render, 5000); });
  document.querySelectorAll('.tabs button').forEach(button => button.addEventListener('click', () => { show(button.dataset.view); if (button.dataset.view === 'system-map') renderDiagram('system'); if (button.dataset.view === 'data-flow') renderDiagram('data'); }));
  ['system-map-run','data-flow-run'].forEach(id => $(id).addEventListener('change', eventObject => selectTrackedRun(eventObject.target.value)));
  $('run-search').addEventListener('input', eventObject => { const query = eventObject.target.value.toLowerCase(); document.querySelectorAll('#runs tbody tr').forEach(row => { row.hidden = query && !row.textContent.toLowerCase().includes(query); }); });
  document.addEventListener('visibilitychange', () => { if (document.hidden) clearInterval(timer); else { render(); timer = setInterval(render, 5000); } });
  window.__morpheusFlow = { chooseTrackedRun, systemNodeFor, dataNodeFor, FLOW_TOPOLOGY };
  if (token) { render(); timer = setInterval(render, 5000); }
})();
