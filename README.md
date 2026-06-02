# Swim Meet Manager

A web application for managing swim meets, heats, lane assignments, and race results.

## Setup & Run

```bash
pip install fastapi uvicorn python-multipart
uvicorn main:app --reload
```

Then open http://localhost:8000 in your browser.

## Usage

1. **Swimmers tab** — Add swimmers with name, date of birth, and team.
2. **Events tab** — Define events (e.g. "100m Freestyle") with distance and stroke.
3. **Meets tab** — Create meets with name, date, and location.
4. **Heats tab** — Create heats by selecting a meet + event + heat number. Then assign swimmers to lanes.
5. **Results tab** — Select a meet and heat, enter finish times (in milliseconds) and optional splits per lane, then save. The leaderboard updates automatically with rank badges and expandable split details.

## Data Model

- **Swimmer**: name, date of birth, team
- **Event**: name, distance, stroke
- **Meet**: name, date, location
- **Heat**: links a meet + event, with a heat number and optional scheduled time
- **HeatEntry**: assigns a swimmer to a lane in a heat
- **Race**: records the finish time (milliseconds), DQ status, and reason for a heat entry
- **Split**: intermediate split times linked to a race

## API

Interactive API docs: http://localhost:8000/docs

Key endpoints:
- `GET/POST /swimmers/` — list and create swimmers
- `GET /swimmers/{id}/history` — full race history with splits for a swimmer
- `GET/POST /events/`, `/meets/`, `/heats/`, `/heat_entries/`
- `POST /races/` — record or update a race result
- `POST /races/{id}/splits` — add splits to a race
- `GET /heats/{id}/results` — ranked results for a heat
