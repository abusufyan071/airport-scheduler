"""Airport Runway Scheduling System - OS concepts demo.
Aircraft=Process | Runway/Gate/Crew=Resources | Priority scheduling + aging |
Deadlock prevention (all-or-nothing request + resource ordering)."""
import os
import sqlite3
from flask import Flask, jsonify, request, render_template

BASE = os.path.dirname(os.path.abspath(__file__))
DB = os.path.join(BASE, "airport.db")
app = Flask(__name__)

PRIORITY = {"Emergency": 10, "Medical": 9, "VIP": 8, "Normal": 5, "Cargo": 4, "Training": 2}
ORDER = ["Runway", "Gate", "Crew"]          # global resource ordering
RESOURCES = [(f"{k} {i}", k) for k in ORDER for i in (1, 2)]
DURATION = 3        # ticks an aircraft uses its resources
AGING_EVERY = 3     # ticks of waiting before priority +1
AGING_CAP = 9       # aging never outranks a true emergency


def db():
    c = sqlite3.connect(DB)
    c.row_factory = sqlite3.Row
    return c


def init_db(reset=False):
    c = db()
    if reset:
        c.executescript("DROP TABLE IF EXISTS aircraft; DROP TABLE IF EXISTS resources;"
                        "DROP TABLE IF EXISTS history; DROP TABLE IF EXISTS meta;")
    c.executescript("""
    CREATE TABLE IF NOT EXISTS aircraft(
      id INTEGER PRIMARY KEY AUTOINCREMENT, callsign TEXT, type TEXT, operation TEXT,
      base_priority INTEGER, priority INTEGER, fuel INTEGER, arrival_tick INTEGER,
      last_aged INTEGER, status TEXT DEFAULT 'WAITING', start_tick INTEGER, end_tick INTEGER,
      runway TEXT, gate TEXT, crew TEXT);
    CREATE TABLE IF NOT EXISTS resources(name TEXT PRIMARY KEY, kind TEXT, holder TEXT);
    CREATE TABLE IF NOT EXISTS history(id INTEGER PRIMARY KEY AUTOINCREMENT, tick INTEGER,
      event TEXT, detail TEXT);
    CREATE TABLE IF NOT EXISTS meta(k TEXT PRIMARY KEY, v INTEGER);
    """)
    if not c.execute("SELECT 1 FROM resources").fetchone():
        c.executemany("INSERT INTO resources(name,kind) VALUES(?,?)", RESOURCES)
        c.execute("INSERT OR REPLACE INTO meta VALUES('clock',0)")
    c.commit()
    c.close()


def clock(c):
    return c.execute("SELECT v FROM meta WHERE k='clock'").fetchone()["v"]


def log(c, event, detail):
    c.execute("INSERT INTO history(tick,event,detail) VALUES(?,?,?)", (clock(c), event, detail))


# ---------- Phase 5/6: allocation with deadlock prevention ----------
def try_allocate(c, a):
    """Request ALL resources together (no hold-and-wait), in global order
    Runway -> Gate -> Crew (no circular wait). Atomic: all or nothing."""
    picks = {}
    for kind in ORDER:
        r = c.execute("SELECT name FROM resources WHERE kind=? AND holder IS NULL ORDER BY name",
                      (kind,)).fetchone()
        if not r:
            return False          # nothing is held -> aircraft just WAITS
        picks[kind] = r["name"]
    now = clock(c)
    for n in picks.values():
        c.execute("UPDATE resources SET holder=? WHERE name=?", (a["callsign"], n))
    c.execute("""UPDATE aircraft SET status='RUNNING', start_tick=?, end_tick=?, runway=?, gate=?, crew=?
                 WHERE id=?""", (now, now + DURATION, picks["Runway"], picks["Gate"], picks["Crew"], a["id"]))
    log(c, "ALLOCATE", f'{a["callsign"]} got {", ".join(picks.values())}')
    return True


def release(c, a):
    c.execute("UPDATE resources SET holder=NULL WHERE holder=?", (a["callsign"],))


def tick(c):
    c.execute("UPDATE meta SET v=v+1 WHERE k='clock'")
    now = clock(c)
    # 1. finish running aircraft -> release resources
    for a in c.execute("SELECT * FROM aircraft WHERE status='RUNNING' AND end_tick<=?", (now,)).fetchall():
        release(c, a)
        c.execute("UPDATE aircraft SET status='COMPLETED' WHERE id=?", (a["id"],))
        log(c, "RELEASE", f'{a["callsign"]} completed {a["operation"]}, resources released')
    # 2. aging (starvation prevention)
    for a in c.execute("SELECT * FROM aircraft WHERE status='WAITING'").fetchall():
        if now - a["last_aged"] >= AGING_EVERY and a["priority"] < AGING_CAP:
            c.execute("UPDATE aircraft SET priority=priority+1, last_aged=? WHERE id=?", (now, a["id"]))
            log(c, "AGING", f'{a["callsign"]} priority {a["priority"]} -> {a["priority"] + 1}')
    # 3. priority scheduling
    for a in c.execute("SELECT * FROM aircraft WHERE status='WAITING' "
                       "ORDER BY priority DESC, arrival_tick, id").fetchall():
        if not try_allocate(c, a):
            log(c, "WAIT", f'{a["callsign"]} waiting (resources busy, holding nothing)')
            break  # every aircraft needs the same kinds, so lower ones cannot go either
    c.commit()


# ---------- deadlock detection (wait-for graph) ----------
def find_cycle(graph):
    seen, stack = set(), []

    def dfs(n):
        if n in stack:
            return stack[stack.index(n):] + [n]
        if n in seen:
            return None
        seen.add(n)
        stack.append(n)
        for m in graph.get(n, []):
            r = dfs(m)
            if r:
                return r
        stack.pop()
        return None
    for n in list(graph):
        r = dfs(n)
        if r:
            return r
    return None


def deadlock_status(c):
    waiting = c.execute("SELECT * FROM aircraft WHERE status='WAITING'").fetchall()
    running = c.execute("SELECT * FROM aircraft WHERE status='RUNNING'").fetchall()
    graph = {}
    for a in waiting:   # waiting aircraft -> holders of kinds that are fully busy
        for kind in ORDER:
            free = c.execute("SELECT 1 FROM resources WHERE kind=? AND holder IS NULL", (kind,)).fetchone()
            if not free:
                holders = [r["holder"] for r in c.execute(
                    "SELECT DISTINCT holder FROM resources WHERE kind=? AND holder IS NOT NULL", (kind,)).fetchall()]
                graph.setdefault(a["callsign"], []).extend(holders)
    cyc = find_cycle(graph)
    return {"safe": cyc is None, "cycle": cyc, "resources_checked": len(RESOURCES),
            "aircraft_checked": len(waiting) + len(running), "waiting_graph": graph}


def deadlock_demo():
    """Pure simulation: naive allocation deadlocks; our policy does not."""
    naive = {"A101": ["A102"], "A102": ["A101"]}
    cyc = find_cycle(naive)
    steps = [
        "NAIVE: A101 holds Runway 1, requests Gate 1.",
        "NAIVE: A102 holds Gate 1, requests Runway 1.",
        "NAIVE: wait-for graph A101 -> A102 -> A101 = CIRCULAR WAIT (deadlock).",
        "PREVENTION 1 (all-or-nothing): A101 asks for Runway 1 + Gate 1 + Crew 1 together and is granted all.",
        "PREVENTION 1: A102 asks for the same set, one resource is busy, so A102 WAITS holding nothing.",
        "PREVENTION 2 (ordering): every aircraft requests Runway -> Gate -> Crew, so Gate -> Runway never happens.",
        "RESULT: no hold-and-wait, no circular wait. When A101 finishes, A102 is granted its resources.",
    ]
    return {"naive_graph": naive, "naive_cycle": cyc, "steps": steps}


# ---------- state / stats ----------
def stats(c):
    rows = [dict(r) for r in c.execute("SELECT * FROM aircraft").fetchall()]
    started = [r for r in rows if r["start_tick"] is not None]
    avg = round(sum(r["start_tick"] - r["arrival_tick"] for r in started) / len(started), 2) if started else 0
    by = {s: sum(1 for r in rows if r["status"] == s) for s in ("WAITING", "RUNNING", "COMPLETED")}
    use = {r["name"]: 0 for r in c.execute("SELECT name FROM resources").fetchall()}
    for r in rows:
        for k in ("runway", "gate", "crew"):
            if r[k]:
                use[r[k]] += 1
    return {"total": len(rows), "by_status": by, "avg_wait": avg, "usage": use,
            "max_wait": max([r["start_tick"] - r["arrival_tick"] for r in started], default=0)}


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/state")
def state():
    c = db()
    ac = [dict(r) for r in c.execute("SELECT * FROM aircraft ORDER BY id").fetchall()]
    now = clock(c)
    for a in ac:
        a["wait"] = (a["start_tick"] if a["start_tick"] is not None else now) - a["arrival_tick"]
    out = {"clock": now, "aircraft": ac,
           "resources": [dict(r) for r in c.execute("SELECT * FROM resources ORDER BY kind, name").fetchall()],
           "stats": stats(c), "deadlock": deadlock_status(c),
           "history": [dict(r) for r in c.execute("SELECT * FROM history ORDER BY id DESC LIMIT 60").fetchall()],
           "types": PRIORITY, "config": {"duration": DURATION, "aging_every": AGING_EVERY}}
    c.close()
    return jsonify(out)


def add_aircraft(c, callsign, typ, op, fuel):
    base = PRIORITY[typ]
    pri = min(10, base + (2 if fuel <= 15 else 0))   # low fuel boosts priority
    now = clock(c)
    c.execute("""INSERT INTO aircraft(callsign,type,operation,base_priority,priority,fuel,arrival_tick,last_aged)
                 VALUES(?,?,?,?,?,?,?,?)""", (callsign, typ, op, base, pri, fuel, now, now))
    log(c, "ARRIVE", f"{callsign} ({typ}, {op}) arrived with priority {pri}")


@app.route("/api/aircraft", methods=["POST"])
def create():
    d = request.get_json(force=True)
    callsign = str(d.get("callsign", "")).strip().upper()
    typ, op = d.get("type"), d.get("operation", "Landing")
    try:
        fuel = int(d.get("fuel", 100))
    except ValueError:
        fuel = 100
    if not callsign or typ not in PRIORITY or op not in ("Landing", "Takeoff") or not 0 <= fuel <= 100:
        return jsonify(error="Invalid aircraft data"), 400
    c = db()
    if c.execute("SELECT 1 FROM aircraft WHERE callsign=? AND status!='COMPLETED'", (callsign,)).fetchone():
        c.close()
        return jsonify(error=f"{callsign} is already active"), 400
    add_aircraft(c, callsign, typ, op, fuel)
    c.commit()
    c.close()
    return jsonify(ok=True)


@app.route("/api/aircraft/<int:aid>", methods=["DELETE"])
def remove(aid):
    c = db()
    a = c.execute("SELECT * FROM aircraft WHERE id=?", (aid,)).fetchone()
    if a:
        release(c, a)
        c.execute("DELETE FROM aircraft WHERE id=?", (aid,))
        log(c, "REMOVE", f'{a["callsign"]} removed')
        c.commit()
    c.close()
    return jsonify(ok=True)


@app.route("/api/tick", methods=["POST"])
def do_tick():
    c = db()
    tick(c)
    c.close()
    return jsonify(ok=True)


@app.route("/api/seed", methods=["POST"])
def seed():
    c = db()
    for cs, t, o, f in [("A101", "Normal", "Landing", 60), ("A102", "Emergency", "Landing", 12),
                        ("A103", "Cargo", "Takeoff", 80), ("A104", "VIP", "Takeoff", 70),
                        ("A105", "Training", "Landing", 90), ("A106", "Medical", "Landing", 40)]:
        if not c.execute("SELECT 1 FROM aircraft WHERE callsign=? AND status!='COMPLETED'", (cs,)).fetchone():
            add_aircraft(c, cs, t, o, f)
    c.commit()
    c.close()
    return jsonify(ok=True)


@app.route("/api/reset", methods=["POST"])
def reset():
    init_db(reset=True)
    return jsonify(ok=True)


@app.route("/api/deadlock/demo")
def demo():
    return jsonify(deadlock_demo())


init_db()

if __name__ == "__main__":
    app.run(debug=True, port=5000)
