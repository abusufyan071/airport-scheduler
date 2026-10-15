# Airport Runway Scheduling System (OS Project)

Aircraft = processes, Runway/Gate/Ground Crew = resources.
Implements: Priority Scheduling + Aging, Resource Allocation, Deadlock Prevention
(all-or-nothing request + global resource ordering), deadlock detection (wait-for graph), SQLite storage, statistics.

## Run
    pip install -r requirements.txt
    python app.py
Open http://127.0.0.1:5000

## Demo flow
1. Click **Load Sample** (6 aircraft). 2. Click **Next Tick** (or Auto) and watch Dashboard / Scheduling tabs.
3. Emergency/Medical go first; low-priority aircraft gain priority through **aging**.
4. **Deadlock** tab -> *Create Conflict & Show Prevention*.

## Structure
app.py (backend + OS logic) | templates/index.html | static/app.js, style.css | airport.db (auto-created)
Tunables at top of app.py: DURATION, AGING_EVERY, AGING_CAP, PRIORITY.
