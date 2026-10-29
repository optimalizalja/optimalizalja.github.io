// West Kiszámolja – felület (v2: nagy és kis ablak)
const $ = (id) => document.getElementById(id);
const fmt = (x) => Math.round(x).toLocaleString('hu-HU');
const COLOR = { szedett: '#6f8a5a', raktar: '#3f8585', pont: '#c9952f', pot: '#4f6b7a', mas: '#7a4f74',
                elore: '#d9b25a', kesobb: '#c8b48f', veg: '#a4472a' };
let kizart = new Set(), last = null, chart = null, celfv = 'darab';

function toast(msg) { const t = $('toast'); t.textContent = msg; t.classList.add('on'); setTimeout(() => t.classList.remove('on'), 1600); }
function copy(text) {
  navigator.clipboard.writeText(text).then(() => toast('Vágólapra másolva'), () => {
    const a = document.createElement('textarea'); a.value = text; document.body.appendChild(a);
    a.select(); document.execCommand('copy'); a.remove(); toast('Vágólapra másolva'); });
}

// ---------- kizárható receptek ----------
async function loadReceptek() {
  const list = await PY.receptek(+$('szakma').value);
  kizart = new Set();
  $('kizarPanel').innerHTML = list.map(r =>
    `<label><input type="checkbox" data-id="${r.id}"><span class="lv">${r.low}</span>${r.nev}${r.blokk ? ' <span class="blk">blokkidő</span>' : ''}</label>`).join('');
  $('kizarPanel').querySelectorAll('input').forEach(cb => cb.addEventListener('change', () => {
    cb.checked ? kizart.add(+cb.dataset.id) : kizart.delete(+cb.dataset.id);
    $('kizarDb').textContent = kizart.size ? `(${kizart.size})` : '';
  }));
  $('kizarDb').textContent = '';
}

// ---------- tervezés ----------
async function run() {
  document.body.classList.add('loading'); $('hiba').classList.add('hidden');
  const v = (id) => $(id).value === '' ? null : +$(id).value;
  $('busy').classList.remove('hidden');
  await new Promise(res => setTimeout(res, 30));          // hadd rajzolja ki a „Számolás…” jelzést
  const r = await PY.terv(+$('szakma').value, +$('start').value, +$('cel').value, v('wa'), v('wb'),
                          $('blokk').checked, [...kizart], celfv);
  $('busy').classList.add('hidden');
  document.body.classList.remove('loading');
  if (r.hiba) { $('hiba').textContent = 'Nem sikerült a tervezés: ' + r.hiba; $('hiba').classList.remove('hidden'); return; }
  last = r; render(r);
}

function rawTable(rows, total) {
  const max = rows.length ? rows[0].db : 1;
  return '<tr><th>Alapanyag</th><th class="n">Darab</th><th>Legjobb munka</th></tr>' +
    rows.map(x => `<tr><td class="bar"><i style="width:${(x.db / max * 100).toFixed(1)}%"></i><b>${x.nev}</b></td>
      <td class="n">${fmt(x.db)}</td><td class="job">${x.munka || '–'}</td></tr>`).join('') +
    `<tr class="sum"><td>Összesen</td><td class="n">${fmt(total)}</td><td></td></tr>`;
}

function render(r) {
  $('eredmeny').classList.remove('hidden');
  const [a, b] = r.ablak, full = a === r.start && b === r.cel;
  $('sMost').textContent = fmt(r.osszes);
  $('sMostL').textContent = full ? `szedett alapanyag ${a}–${b}` : `szedett alapanyag most (${a}–${b})`;
  $('sTeljes').textContent = fmt(r.teljes.osszes);
  $('sTeljesL').textContent = `alapanyag a teljes úton (${r.start}–${r.cel})`;

  $('tSzedett').innerHTML = rawTable(r.szedett, r.osszes);
  if (r.raktarbol.length) {
    $('raktar').innerHTML = r.raktarbol.map(([n, q]) => `<span class="pill">${n} <b>${fmt(q)}</b></span>`).join('');
    $('raktarWrap').classList.remove('hidden');
  } else $('raktarWrap').classList.add('hidden');

  const el = r.gyartas.filter(g => g.elore > .5);
  if (el.length) {
    $('elore').innerHTML = el.map(g => `<span class="pill">${g.termek} <b>${fmt(g.elore)}</b></span>`).join('');
    $('tOpc').innerHTML = rawTable(r.szedett_opcionalis, r.szedett_opcionalis.reduce((s, x) => s + x.db, 0));
    $('opcWrap').classList.remove('hidden');
  } else $('opcWrap').classList.add('hidden');

  $('tSavok').innerHTML = '<tr><th>Szint</th><th>Mit gyárts pontért</th></tr>' +
    r.savok.map(s => `<tr><td class="sav">${s.tol}–${s.ig}</td><td>${s.gyart.map(g =>
      `<span class="item">${g.recept} <b>${fmt(g.db)}</b><span class="chip ${g.esely > .9 ? 'p96' : 'p50'}">${Math.round(g.esely * 100)}%</span></span>`).join('')}</td></tr>`).join('');

  $('tGyart').innerHTML = '<tr><th>Termék</th><th>Szakma</th><th class="n">Szint</th><th class="n">Pontért</th><th class="n">Pótgyártás</th><th class="n">Most összesen</th><th class="n">Előre (opc.)</th></tr>' +
    r.gyartas.filter(g => g.pont + g.pot > .5 || g.elore > .5).map(g => `<tr>
      <td>${g.termek}${g.szakma !== r.szakma ? '<span class="tag">más szakma</span>' : ''}</td><td class="muted">${g.szakma}</td>
      <td class="n muted">${g.low}</td><td class="n">${g.pont > .5 ? fmt(g.pont) : '–'}</td><td class="n">${g.pot > .5 ? fmt(g.pot) : '–'}</td>
      <td class="n"><b>${g.pont + g.pot > .5 ? fmt(g.pont + g.pot) : '–'}</b></td><td class="n muted">${g.elore > .5 ? fmt(g.elore) : '–'}</td></tr>`).join('');

  drawSankey(r);
}

// ---------- másolás ----------
function listText(title, rows) {
  return `${title}\n` + rows.filter(x => x.db > .5).map(x => `${x.nev}: ${Math.round(x.db)}`).join('\n') +
         `\nÖsszesen: ${Math.round(rows.reduce((s, x) => s + x.db, 0))}`;
}
function copyMost(r) {
  let t = listText(`${r.szakma} ${r.ablak[0]}–${r.ablak[1]} – most kell (várható érték)`, r.szedett);
  const mas = r.gyartas.filter(g => g.szakma !== r.szakma && g.pont + g.pot > .5);
  if (mas.length) t += '\nMás szakmától: ' + mas.map(g => `${g.termek} ${Math.round(g.pont + g.pot)}`).join(', ');
  if (r.raktarbol.length) t += '\nRaktárból: ' + r.raktarbol.map(([n, q]) => `${n} ${Math.round(q)}`).join(', ');
  return t;
}
function copyOpc(r) {
  const el = r.gyartas.filter(g => g.elore > .5);
  return listText(`${r.szakma} ${r.ablak[0]}–${r.ablak[1]} – opcionális, előre legyártható`, r.szedett_opcionalis) +
         '\nElőre gyártható: ' + el.map(g => `${g.termek} ${Math.round(g.elore)}`).join(', ');
}

// ---------- Sankey ----------
function drawSankey(r) {
  const showOpc = $('showOpc').checked;
  const links = r.sankey.links.filter(l => showOpc || !l.opcionalis);
  // a látható áramokból számoljuk újra a csomópontok értékét
  const inflow = {}, outflow = {};
  links.forEach(l => { outflow[l.source] = (outflow[l.source] || 0) + l.value; inflow[l.target] = (inflow[l.target] || 0) + l.value; });
  const used = new Set(links.flatMap(l => [l.source, l.target]));
  const nodes = r.sankey.nodes.filter(n => used.has(n.name));
  const val = (n) => ['szedett', 'raktar'].includes(n.tipus) ? (outflow[n.name] || 0)
                   : ['kesobb', 'veg'].includes(n.tipus) ? (inflow[n.name] || 0) : n.db;
  const byName = Object.fromEntries(nodes.map(n => [n.name, n]));

  const h = Math.max(460, Math.min(2400, nodes.length * 32));
  $('sankey').style.height = h + 'px';
  if (!chart) chart = echarts.init($('sankey'), null, { renderer: 'canvas' });
  chart.resize();
  if (!nodes.length) { chart.clear(); return; }
  chart.setOption({
    animationDuration: 500,
    tooltip: {
      trigger: 'item', confine: true,
      backgroundColor: '#2b2118', borderColor: '#2b2118', textStyle: { color: '#f4ecdd' },
      formatter: (p) => p.dataType === 'edge'
        ? `${p.data.source}<br>→ ${p.data.target}<br><b>${fmt(p.data.value)} db</b>${p.data.opcionalis ? '<br><i>opcionális</i>' : ''}`
        : `<b>${p.name}</b><br>${fmt(val(byName[p.name]))} db`
    },
    series: [{
      type: 'sankey', left: 10, right: 200, top: 10, bottom: 10,
      nodeWidth: 14, nodeGap: 10, nodeAlign: 'justify', layoutIterations: 64, draggable: true,
      emphasis: { focus: 'adjacency' },
      data: nodes.map(n => ({ name: n.name, itemStyle: { color: COLOR[n.tipus], borderColor: COLOR[n.tipus] } })),
      links: links.map(l => ({ ...l, lineStyle: l.opcionalis ? { opacity: 0.22, type: 'dashed' } : undefined })),
      lineStyle: { color: 'gradient', opacity: 0.32, curveness: 0.5 },
      label: {
        color: '#2b2118', fontFamily: 'Source Sans 3', fontSize: 12,
        formatter: (p) => { const n = byName[p.name];
          const name = n.tipus === 'veg' ? n.termek + ' (végtermék)' : p.name;
          return `${name}  {n|${fmt(val(n))}}`; },
        rich: { n: { color: '#6b5a48', fontWeight: 700 } }
      }
    }]
  }, true);
}
window.addEventListener('resize', () => chart && chart.resize());

// ---------- események ----------
$('go').addEventListener('click', run);
$('szakma').addEventListener('change', loadReceptek);
$('kizarBtn').addEventListener('click', () => $('kizarPanel').classList.toggle('hidden'));
$('copyMost').addEventListener('click', () => last && copy(copyMost(last)));
$('copyOpc').addEventListener('click', () => last && copy(copyOpc(last)));
$('showOpc').addEventListener('change', () => last && drawSankey(last));
document.querySelectorAll('#celfv button').forEach(bt => bt.addEventListener('click', () => {
  document.querySelectorAll('#celfv button').forEach(x => x.classList.toggle('on', x === bt));
  celfv = bt.dataset.v;
}));
document.querySelectorAll('input[type=number]').forEach(i => i.addEventListener('keydown', e => { if (e.key === 'Enter') run(); }));

// ---------- Pyodide betöltés ----------
const PY = {};
async function boot() {
  const order = ['py', 'pkg', 'data', 'init'];
  const step = (k, msg) => {
    const i = order.indexOf(k);
    document.querySelectorAll('#steps li').forEach((li, j) => li.className = j < i ? 'done' : j === i ? 'active' : '');
    $('pbar').style.width = (i / order.length * 100 + 6) + '%';
    if (msg) $('loadMsg').textContent = msg;
  };
  try {
    step('py', 'Pyodide letöltése…');
    const pyodide = await loadPyodide();
    step('pkg', 'numpy és scipy betöltése…');
    await pyodide.loadPackage(['numpy', 'scipy'], { messageCallback: (m) => { $('loadMsg').textContent = m; } });
    step('data', 'Adatfájlok letöltése…');
    for (const f of ['planner.py', 'twcalc_data.json', 'twdb_jobs.json']) {
      $('loadMsg').textContent = f + ' letöltése…';
      const txt = await (await fetch('py/' + f, { cache: 'no-cache' })).text();
      pyodide.FS.writeFile('/home/pyodide/' + f, txt);
    }
    step('init', 'Tervező indítása…');
    await pyodide.runPythonAsync(`
import sys, json
sys.path.insert(0, '/home/pyodide')
import planner
def _terv(s):
    try:
        return json.dumps(planner.api_plan(*json.loads(s)))
    except Exception as e:
        return json.dumps({'hiba': str(e)})
def _receptek(s):
    return json.dumps(planner.api_receptek(json.loads(s)))
`);
    const terv = pyodide.globals.get('_terv'), rec = pyodide.globals.get('_receptek');
    PY.terv = async (...a) => JSON.parse(terv(JSON.stringify(a)));
    PY.receptek = async (sz) => JSON.parse(rec(JSON.stringify(sz)));
    document.querySelectorAll('#steps li').forEach(li => li.className = 'done');
    $('pbar').style.width = '100%'; $('loadMsg').textContent = 'Kész!';
    await loadReceptek();
    setTimeout(() => $('loader').classList.add('gone'), 350);
  } catch (e) {
    $('loadMsg').textContent = 'Hiba a betöltésnél: ' + e.message + ' – frissítsd az oldalt.';
    $('loader').classList.add('err');
    console.error(e);
  }
}
boot();
