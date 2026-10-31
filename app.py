"""My Festival REST API — M10 (CSC Rahti)."""
import os
import sqlite3
from datetime import datetime, timedelta

from flask import Flask, jsonify, request

app = Flask(__name__)

DB_PATH = os.environ.get("DB_PATH", os.path.join(os.path.dirname(__file__), "myfestival.db"))

DT_FORMAT = "%Y-%m-%d %H:%M:%S"
DURATION_MIN = 45


def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA foreign_keys = ON")
    conn.row_factory = sqlite3.Row
    return conn


@app.get("/")
def health():
    return jsonify(status="ok", endpoints=["/api/artists", "/api/days", "/api/stages",
                                           "/api/artists/<id>/events", "/api/timetable?day=YYYY-MM-DD",
                                           "POST /api/events", "DELETE /api/events/<id>"])


@app.get("/api/artists")
def get_artists():
    conn = get_db()
    try:
        cols = {r["name"].lower() for r in conn.execute("PRAGMA table_info(Artist)")}
        country_col = "country" if "country" in cols else "contry"
        rows = conn.execute(
            f"SELECT artist_id, name, {country_col} AS country FROM Artist ORDER BY name"
        ).fetchall()
        return jsonify([dict(r) for r in rows])
    finally:
        conn.close()


@app.get("/api/days")
def get_days():
    conn = get_db()
    try:
        rows = conn.execute("SELECT day_id, date FROM Day ORDER BY date").fetchall()
        return jsonify([dict(r) for r in rows])
    finally:
        conn.close()


@app.get("/api/stages")
def get_stages():
    conn = get_db()
    try:
        rows = conn.execute(
            "SELECT Stage_id AS stage_id, name FROM Stage ORDER BY Stage_id").fetchall()
        return jsonify([dict(r) for r in rows])
    finally:
        conn.close()


@app.get("/api/artists/<int:artist_id>/events")
def get_artist_events(artist_id):
    conn = get_db()
    try:
        if conn.execute("SELECT 1 FROM Artist WHERE artist_id = ?", (artist_id,)).fetchone() is None:
            return jsonify(error="artist not found"), 404
        rows = conn.execute(
            """SELECT e.event_id, d.date AS day, s.name AS stage, e.start_dt AS starts
               FROM Event e
               JOIN Day d   ON d.day_id = e.day_id
               JOIN Stage s ON s.Stage_id = e.stage_id
               WHERE e.artist_id = ?
               ORDER BY e.start_dt""",
            (artist_id,),
        ).fetchall()
        return jsonify([dict(r) for r in rows])
    finally:
        conn.close()


@app.get("/api/timetable")
def get_timetable():
    day = request.args.get("day")
    sql = """SELECT d.date AS date, s.name AS stage, a.name AS artist,
                    e.start_dt AS starts, e.end_dt AS ends
             FROM Event e
             JOIN Day d    ON d.day_id = e.day_id
             JOIN Stage s  ON s.Stage_id = e.stage_id
             JOIN Artist a ON a.artist_id = e.artist_id"""
    params = ()
    if day is not None:
        try:
            datetime.strptime(day, "%Y-%m-%d")
        except ValueError:
            return jsonify(error="invalid date, expected YYYY-MM-DD"), 400
        sql += " WHERE d.date = ?"
        params = (day,)
    sql += " ORDER BY e.start_dt, s.name"

    conn = get_db()
    try:
        rows = conn.execute(sql, params).fetchall()
        return jsonify([dict(r) for r in rows])
    finally:
        conn.close()


@app.post("/api/events")
def create_event():
    body = request.get_json(silent=True)
    if not isinstance(body, dict):
        return jsonify(error="request body must be a JSON object"), 400

    required = ("artist_id", "stage_id", "day_id", "start_dt")
    missing = [f for f in required if body.get(f) in (None, "")]
    if missing:
        return jsonify(error=f"missing fields: {', '.join(missing)}"), 400

    for f in ("artist_id", "stage_id", "day_id"):
        v = body[f]
        if isinstance(v, bool) or not isinstance(v, int):
            return jsonify(error=f"{f} must be an integer"), 400

    try:
        start = datetime.strptime(str(body["start_dt"]), DT_FORMAT)
    except ValueError:
        return jsonify(error="start_dt must be in format YYYY-MM-DD HH:MM:SS"), 400
    start_dt = start.strftime(DT_FORMAT)
    end_dt = (start + timedelta(minutes=DURATION_MIN)).strftime(DT_FORMAT)

    conn = get_db()
    try:
        cur = conn.execute(
            """INSERT INTO Event (event_type_id, day_id, stage_id, artist_id,
                                  start_dt, end_dt, duration_min)
               VALUES ((SELECT event_type_id FROM EventType WHERE code = 'performance'),
                       ?, ?, ?, ?, ?, ?)""",
            (body["day_id"], body["stage_id"], body["artist_id"], start_dt, end_dt, DURATION_MIN),
        )
        conn.commit()
        row = conn.execute("SELECT * FROM Event WHERE event_id = ?", (cur.lastrowid,)).fetchone()
        return jsonify(dict(row)), 201
    except sqlite3.IntegrityError as exc:
        conn.rollback()
        return jsonify(error=f"integrity error: {exc} "
                             "(check that artist_id, stage_id and day_id exist)"), 400
    finally:
        conn.close()


@app.delete("/api/events/<int:event_id>")
def delete_event(event_id):
    conn = get_db()
    try:
        cur = conn.execute("DELETE FROM Event WHERE event_id = ?", (event_id,))
        conn.commit()
        if cur.rowcount == 0:
            return jsonify(error="event not found"), 404
    except sqlite3.IntegrityError as exc:
        conn.rollback()
        return jsonify(error=f"cannot delete: {exc}"), 409
    finally:
        conn.close()
    return "", 204


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 8080)), debug=True)
