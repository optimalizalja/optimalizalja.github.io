"""
TW szakma-tervező mag.

1) plan()      – LP a NAGY ablakra (start -> cel), várható értékre.
                 Cél: legkevesebb szedett alapanyag ('darab') vagy legkevesebb munkaóra ('ora').
2) simulate()  – a megoldást szintről szintre végigjátssza, és minden anyagáramot
                 nyilvántart: honnan jön (szedés / pontszerző gyártás / pótgyártás / raktár)
                 és hová megy.
3) ablak()     – a KIS ablak nézete: mi kell most, mi jön raktárból, mi megy később
                 tovább, és opcionálisan mit lehet már most előre legyártani.

Modell:
  sum_r p(r,s) * x[r,s] = sáv hossza      minden szintsávra (várhatóan ennyi pont)
  gyártott(i) >= felhasznált(i)           köztes termékekre
  min  sum_i suly_i * szedett_i           suly = 1 (darab) vagy óra/darab (munkaóra)
"""
import json, os
import numpy as np
from scipy.optimize import linprog

HERE = os.path.dirname(os.path.abspath(__file__))
P_BIG, P_SMALL = 0.96, 0.50
GOLD_FACTOR = 9.375        # tw-db: arany csillagszintnél a termékesély = alapérték * 9.375 (ezrelék)

DATA = json.load(open(os.path.join(HERE, 'twcalc_data.json'), encoding='utf-8'))
T = {int(k): v for k, v in DATA['targyak'].items()}
R = [dict(r, alapanyag={int(a): c for a, c in r['alapanyag'].items()}) for r in DATA['receptek']]
PN = {int(k): v for k, v in DATA['szakmak'].items()}
RID = {r['id']: r for r in R}
nev = lambda i: T.get(i, {}).get('nev', str(i))

# ---------- munkák: melyik alapanyag honnan esik a legjobban ----------
JOBS = json.load(open(os.path.join(HERE, 'twdb_jobs.json'), encoding='utf-8'))['munkak']
BEST_JOB = {}            # termék -> (alapérték, munka neve, nehézség)
for j in JOBS:
    for pid, v in j['prods']:
        if pid and v > BEST_JOB.get(pid, (0,))[0]:
            BEST_JOB[pid] = (v, j.get('nev_hu', j['name']), j['diff'])


def ora_per_db(i):
    """Becsült munkaóra egy darabra: 1 órás munka, arany csillagszint."""
    if i not in BEST_JOB: return None
    return 1.0 / min(1.0, BEST_JOB[i][0] * GOLD_FACTOR / 1000)


def is_event(r):
    i = r['id']
    return 52000000 <= i < 54500000 or i >= 54800000


# ======================================================================
#  1) LP
# ======================================================================
def plan(szakma, start=0, cel=700, blokkidos=False, kizart=(), extra_bps=(), cel_fv='darab'):
    rec = [r for r in R if not is_event(r) and r['id'] not in kizart
           and (blokkidos or not r['blokkido'])]
    craftable = {r['termek'] for r in rec}
    def ok(i): return i in craftable or T.get(i, {}).get('tipus') in ('mapdrop', 'jobdrop')
    changed = True
    while changed:                      # amit nem lehet beszerezni, az a recept kiesik
        changed = False
        for r in list(rec):
            if not all(ok(i) for i in r['alapanyag']):
                rec.remove(r); changed = True
        craftable = {r['termek'] for r in rec}
    own = [r for r in rec if r['szakma'] == szakma and r['low'] < cel]
    other = [r for r in rec if r['szakma'] != szakma]

    bps = {start, cel} | {v for r in own for v in (r['low'], r['mid'], r['high'])
                          if v is not None and start < v < cel} | {v for v in extra_bps if start < v < cel}
    bps = sorted(bps); segs = list(zip(bps[:-1], bps[1:]))

    var = []
    for r in own:
        for si, (a, b) in enumerate(segs):
            if esely(r, a) > 0: var.append(('x', r, si))
        var.append(('g', r, None))
    for r in other: var.append(('f', r, None))
    raws = sorted({i for r in own + other for i in r['alapanyag'] if i not in craftable})
    for i in raws: var.append(('gy', i, None))
    N = len(var)

    def suly(i):
        if cel_fv == 'ora':
            h = ora_per_db(i)
            return h if h is not None else 50.0     # nincs munkából: drágának vesszük
        return 1.0
    c = np.array([suly(v[1]) if v[0] == 'gy' else 1e-6 for v in var])

    A_eq, b_eq = [], []
    for si, (a, b) in enumerate(segs):
        row = np.zeros(N)
        for k, v in enumerate(var):
            if v[0] == 'x' and v[2] == si: row[k] = esely(v[1], a)
        if not row.any(): raise ValueError(f"A {a}–{b} sávban nincs pontot adó recept")
        A_eq.append(row); b_eq.append(b - a)
    A_ub, b_ub = [], []
    for i in sorted(craftable | set(raws)):
        row = np.zeros(N)
        for k, (t, r, _) in enumerate(var):
            if t in ('x', 'g', 'f'):
                if r['termek'] == i: row[k] -= 1
                row[k] += r['alapanyag'].get(i, 0)
            elif r == i: row[k] -= 1
        if row.any(): A_ub.append(row); b_ub.append(0)
    res = linprog(c, A_ub=np.array(A_ub), b_ub=b_ub, A_eq=np.array(A_eq), b_eq=b_eq,
                  bounds=[(0, None)] * N, method='highs')
    if res.status != 0: raise RuntimeError(res.message)
    X = res.x

    # melyik recepttel gyártjuk az egyes köztes termékeket pótlólag
    recipe_of = {}
    for r in own + other: recipe_of.setdefault(r['termek'], r)
    for k, (t, r, s) in enumerate(var):
        if t in ('g', 'f') and X[k] > 1e-6: recipe_of[r['termek']] = r
    point = []                              # (szint-tól, szint-ig, recept, db, esély)
    for k, (t, r, s) in enumerate(var):
        if t == 'x' and X[k] > 1e-6:
            point.append((segs[s][0], segs[s][1], r, float(X[k]), esely(r, segs[s][0])))
    return dict(szakma=szakma, start=start, cel=cel, point=point, recipe_of=recipe_of, segs=segs)


def esely(r, L):
    if L < r['low']: return 0.0
    mid = r['mid'] if r['mid'] is not None else r['high']
    if L < mid: return P_BIG
    if L < r['high']: return P_SMALL
    return 0.0


# ======================================================================
#  2) Szimuláció: anyagáramok lépésről lépésre
# ======================================================================
def simulate(o, cuts):
    """cuts: lépéshatárok (start..cel). Visszaad: craft-csomópontok és áramok.
       Csomópont kulcs: ('pont'|'pot'|'mas', recept_id, lépés)  vagy ('raw', termék).
       A pontszerző gyártás termékei raktárba kerülnek (FIFO), a hiányzó alapanyagot
       abban a lépésben gyártjuk le pótlólag, ahol először kell."""
    pts = sorted({o['start'], o['cel']} | {c for c in cuts if o['start'] < c < o['cel']})
    steps = list(zip(pts[:-1], pts[1:]))
    recipe_of, own = o['recipe_of'], o['szakma']
    lots = {}          # termék -> [[forrás-kulcs, db], ...]
    crafts = {}        # kulcs -> db
    flows = []         # (forrás, cél, termék, db)
    for k, (a, b) in enumerate(steps):
        queue = []
        for (sa, sb, r, q, p) in o['point']:
            if a <= sa < b:
                key = ('pont', r['id'], k)
                crafts[key] = crafts.get(key, 0) + q
                lots.setdefault(r['termek'], []).append([key, q])
                queue.append((key, r, q))
        while queue:
            node, r, q = queue.pop(0)
            for i, c in r['alapanyag'].items():
                need = c * q
                if i in recipe_of:
                    for lot in lots.get(i, []):
                        if need <= 1e-9: break
                        take = min(lot[1], need)
                        if take > 1e-9:
                            lot[1] -= take; need -= take
                            flows.append((lot[0], node, i, take))
                    if need > 1e-9:
                        r2 = recipe_of[i]
                        key2 = ('pot' if r2['szakma'] == own else 'mas', r2['id'], k)
                        crafts[key2] = crafts.get(key2, 0) + need
                        flows.append((key2, node, i, need))
                        queue.append((key2, r2, need))
                else:
                    flows.append((('raw', i), node, i, need))
    for i, ls in lots.items():                       # ami a végén megmarad: végtermék
        for src, q in ls:
            if q > 1e-6: flows.append((src, ('veg', i), i, q))
    return steps, crafts, flows


# ======================================================================
#  3) Kis ablak nézete
# ======================================================================
def ablak(o, a, b):
    steps, crafts, flows = simulate(o, [a, b])
    w = next(k for k, s in enumerate(steps) if s == (a, b))
    own = o['szakma']

    def step_of(key): return key[2] if key[0] in ('pont', 'pot', 'mas') else None
    def rlabel(rid):
        r = RID[rid]
        return nev(r['termek']) + ('' if r['szakma'] == own else f" ({PN[r['szakma']]})")

    # ---- előre legyártható: későbbi pót-/más szakmás gyártás, ami már most elérhető ----
    #  = ugyanannak a saját receptnek a későbbi pótgyártása, amit most is gyártasz,
    #    plusz azok a későbbi gyártások, amik ehhez alapanyagot adnak (pl. Faszén, Gyanta).
    window_recipes = {kk[1] for kk in crafts if kk[0] in ('pont', 'pot') and kk[2] == w}
    cand = {kk for kk in crafts if kk[0] == 'pot' and kk[2] > w and kk[1] in window_recipes}
    changed = True
    while changed:          # alapanyag-függőségek hozzávétele
        changed = False
        for (src, dst, i, q) in flows:
            if dst in cand and src[0] in ('pot', 'mas') and src[2] > w and src not in cand:
                cand.add(src); changed = True
    changed = True
    while changed:          # ami most még nem gyártható (saját recept, szint > ablak vége), kiesik a láncával
        changed = False
        for kk in list(cand):
            r = RID[kk[1]]
            bad = r['szakma'] == own and r['low'] >= b
            bad = bad or any(dst == kk and src[0] in ('pont', 'pot', 'mas') and src[2] > w and src not in cand
                             for (src, dst, i, q) in flows)
            if bad: cand.discard(kk); changed = True
    elore = cand
    # arány: a függőség-csomópontból mekkora rész jut az előre gyártott termékekre
    top = {kk for kk in elore if kk[1] in window_recipes}
    frac = {kk: 1.0 for kk in top}
    for _ in range(len(elore) + 1):
        for kk in elore - top:
            tot = sum(q * frac.get(dst, 0) for (src, dst, i, q) in flows if src == kk and dst in elore)
            frac[kk] = min(1.0, tot / crafts[kk]) if crafts[kk] > 0 else 0.0

    def node_name(key, role):
        t = key[0]
        if t == 'raw': return nev(key[1])
        if t == 'veg': return f"{nev(key[1])} · végtermék"
        if key in elore: return f"{rlabel(key[1])} · előre"
        if t == 'pont': return f"{rlabel(key[1])} · pontért"
        if t == 'pot': return f"{rlabel(key[1])} · pótgyártás"
        return rlabel(key[1])                                   # más szakma

    def kind(key):
        if key[0] == 'raw': return 'szedett'
        if key[0] == 'veg': return 'veg'
        if key in elore: return 'elore'
        return key[0]

    links, nodes = {}, {}
    def add_node(name, tipus, termek, db=0):
        n = nodes.setdefault(name, dict(tipus=tipus, termek=termek, db=0.0)); n['db'] += db
    def add_link(s, t, v, opt):
        if v > 1e-6:
            l = links.setdefault((s, t), [0.0, opt]); l[0] += v

    in_window = lambda key: key[0] in ('pont', 'pot', 'mas') and key[2] == w
    raw_now, raw_opt, stock_now = {}, {}, {}
    for (src, dst, i, q) in flows:
        dst_in, dst_opt = in_window(dst), dst in elore
        src_in, src_opt = in_window(src), src in elore
        if dst_opt: q = q * frac.get(dst, 1.0)
        if dst_in or dst_opt:
            opt = dst_opt
            if src[0] == 'raw':
                sname = nev(i); add_node(sname, 'szedett', nev(i))
                (raw_opt if opt else raw_now)[nev(i)] = (raw_opt if opt else raw_now).get(nev(i), 0) + q
            elif src_in or src_opt:
                sname = node_name(src, 'src')
            else:                                    # korábbi lépésből: raktár
                sname = f"{nev(i)} · raktárból"; add_node(sname, 'raktar', nev(i))
                stock_now[nev(i)] = stock_now.get(nev(i), 0) + q
            add_link(sname, node_name(dst, 'dst'), q, opt)
        elif src_in or (src_opt and frac.get(src, 1.0) > 0.999):   # innen megy tovább később / végtermék
            if dst[0] == 'veg':
                tname = f"{nev(i)} · végtermék"; add_node(tname, 'veg', nev(i))
            else:
                tname = f"→ később: {rlabel(dst[1])}"; add_node(tname, 'kesobb', rlabel(dst[1]))
            add_link(node_name(src, 'src'), tname, q, src_opt)
    for key, q in crafts.items():
        if in_window(key) or key in elore:
            add_node(node_name(key, ''), kind(key), rlabel(key[1]), q * frac.get(key, 1.0))
    # a szedett/raktár/később csomópontok mennyisége = rajtuk átfolyó áram
    for (s, t), (v, opt) in links.items():
        if nodes.get(s, {}).get('tipus') in ('szedett', 'raktar'): nodes[s]['db'] += v
        if nodes.get(t, {}).get('tipus') in ('kesobb', 'veg'): nodes[t]['db'] += v

    # ---- táblázatok ----
    gy = {}
    for key, q in crafts.items():
        if not (in_window(key) or key in elore): continue
        g = gy.setdefault(key[1], dict(termek=rlabel(key[1]), szakma=PN[RID[key[1]]['szakma']],
                                       low=RID[key[1]]['low'], pont=0.0, pot=0.0, elore=0.0))
        g['elore' if key in elore else ('pont' if key[0] == 'pont' else 'pot')] += q * frac.get(key, 1.0)
    savok = []
    for (sa, sb) in o['segs']:
        if a <= sa < b:
            sg = [dict(recept=rlabel(r['id']), db=q, esely=p) for (x, y, r, q, p) in o['point'] if x == sa]
            sig = sorted((g['recept'], g['esely']) for g in sg)
            prev = savok[-1] if savok else None
            if prev and prev['ig'] == sa and sorted((g['recept'], g['esely']) for g in prev['gyart']) == sig:
                prev['ig'] = sb                 # azonos recept és esély: összevonjuk az előzővel
                for g, h in zip(sorted(prev['gyart'], key=lambda g: g['recept']), sorted(sg, key=lambda g: g['recept'])):
                    g['db'] += h['db']
            else:
                savok.append(dict(tol=sa, ig=sb, gyart=sg))
    def rawrows(d):
        rows = []
        for n, q in sorted(d.items(), key=lambda x: -x[1]):
            i = next((k for k, v in T.items() if v['nev'] == n and v['tipus'] in ('mapdrop', 'jobdrop')), None)
            h = ora_per_db(i) if i else None
            bj = BEST_JOB.get(i)
            rows.append(dict(nev=n, db=q, ora=(q * h if h else None), munka=bj[1] if bj else None))
        return rows
    return dict(
        ablak=[a, b],
        szedett=rawrows(raw_now), szedett_opcionalis=rawrows(raw_opt),
        raktarbol=sorted(([n, q] for n, q in stock_now.items()), key=lambda x: -x[1]),
        gyartas=sorted(gy.values(), key=lambda g: (g['szakma'] != PN[own], g['low'], g['termek'])),
        savok=savok,
        sankey=dict(nodes=[dict(name=n, **d) for n, d in nodes.items()],
                    links=[dict(source=s, target=t, value=round(v, 2), opcionalis=opt)
                           for (s, t), (v, opt) in links.items()]))


# ======================================================================
#  Eel API
# ======================================================================
def api_plan(szakma, start, cel, ablak_tol=None, ablak_ig=None, blokkidos=False, kizart=(), cel_fv='darab'):
    start, cel = int(start), int(cel)
    a = int(ablak_tol) if ablak_tol not in (None, '') else start
    b = int(ablak_ig) if ablak_ig not in (None, '') else cel
    a, b = max(start, min(a, cel)), max(start, min(b, cel))
    if b <= a: a, b = start, cel
    o = plan(int(szakma), start, cel, bool(blokkidos), tuple(int(k) for k in kizart), (a, b), cel_fv)
    teljes = ablak(o, start, cel)
    kis = ablak(o, a, b) if (a, b) != (start, cel) else teljes
    res = dict(szakma=PN[int(szakma)], start=start, cel=cel, cel_fv=cel_fv,
               teljes=dict(szedett=teljes['szedett'],
                           osszes=sum(r['db'] for r in teljes['szedett']),
                           ora=sum(r['ora'] or 0 for r in teljes['szedett'])),
               **kis)
    res['osszes'] = sum(r['db'] for r in kis['szedett'])
    res['ora'] = sum(r['ora'] or 0 for r in kis['szedett'])
    return json.loads(json.dumps(res, default=float))


def api_receptek(szakma):
    return [dict(id=r['id'], nev=nev(r['termek']), low=r['low'], blokk=bool(r['blokkido']))
            for r in sorted(R, key=lambda r: (r['low'], r['id']))
            if r['szakma'] == int(szakma) and not is_event(r)]


if __name__ == '__main__':
    import sys
    sz = int(sys.argv[1]) if len(sys.argv) > 1 else 3
    r = api_plan(sz, 0, 700, *(sys.argv[2:4] if len(sys.argv) > 3 else (None, None)))
    print(r['szakma'], r['ablak'], 'most:', round(r['osszes']), 'teljes:', round(r['teljes']['osszes']))
    for x in r['szedett']: print(f"  {x['nev']:<20}{x['db']:8.1f}")
