import sqlite3
import os
from contextlib import contextmanager
from typing import Optional, List
from datetime import date

from fastapi import FastAPI, HTTPException, Depends
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel

DB_PATH = os.path.join(os.path.dirname(__file__), "swim_meet.db")


# ---------------------------------------------------------------------------
# DB helpers
# ---------------------------------------------------------------------------

def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        yield conn
    finally:
        conn.close()


def init_db():
    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA foreign_keys = ON")
    c = conn.cursor()
    c.executescript("""
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

class SwimmerIn(BaseModel):
    name: str
    dob: Optional[str] = None
    team: Optional[str] = None

class SwimmerOut(SwimmerIn):
    id: int

class EventIn(BaseModel):
    name: str
    distance: Optional[int] = None
    stroke: Optional[str] = None

class EventOut(EventIn):
    id: int

class MeetIn(BaseModel):
    name: str
    date: Optional[str] = None
    location: Optional[str] = None

class MeetOut(MeetIn):
    id: int

class HeatIn(BaseModel):
    meet_id: int
    event_id: int
    heat_number: int
    scheduled_time: Optional[str] = None

class HeatOut(HeatIn):
    id: int

class HeatEntryIn(BaseModel):
    heat_id: int
    swimmer_id: int
    lane: int

class HeatEntryOut(HeatEntryIn):
    id: int

class RaceIn(BaseModel):
    heat_entry_id: int
    final_time_ms: Optional[int] = None
    disqualified: bool = False
    dq_reason: Optional[str] = None

class RaceOut(RaceIn):
    id: int

class SplitIn(BaseModel):
    split_number: int
    distance: Optional[int] = None
    time_ms: Optional[int] = None

class SplitOut(SplitIn):
    id: int
    race_id: int


# ---------------------------------------------------------------------------
# App
# ---------------------------------------------------------------------------

app = FastAPI(title="Swim Meet Manager")

init_db()

frontend_dir = os.path.join(os.path.dirname(__file__), "frontend")
if os.path.isdir(frontend_dir):
    app.mount("/static", StaticFiles(directory=frontend_dir), name="static")

@app.get("/")
def root():
    return FileResponse(os.path.join(frontend_dir, "index.html"))


# ---------------------------------------------------------------------------
# Swimmers
# ---------------------------------------------------------------------------

@app.get("/swimmers/", response_model=List[SwimmerOut])
def list_swimmers(db: sqlite3.Connection = Depends(get_db)):
    rows = db.execute("SELECT * FROM swimmer ORDER BY name").fetchall()
    return [dict(r) for r in rows]

@app.post("/swimmers/", response_model=SwimmerOut)
def create_swimmer(body: SwimmerIn, db: sqlite3.Connection = Depends(get_db)):
    cur = db.execute("INSERT INTO swimmer(name,dob,team) VALUES(?,?,?)",
                     (body.name, body.dob, body.team))
    db.commit()
    return {**body.dict(), "id": cur.lastrowid}

@app.get("/swimmers/{swimmer_id}", response_model=SwimmerOut)
def get_swimmer(swimmer_id: int, db: sqlite3.Connection = Depends(get_db)):
    row = db.execute("SELECT * FROM swimmer WHERE id=?", (swimmer_id,)).fetchone()
    if not row:
        raise HTTPException(404, "Swimmer not found")
    return dict(row)

@app.put("/swimmers/{swimmer_id}", response_model=SwimmerOut)
def update_swimmer(swimmer_id: int, body: SwimmerIn, db: sqlite3.Connection = Depends(get_db)):
    db.execute("UPDATE swimmer SET name=?,dob=?,team=? WHERE id=?",
               (body.name, body.dob, body.team, swimmer_id))
    db.commit()
    return {**body.dict(), "id": swimmer_id}

@app.delete("/swimmers/{swimmer_id}")
def delete_swimmer(swimmer_id: int, db: sqlite3.Connection = Depends(get_db)):
    db.execute("DELETE FROM swimmer WHERE id=?", (swimmer_id,))
    db.commit()
    return {"ok": True}

@app.get("/swimmers/{swimmer_id}/history")
def swimmer_history(swimmer_id: int, db: sqlite3.Connection = Depends(get_db)):
    rows = db.execute("""
        SELECT r.id as race_id, r.final_time_ms, r.disqualified, r.dq_reason,
               he.lane, h.heat_number, h.scheduled_time,
               m.name as meet_name, m.date as meet_date,
               e.name as event_name, e.distance, e.stroke
        FROM race r
        JOIN heat_entry he ON he.id = r.heat_entry_id
        JOIN heat h ON h.id = he.heat_id
        JOIN meet m ON m.id = h.meet_id
        JOIN event e ON e.id = h.event_id
        WHERE he.swimmer_id = ?
        ORDER BY m.date DESC, r.id DESC
    """, (swimmer_id,)).fetchall()

    results = []
    for row in rows:
        entry = dict(row)
        splits = db.execute(
            "SELECT * FROM split WHERE race_id=? ORDER BY split_number",
            (entry["race_id"],)
        ).fetchall()
        entry["splits"] = [dict(s) for s in splits]
        results.append(entry)
    return results


# ---------------------------------------------------------------------------
# Events
# ---------------------------------------------------------------------------

@app.get("/events/", response_model=List[EventOut])
def list_events(db: sqlite3.Connection = Depends(get_db)):
    rows = db.execute("SELECT * FROM event ORDER BY name").fetchall()
    return [dict(r) for r in rows]

@app.post("/events/", response_model=EventOut)
def create_event(body: EventIn, db: sqlite3.Connection = Depends(get_db)):
    cur = db.execute("INSERT INTO event(name,distance,stroke) VALUES(?,?,?)",
                     (body.name, body.distance, body.stroke))
    db.commit()
    return {**body.dict(), "id": cur.lastrowid}

@app.get("/events/{event_id}", response_model=EventOut)
def get_event(event_id: int, db: sqlite3.Connection = Depends(get_db)):
    row = db.execute("SELECT * FROM event WHERE id=?", (event_id,)).fetchone()
    if not row:
        raise HTTPException(404, "Event not found")
    return dict(row)

@app.put("/events/{event_id}", response_model=EventOut)
def update_event(event_id: int, body: EventIn, db: sqlite3.Connection = Depends(get_db)):
    db.execute("UPDATE event SET name=?,distance=?,stroke=? WHERE id=?",
               (body.name, body.distance, body.stroke, event_id))
    db.commit()
    return {**body.dict(), "id": event_id}

@app.delete("/events/{event_id}")
def delete_event(event_id: int, db: sqlite3.Connection = Depends(get_db)):
    db.execute("DELETE FROM event WHERE id=?", (event_id,))
    db.commit()
    return {"ok": True}


# ---------------------------------------------------------------------------
# Meets
# ---------------------------------------------------------------------------

@app.get("/meets/", response_model=List[MeetOut])
def list_meets(db: sqlite3.Connection = Depends(get_db)):
    rows = db.execute("SELECT * FROM meet ORDER BY date DESC").fetchall()
    return [dict(r) for r in rows]

@app.post("/meets/", response_model=MeetOut)
def create_meet(body: MeetIn, db: sqlite3.Connection = Depends(get_db)):
    cur = db.execute("INSERT INTO meet(name,date,location) VALUES(?,?,?)",
                     (body.name, body.date, body.location))
    db.commit()
    return {**body.dict(), "id": cur.lastrowid}

@app.get("/meets/{meet_id}", response_model=MeetOut)
def get_meet(meet_id: int, db: sqlite3.Connection = Depends(get_db)):
    row = db.execute("SELECT * FROM meet WHERE id=?", (meet_id,)).fetchone()
    if not row:
        raise HTTPException(404, "Meet not found")
    return dict(row)

@app.put("/meets/{meet_id}", response_model=MeetOut)
def update_meet(meet_id: int, body: MeetIn, db: sqlite3.Connection = Depends(get_db)):
    db.execute("UPDATE meet SET name=?,date=?,location=? WHERE id=?",
               (body.name, body.date, body.location, meet_id))
    db.commit()
    return {**body.dict(), "id": meet_id}

@app.delete("/meets/{meet_id}")
def delete_meet(meet_id: int, db: sqlite3.Connection = Depends(get_db)):
    db.execute("DELETE FROM meet WHERE id=?", (meet_id,))
    db.commit()
    return {"ok": True}


# ---------------------------------------------------------------------------
# Heats
# ---------------------------------------------------------------------------

@app.get("/heats/", response_model=List[HeatOut])
def list_heats(meet_id: Optional[int] = None, event_id: Optional[int] = None,
               db: sqlite3.Connection = Depends(get_db)):
    query = "SELECT * FROM heat WHERE 1=1"
    params = []
    if meet_id:
        query += " AND meet_id=?"
        params.append(meet_id)
    if event_id:
        query += " AND event_id=?"
        params.append(event_id)
    query += " ORDER BY heat_number"
    rows = db.execute(query, params).fetchall()
    return [dict(r) for r in rows]

@app.post("/heats/", response_model=HeatOut)
def create_heat(body: HeatIn, db: sqlite3.Connection = Depends(get_db)):
    cur = db.execute(
        "INSERT INTO heat(meet_id,event_id,heat_number,scheduled_time) VALUES(?,?,?,?)",
        (body.meet_id, body.event_id, body.heat_number, body.scheduled_time)
    )
    db.commit()
    return {**body.dict(), "id": cur.lastrowid}

@app.get("/heats/{heat_id}", response_model=HeatOut)
def get_heat(heat_id: int, db: sqlite3.Connection = Depends(get_db)):
    row = db.execute("SELECT * FROM heat WHERE id=?", (heat_id,)).fetchone()
    if not row:
        raise HTTPException(404, "Heat not found")
    return dict(row)

@app.delete("/heats/{heat_id}")
def delete_heat(heat_id: int, db: sqlite3.Connection = Depends(get_db)):
    db.execute("DELETE FROM heat WHERE id=?", (heat_id,))
    db.commit()
    return {"ok": True}

@app.get("/heats/{heat_id}/entries")
def heat_entries(heat_id: int, db: sqlite3.Connection = Depends(get_db)):
    rows = db.execute("""
        SELECT he.id, he.heat_id, he.swimmer_id, he.lane,
               s.name as swimmer_name, s.team
        FROM heat_entry he
        JOIN swimmer s ON s.id = he.swimmer_id
        WHERE he.heat_id = ?
        ORDER BY he.lane
    """, (heat_id,)).fetchall()
    return [dict(r) for r in rows]

@app.get("/heats/{heat_id}/results")
def heat_results(heat_id: int, db: sqlite3.Connection = Depends(get_db)):
    rows = db.execute("""
        SELECT r.id as race_id, r.final_time_ms, r.disqualified, r.dq_reason,
               he.lane, he.id as heat_entry_id,
               s.name as swimmer_name, s.team
        FROM heat_entry he
        JOIN swimmer s ON s.id = he.swimmer_id
        LEFT JOIN race r ON r.heat_entry_id = he.id
        WHERE he.heat_id = ?
        ORDER BY
            CASE WHEN r.disqualified=1 OR r.final_time_ms IS NULL THEN 1 ELSE 0 END,
            r.final_time_ms ASC
    """, (heat_id,)).fetchall()

    results = []
    for row in rows:
        entry = dict(row)
        if entry["race_id"]:
            splits = db.execute(
                "SELECT * FROM split WHERE race_id=? ORDER BY split_number",
                (entry["race_id"],)
            ).fetchall()
            entry["splits"] = [dict(s) for s in splits]
        else:
            entry["splits"] = []
        results.append(entry)
    return results


# ---------------------------------------------------------------------------
# Heat Entries
# ---------------------------------------------------------------------------

@app.get("/heat_entries/", response_model=List[HeatEntryOut])
def list_heat_entries(heat_id: Optional[int] = None, db: sqlite3.Connection = Depends(get_db)):
    if heat_id:
        rows = db.execute("SELECT * FROM heat_entry WHERE heat_id=? ORDER BY lane", (heat_id,)).fetchall()
    else:
        rows = db.execute("SELECT * FROM heat_entry ORDER BY id").fetchall()
    return [dict(r) for r in rows]

@app.post("/heat_entries/", response_model=HeatEntryOut)
def create_heat_entry(body: HeatEntryIn, db: sqlite3.Connection = Depends(get_db)):
    cur = db.execute(
        "INSERT INTO heat_entry(heat_id,swimmer_id,lane) VALUES(?,?,?)",
        (body.heat_id, body.swimmer_id, body.lane)
    )
    db.commit()
    return {**body.dict(), "id": cur.lastrowid}

@app.delete("/heat_entries/{entry_id}")
def delete_heat_entry(entry_id: int, db: sqlite3.Connection = Depends(get_db)):
    db.execute("DELETE FROM heat_entry WHERE id=?", (entry_id,))
    db.commit()
    return {"ok": True}


# ---------------------------------------------------------------------------
# Races
# ---------------------------------------------------------------------------

@app.get("/races/", response_model=List[RaceOut])
def list_races(db: sqlite3.Connection = Depends(get_db)):
    rows = db.execute("SELECT * FROM race ORDER BY id").fetchall()
    return [dict(r) for r in rows]

@app.post("/races/", response_model=RaceOut)
def create_race(body: RaceIn, db: sqlite3.Connection = Depends(get_db)):
    # Upsert: if race already exists for this heat_entry, update it
    existing = db.execute(
        "SELECT id FROM race WHERE heat_entry_id=?", (body.heat_entry_id,)
    ).fetchone()
    if existing:
        db.execute(
            "UPDATE race SET final_time_ms=?,disqualified=?,dq_reason=? WHERE id=?",
            (body.final_time_ms, int(body.disqualified), body.dq_reason, existing["id"])
        )
        db.commit()
        return {**body.dict(), "id": existing["id"]}
    cur = db.execute(
        "INSERT INTO race(heat_entry_id,final_time_ms,disqualified,dq_reason) VALUES(?,?,?,?)",
        (body.heat_entry_id, body.final_time_ms, int(body.disqualified), body.dq_reason)
    )
    db.commit()
    return {**body.dict(), "id": cur.lastrowid}

@app.post("/races/{race_id}/splits", response_model=List[SplitOut])
def add_splits(race_id: int, splits: List[SplitIn], db: sqlite3.Connection = Depends(get_db)):
    # Replace all splits for this race
    db.execute("DELETE FROM split WHERE race_id=?", (race_id,))
    result = []
    for s in splits:
        cur = db.execute(
            "INSERT INTO split(race_id,split_number,distance,time_ms) VALUES(?,?,?,?)",
            (race_id, s.split_number, s.distance, s.time_ms)
        )
        result.append({**s.dict(), "id": cur.lastrowid, "race_id": race_id})
    db.commit()
    return result
