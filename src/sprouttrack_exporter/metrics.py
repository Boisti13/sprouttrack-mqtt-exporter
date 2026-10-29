from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from .db import connect, query_one


def now_ms() -> int:
    return int(datetime.now(tz=timezone.utc).timestamp() * 1000)


def to_ms(v) -> int | None:
    """DB timestamp (epoch-ms number or ISO 8601 string) -> epoch ms, or None.

    Older Sprout Track versions stored epoch ms; since ~2026-10 the DB holds
    ISO 8601 UTC strings ('2026-10-11T17:40:00.000+00:00').
    """
    if v is None:
        return None
    if isinstance(v, (int, float)):
        return int(v)
    s = str(v).strip()
    if s.lstrip("-").isdigit():
        return int(s)
    return int(datetime.fromisoformat(s.replace("Z", "+00:00")).timestamp() * 1000)


def hhmm_since_ms(ms: int | None) -> str:
    """Convert (now - ms) to HH:MM. Returns 00:00 for None or negative."""
    if ms is None:
        return "00:00"
    delta_min = int((now_ms() - int(ms)) // 60000)
    if delta_min <= 0:
        return "00:00"
    hours = delta_min // 60
    minutes = delta_min % 60
    return f"{hours:02d}:{minutes:02d}"


def start_of_day_iso(tz_name: str) -> str:
    """Local midnight as UTC, in the DB's ISO format (compared as text in SQL)."""
    tz = timezone.utc if tz_name.upper() == "UTC" else ZoneInfo(tz_name)
    dt = datetime.now(tz=tz).replace(hour=0, minute=0, second=0, microsecond=0)
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000+00:00")


@dataclass(frozen=True)
class MetricsResult:
    values: dict


def query_metrics(db_path: str, baby_id: str, tz_name: str) -> MetricsResult:
    con = connect(db_path)
    cur = con.cursor()

    # Last feed time (any feed type)
    r = query_one(
        cur,
        """
        SELECT time
        FROM FeedLog
        WHERE babyId=? AND deletedAt IS NULL
        ORDER BY time DESC
        LIMIT 1;
        """,
        (baby_id,),
    )
    last_feed_ms = to_ms(r["time"]) if r else None

    # Breast feed side (LEFT/RIGHT/BOTH) for latest BREAST session (group by identical time)
    r = query_one(
        cur,
        """
        SELECT time
        FROM FeedLog
        WHERE babyId=? AND deletedAt IS NULL AND type='BREAST'
        ORDER BY time DESC
        LIMIT 1;
        """,
        (baby_id,),
    )
    last_breast_time = r["time"] if r else None  # compared as stored

    last_feed_side = None
    next_feed_side = None
    if last_breast_time is not None:
        cur.execute(
            """
            SELECT side
            FROM FeedLog
            WHERE babyId=? AND deletedAt IS NULL AND type='BREAST' AND time=?;
            """,
            (baby_id, last_breast_time),
        )

        sides = sorted(
            {
                (row["side"] or "").strip().upper()
                for row in cur.fetchall()
                if row["side"] is not None
            }
        )

        if "LEFT" in sides and "RIGHT" in sides:
            last_feed_side = "BOTH"
        elif "LEFT" in sides:
            last_feed_side = "LEFT"
        elif "RIGHT" in sides:
            last_feed_side = "RIGHT"

        # Rule: BOTH -> LEFT for next
        if last_feed_side == "LEFT":
            next_feed_side = "RIGHT"
        elif last_feed_side == "RIGHT":
            next_feed_side = "LEFT"
        elif last_feed_side == "BOTH":
            next_feed_side = "LEFT"

    # Last diaper
    r = query_one(
        cur,
        """
        SELECT time
        FROM DiaperLog
        WHERE babyId=? AND deletedAt IS NULL
        ORDER BY time DESC
        LIMIT 1;
        """,
        (baby_id,),
    )
    last_diaper_ms = to_ms(r["time"]) if r else None

    # Last sleep log
    r = query_one(
        cur,
        """
        SELECT startTime, endTime, type
        FROM SleepLog
        WHERE babyId=? AND deletedAt IS NULL
        ORDER BY startTime DESC
        LIMIT 1;
        """,
        (baby_id,),
    )

    last_sleep_start_ms = to_ms(r["startTime"]) if r else None
    last_sleep_end_ms = to_ms(r["endTime"]) if r else None
    last_sleep_type = (r["type"] if r else None)

    if r and r["endTime"] is None:
        sleep_state = last_sleep_type or "SLEEPING"
        sleeping = "on"
    else:
        sleep_state = "AWAKE"
        sleeping = "off"

    sod = start_of_day_iso(tz_name)

    r = query_one(
        cur,
        """
        SELECT COUNT(*) AS n
        FROM FeedLog
        WHERE babyId=? AND deletedAt IS NULL AND time >= ?;
        """,
        (baby_id, sod),
    )
    feeds_today = int(r["n"]) if r else 0

    r = query_one(
        cur,
        """
        SELECT COUNT(*) AS n
        FROM DiaperLog
        WHERE babyId=? AND deletedAt IS NULL AND time >= ?;
        """,
        (baby_id, sod),
    )
    diapers_today = int(r["n"]) if r else 0

    cur.execute(
        """
        SELECT duration
        FROM SleepLog
        WHERE babyId=? AND deletedAt IS NULL AND startTime >= ?;
        """,
        (baby_id, sod),
    )
    sleep_minutes_today = sum(int(row["duration"]) for row in cur.fetchall() if row["duration"] is not None)
    sleep_today = f"{sleep_minutes_today // 60:02d}:{sleep_minutes_today % 60:02d}"

    con.close()

    # Elapsed strings
    time_since_feed = hhmm_since_ms(last_feed_ms)
    time_since_diaper = hhmm_since_ms(last_diaper_ms)
    time_since_sleep_start = hhmm_since_ms(last_sleep_start_ms) if sleeping == "on" else "00:00"
    time_since_sleep_end = hhmm_since_ms(last_sleep_end_ms) if last_sleep_end_ms is not None else "00:00"

    return MetricsResult(
        values={
            "time_since_feed": time_since_feed,
            "time_since_diaper": time_since_diaper,
            "last_feed_side": last_feed_side,
            "next_feed_side": next_feed_side,
            "sleeping": sleeping,
            "sleep_state": sleep_state,
            "time_since_sleep_start": time_since_sleep_start,
            "time_since_sleep_end": time_since_sleep_end,
            "feeds_today": feeds_today,
            "diapers_today": diapers_today,
            "sleep_today": sleep_today,
        }
    )
