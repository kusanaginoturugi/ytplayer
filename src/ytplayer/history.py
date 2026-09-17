from __future__ import annotations

import sqlite3
from pathlib import Path
from time import time

from .models import Track


class History:
    """Append-only play log plus an explainable, decaying preference profile."""

    def __init__(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(path)
        self.db.row_factory = sqlite3.Row
        self.db.executescript("""
            PRAGMA journal_mode=WAL;
            CREATE TABLE IF NOT EXISTS plays (
              id INTEGER PRIMARY KEY, played_at REAL NOT NULL, video_id TEXT NOT NULL,
              title TEXT NOT NULL, artist TEXT, url TEXT NOT NULL,
              selected_field TEXT, selected_value TEXT
            );
            CREATE TABLE IF NOT EXISTS preferences (
              field TEXT NOT NULL, value TEXT NOT NULL, score REAL NOT NULL DEFAULT 0,
              updated_at REAL NOT NULL, PRIMARY KEY(field, value)
            );
            CREATE INDEX IF NOT EXISTS plays_video_time ON plays(video_id, played_at DESC);
            CREATE TABLE IF NOT EXISTS favorites (
              video_id TEXT PRIMARY KEY, title TEXT NOT NULL, url TEXT NOT NULL,
              artist TEXT, singer TEXT, songwriter TEXT, composer TEXT, genre TEXT,
              lyrics TEXT, duration INTEGER, thumbnail TEXT, added_at REAL NOT NULL
            );
        """)
        columns = {row[1] for row in self.db.execute("PRAGMA table_info(favorites)")}
        if "thumbnail" not in columns:
            self.db.execute("ALTER TABLE favorites ADD COLUMN thumbnail TEXT")
            self.db.commit()

    def record_play(self, track: Track, selected: tuple[str, str] | None = None) -> None:
        now = time()
        field, value = selected or (None, None)
        self.db.execute(
            "INSERT INTO plays(played_at,video_id,title,artist,url,selected_field,selected_value) VALUES(?,?,?,?,?,?,?)",
            (now, track.id, track.title, track.artist, track.url, field, value),
        )
        # A selection is a strong signal; listening is a softer signal for all usable facets.
        for name, facet in track.facets().items():
            if facet:
                self._add(name, facet, 1.0, now)
        if field and value:
            self._add(field, value, 7.0, now)
        self.db.commit()

    def _add(self, field: str, value: str, amount: float, now: float) -> None:
        row = self.db.execute("SELECT score,updated_at FROM preferences WHERE field=? AND value=?", (field, value)).fetchone()
        # Half-life is 45 days: recent intent matters most, history is never discarded.
        score = 0.0 if row is None else row["score"] * 0.5 ** ((now - row["updated_at"]) / (45 * 86400))
        self.db.execute("""
            INSERT INTO preferences(field,value,score,updated_at) VALUES(?,?,?,?)
            ON CONFLICT(field,value) DO UPDATE SET score=excluded.score, updated_at=excluded.updated_at
        """, (field, value, score + amount, now))

    def score(self, track: Track) -> float:
        score = 0.0
        now = time()
        for field, value in track.facets().items():
            if not value:
                continue
            row = self.db.execute("SELECT score,updated_at FROM preferences WHERE field=? AND value=?", (field, value)).fetchone()
            if row:
                score += row["score"] * 0.5 ** ((now - row["updated_at"]) / (45 * 86400))
        # Do not loop the same video repeatedly, even if it is loved.
        recent = self.db.execute("SELECT played_at FROM plays WHERE video_id=? ORDER BY played_at DESC LIMIT 1", (track.id,)).fetchone()
        if recent:
            age_hours = (now - recent["played_at"]) / 3600
            score -= max(0, 10 - age_hours / 3)
        return score

    def recent_video_ids(self, limit: int = 100) -> set[str]:
        """Tracks in the recent rotation; their full log remains untouched."""
        rows = self.db.execute(
            "SELECT video_id FROM plays ORDER BY played_at DESC, id DESC LIMIT ?", (limit,)
        ).fetchall()
        return {row["video_id"] for row in rows}

    def toggle_favorite(self, track: Track) -> bool:
        """Return True when added and False when removed."""
        exists = self.db.execute("SELECT 1 FROM favorites WHERE video_id=?", (track.id,)).fetchone()
        if exists:
            self.db.execute("DELETE FROM favorites WHERE video_id=?", (track.id,))
            self.db.commit()
            return False
        self.db.execute("""
            INSERT INTO favorites(video_id,title,url,artist,singer,songwriter,composer,genre,lyrics,duration,thumbnail,added_at)
            VALUES(?,?,?,?,?,?,?,?,?,?,?,?)
        """, (
            track.id, track.title, track.url, track.artist, track.singer, track.songwriter,
            track.composer, track.genre, track.lyrics, track.duration, track.thumbnail, time(),
        ))
        self.db.commit()
        return True

    def is_favorite(self, video_id: str) -> bool:
        return self.db.execute("SELECT 1 FROM favorites WHERE video_id=?", (video_id,)).fetchone() is not None

    def favorites(self) -> list[Track]:
        rows = self.db.execute("SELECT * FROM favorites ORDER BY added_at DESC").fetchall()
        return [Track(
            id=row["video_id"], title=row["title"], url=row["url"], artist=row["artist"] or "",
            singer=row["singer"] or "", songwriter=row["songwriter"] or "",
            composer=row["composer"] or "", genre=row["genre"] or "",
            lyrics=row["lyrics"] or "", duration=row["duration"], thumbnail=row["thumbnail"] or "",
        ) for row in rows]

    def close(self) -> None:
        self.db.close()
