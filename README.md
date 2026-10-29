# Optimalizálja – szakmatervező (webes verzió)

The West szakmatervező: a legkevesebb szedett alapanyaggal (vagy munkával) a célszintig.
A teljes Python-motor a böngészőben fut [Pyodide](https://pyodide.org) segítségével, szerver nem kell.

## Helyi futtatás
    python -m http.server 8000
majd: http://localhost:8000

## Fájlok
- `index.html`, `app.js`, `style.css` – a felület (ECharts Sankey)
- `py/planner.py` – az LP-motor (scipy/HiGHS)
- `py/twcalc_data.json` – receptek és tárgyak (forrás: tw-calc.net)
- `py/twdb_jobs.json` – munkák és dropesélyek (forrás: tw-db.info)

Nem hivatalos rajongói eszköz.
