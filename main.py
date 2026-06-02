import sqlite3
import os
from typing import Optional, List

from fastapi import FastAPI, HTTPException, Depends
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "swim_meet.db")

# ---------------------------------------------------------------------------
# Database helpers
# ---------------------------------------------------------------------------

def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db():
    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA foreign_keys = ON")
    cur = conn.cursor()

    cur.executescript("""
        CREATE TABLE IF NOT EXISTS swimmer (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            dob TEXT,
            team TEXT
        );

        CREATE TABLE IF NOT EXISTS event (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            distance INTEGER,
            stroke TEXT
        );

        CREATE TABLE IF NOT EXISTS meet (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            date TEXT,
            location TEXT
        );

        CREATE TABLE IF NOT EXISTS heat (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            meet_id INTEGER NOT NULL REFERENCES meet(id) ON DELETE CASCADE,
            event_id INTEGER NOT NULL REFERENCES event(id) ON DELETE CASCADE,
            heat_number INTEGER NOT NULL,
            scheduled_time TEXT
        );

        CREATE TABLE IF NOT EXISTS heat_entry (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            heat_id INTEGER NOT NULL REFERENCES heat(id) ON DELETE CASCADE,
            swimmer_id INTEGER NOT NULL REFERENCES swimmer(id) ON DELETE CASCADE,
            lane INTEGER NOT NULL
        );

        CREATE TABLE IF NOT EXISTS race (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            heat_entry_id INTEGER NOT NULL REFERENCES heat_entry(id) ON DELETE CASCADE,
            final_time_ms INTEGER,
            disqualified INTEGER NOT NULL DEFAULT 0,
            dq_reason TEXT
        );

        CREATE TABLE IF NOT EXISTS split (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            race_id INTEGER NOT NULL REFERENCES race(id) ON DELETE CASCADE,
            split_number INTEGER NOT NULL,
            distance INTEGER,
            time_ms INTEGER
        );
    """)
    conn.commit()
    conn.close()


# ---------------------------------------------------------------------------
# Pydantic models
# ---------------------------------------------------------------------------

class SwimmerCreate(BaseModel):
    name: str
    dob: Optional[str] = None
    team: Optional[str] = None

class EventCreate(BaseModel):
    name: str
    distance: Optional[int] = None
    stroke: Optional[str] = None

class MeetCreate(BaseModel):
    name: str
    date: Optional[str] = None
    location: Optional[str] = None

class HeatCreate(BaseModel):
    meet_id: int
    event_id: int
    heat_number: int
    scheduled_time: Optional[str] = None

class HeatEntryCreate(BaseModel):
    heat_id: int
    swimmer_id: int
    lane: int

class RaceCreate(BaseModel):
    heat_entry_id: int
    final_time_ms: Optional[int] = None
    disqualified: bool = False
    dq_reason: Optional[str] = None

class SplitCreate(BaseModel):
    split_number: int
    distance: Optional[int] = None
    time_ms: Optional[int] = None

# ---------------------------------------------------------------------------
# App
# ---------------------------------------------------------------------------

app = FastAPI(title="Swim Meet Manager")

@app.on_event("startup")
def on_startup():
    init_db()

# Serve frontend
frontend_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "frontend")
app.mount("/static", StaticFiles(directory=frontend_dir), name="static")

@app.get("/")
def root():
    return FileResponse(os.path.join(frontend_dir, "index.html"))

# ---------------------------------------------------------------------------
# Swimmers
# ---------------------------------------------------------------------------

@app.post("/swimmers/", status_code=201)
def create_swimmer(body: SwimmerCreate, db: sqlite3.Connection = Depends(get_db)):
    cur = db.execute(
        "INSERT INTO swimmer (name, dob, team) VALUES (?, ?, ?)",
        (body.name, body.dob, body.team)
    )
    return {"id": cur.lastrowid, **body.dict()}

@app.get("/swimmers/")
def list_swimmers(db: sqlite3.Connection = Depends(get_db)):
    rows = db.execute("SELECT * FROM swimmer ORDER BY name").fetchall()
    return [dict(r) for r in rows]

@app.get("/swimmers/{swimmer_id}")
def get_swimmer(swimmer_id: int, db: sqlite3.Connection = Depends(get_db)):
    row = db.execute("SELECT * FROM swimmer WHERE id = ?", (swimmer_id,)).fetchone()
    if not row:
        raise HTTPException(404, "Swimmer not found")
    return dict(row)

@app.put("/swimmers/{swimmer_id}")
def update_swimmer(swimmer_id: int, body: SwimmerCreate, db: sqlite3.Connection = Depends(get_db)):
    db.execute(
        "UPDATE swimmer SET name=?, dob=?, team=? WHERE id=?",
        (body.name, body.dob, body.team, swimmer_id)
    )
    return {"id": swimmer_id, **body.dict()}

@app.delete("/swimmers/{swimmer_id}", status_code=204)
def delete_swimmer(swimmer_id: int, db: sqlite3.Connection = Depends(get_db)):
    db.execute("DELETE FROM swimmer WHERE id = ?", (swimmer_id,))

@app.get("/swimmers/{swimmer_id}/history")
def swimmer_history(swimmer_id: int, db: sqlite3.Connection = Depends(get_db)):
    races = db.execute("""
        SELECT r.id as race_id, r.final_time_ms, r.disqualified, r.dq_reason,
               he.lane, h.heat_number, h.scheduled_time,
               e.name as event_name, e.distance, e.stroke,
               m.name as meet_name, m.date as meet_date
        FROM race r
        JOIN heat_entry he ON he.id = r.heat_entry_id
        JOIN heat h ON h.id = he.heat_id
        JOIN event e ON e.id = h.event_id
        JOIN meet m ON m.id = h.meet_id
        WHERE he.swimmer_id = ?
        ORDER BY m.date DESC, r.id DESC
    """, (swimmer_id,)).fetchall()

    result = []
    for race in races:
        r = dict(race)
        splits = db.execute(
            "SELECT * FROM split WHERE race_id = ? ORDER BY split_number",
            (race["race_id"],)
        ).fetchall()
        r["splits"] = [dict(s) for s in splits]
        result.append(r)
    return result

# ---------------------------------------------------------------------------
# Events
# ---------------------------------------------------------------------------

@app.post("/events/", status_code=201)
def create_event(body: EventCreate, db: sqlite3.Connection = Depends(get_db)):
    cur = db.execute(
        "INSERT INTO event (name, distance, stroke) VALUES (?, ?, ?)",
        (body.name, body.distance, body.stroke)
    )
    return {"id": cur.lastrowid, **body.dict()}

@app.get("/events/")
def list_events(db: sqlite3.Connection = Depends(get_db)):
    rows = db.execute("SELECT * FROM event ORDER BY name").fetchall()
    return [dict(r) for r in rows]

@app.get("/events/{event_id}")
def get_event(event_id: int, db: sqlite3.Connection = Depends(get_db)):
    row = db.execute("SELECT * FROM event WHERE id = ?", (event_id,)).fetchone()
    if not row:
        raise HTTPException(404, "Event not found")
    return dict(row)

@app.put("/events/{event_id}")
def update_event(event_id: int, body: EventCreate, db: sqlite3.Connection = Depends(get_db)):
    db.execute(
        "UPDATE event SET name=?, distance=?, stroke=? WHERE id=?",
        (body.name, body.distance, body.stroke, event_id)
    )
    return {"id": event_id, **body.dict()}

@app.delete("/events/{event_id}", status_code=204)
def delete_event(event_id: int, db: sqlite3.Connection = Depends(get_db)):
    db.execute("DELETE FROM event WHERE id = ?", (event_id,))

# ---------------------------------------------------------------------------
# Meets
# ---------------------------------------------------------------------------

@app.post("/meets/", status_code=201)
def create_meet(body: MeetCreate, db: sqlite3.Connection = Depends(get_db)):
    cur = db.execute(
        "INSERT INTO meet (name, date, location) VALUES (?, ?, ?)",
        (body.name, body.date, body.location)
    )
    return {"id": cur.lastrowid, **body.dict()}

@app.get("/meets/")
def list_meets(db: sqlite3.Connection = Depends(get_db)):
    rows = db.execute("SELECT * FROM meet ORDER BY date DESC").fetchall()
    return [dict(r) for r in rows]

@app.get("/meets/{meet_id}")
def get_meet(meet_id: int, db: sqlite3.Connection = Depends(get_db)):
    row = db.execute("SELECT * FROM meet WHERE id = ?", (meet_id,)).fetchone()
    if not row:
        raise HTTPException(404, "Meet not found")
    return dict(row)

@app.put("/meets/{meet_id}")
def update_meet(meet_id: int, body: MeetCreate, db: sqlite3.Connection = Depends(get_db)):
    db.execute(
        "UPDATE meet SET name=?, date=?, location=? WHERE id=?",
        (body.name, body.date, body.location, meet_id)
    )
    return {"id": meet_id, **body.dict()}

@app.delete("/meets/{meet_id}", status_code=204)
def delete_meet(meet_id: int, db: sqlite3.Connection = Depends(get_db)):
    db.execute("DELETE FROM meet WHERE id = ?", (meet_id,))

# ---------------------------------------------------------------------------
# Heats
# ---------------------------------------------------------------------------

@app.post("/heats/", status_code=201)
def create_heat(body: HeatCreate, db: sqlite3.Connection = Depends(get_db)):
    cur = db.execute(
        "INSERT INTO heat (meet_id, event_id, heat_number, scheduled_time) VALUES (?, ?, ?, ?)",
        (body.meet_id, body.event_id, body.heat_number, body.scheduled_time)
    )
    return {"id": cur.lastrowid, **body.dict()}

@app.get("/heats/")
def list_heats(meet_id: Optional[int] = None, event_id: Optional[int] = None,
               db: sqlite3.Connection = Depends(get_db)):
    query = "SELECT h.*, m.name as meet_name, e.name as event_name FROM heat h JOIN meet m ON m.id = h.meet_id JOIN event e ON e.id = h.event_id WHERE 1=1"
    params = []
    if meet_id:
        query += " AND h.meet_id = ?"
        params.append(meet_id)
    if event_id:
        query += " AND h.event_id = ?"
        params.append(event_id)
    query += " ORDER BY h.heat_number"
    rows = db.execute(query, params).fetchall()
    return [dict(r) for r in rows]

@app.get("/heats/{heat_id}")
def get_heat(heat_id: int, db: sqlite3.Connection = Depends(get_db)):
    row = db.execute("SELECT * FROM heat WHERE id = ?", (heat_id,)).fetchone()
    if not row:
        raise HTTPException(404, "Heat not found")
    return dict(row)

@app.put("/heats/{heat_id}")
def update_heat(heat_id: int, body: HeatCreate, db: sqlite3.Connection = Depends(get_db)):
    db.execute(
        "UPDATE heat SET meet_id=?, event_id=?, heat_number=?, scheduled_time=? WHERE id=?",
        (body.meet_id, body.event_id, body.heat_number, body.scheduled_time, heat_id)
    )
    return {"id": heat_id, **body.dict()}

@app.delete("/heats/{heat_id}", status_code=204)
def delete_heat(heat_id: int, db: sqlite3.Connection = Depends(get_db)):
    db.execute("DELETE FROM heat WHERE id = ?", (heat_id,))

@app.get("/heats/{heat_id}/results")
def heat_results(heat_id: int, db: sqlite3.Connection = Depends(get_db)):
    rows = db.execute("""
        SELECT r.id as race_id, r.final_time_ms, r.disqualified, r.dq_reason,
               he.lane, he.id as heat_entry_id,
               s.id as swimmer_id, s.name as swimmer_name, s.team
        FROM heat_entry he
        JOIN swimmer s ON s.id = he.swimmer_id
        LEFT JOIN race r ON r.heat_entry_id = he.id
        WHERE he.heat_id = ?
        ORDER BY
            CASE WHEN r.disqualified = 1 OR r.final_time_ms IS NULL THEN 1 ELSE 0 END,
            r.final_time_ms ASC
    """, (heat_id,)).fetchall()

    result = []
    for row in rows:
        r = dict(row)
        if r["race_id"]:
            splits = db.execute(
                "SELECT * FROM split WHERE race_id = ? ORDER BY split_number",
                (r["race_id"],)
            ).fetchall()
            r["splits"] = [dict(s) for s in splits]
        else:
            r["splits"] = []
        result.append(r)
    return result

# ---------------------------------------------------------------------------
# Heat Entries
# ---------------------------------------------------------------------------

@app.post("/heat_entries/", status_code=201)
def create_heat_entry(body: HeatEntryCreate, db: sqlite3.Connection = Depends(get_db)):
    cur = db.execute(
        "INSERT INTO heat_entry (heat_id, swimmer_id, lane) VALUES (?, ?, ?)",
        (body.heat_id, body.swimmer_id, body.lane)
    )
    return {"id": cur.lastrowid, **body.dict()}

@app.get("/heat_entries/")
def list_heat_entries(heat_id: Optional[int] = None, db: sqlite3.Connection = Depends(get_db)):
    if heat_id:
        rows = db.execute(
            "SELECT he.*, s.name as swimmer_name, s.team FROM heat_entry he JOIN swimmer s ON s.id = he.swimmer_id WHERE he.heat_id = ? ORDER BY he.lane",
            (heat_id,)
        ).fetchall()
    else:
        rows = db.execute(
            "SELECT he.*, s.name as swimmer_name, s.team FROM heat_entry he JOIN swimmer s ON s.id = he.swimmer_id ORDER BY he.heat_id, he.lane"
        ).fetchall()
    return [dict(r) for r in rows]

@app.delete("/heat_entries/{entry_id}", status_code=204)
def delete_heat_entry(entry_id: int, db: sqlite3.Connection = Depends(get_db)):
    db.execute("DELETE FROM heat_entry WHERE id = ?", (entry_id,))

# ---------------------------------------------------------------------------
# Races
# ---------------------------------------------------------------------------

@app.post("/races/", status_code=201)
def create_race(body: RaceCreate, db: sqlite3.Connection = Depends(get_db)):
    existing = db.execute(
        "SELECT id FROM race WHERE heat_entry_id = ?", (body.heat_entry_id,)
    ).fetchone()
    if existing:
        db.execute(
            "UPDATE race SET final_time_ms=?, disqualified=?, dq_reason=? WHERE id=?",
            (body.final_time_ms, int(body.disqualified), body.dq_reason, existing["id"])
        )
        return {"id": existing["id"], **body.dict()}

    cur = db.execute(
        "INSERT INTO race (heat_entry_id, final_time_ms, disqualified, dq_reason) VALUES (?, ?, ?, ?)",
        (body.heat_entry_id, body.final_time_ms, int(body.disqualified), body.dq_reason)
    )
    return {"id": cur.lastrowid, **body.dict()}

@app.get("/races/{race_id}")
def get_race(race_id: int, db: sqlite3.Connection = Depends(get_db)):
    row = db.execute("SELECT * FROM race WHERE id = ?", (race_id,)).fetchone()
    if not row:
        raise HTTPException(404, "Race not found")
    return dict(row)

@app.post("/races/{race_id}/splits", status_code=201)
def add_splits(race_id: int, splits: List[SplitCreate], db: sqlite3.Connection = Depends(get_db)):
    db.execute("DELETE FROM split WHERE race_id = ?", (race_id,))
    inserted = []
    for s in splits:
        cur = db.execute(
            "INSERT INTO split (race_id, split_number, distance, time_ms) VALUES (?, ?, ?, ?)",
            (race_id, s.split_number, s.distance, s.time_ms)
        )
        inserted.append({"id": cur.lastrowid, "race_id": race_id, **s.dict()})
    return inserted
