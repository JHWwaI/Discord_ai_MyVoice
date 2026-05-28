"""Tier 3 fine-tune 작업 큐 — SQLite 테이블 `tier3_jobs` 접근."""
from dataclasses import dataclass

from db.database import get_connection


@dataclass
class Tier3Job:
    job_id: int
    user_id: int
    guild_id: int
    status: str          # queued · training · ready · failed
    wav_count: int
    wav_dir: str | None
    ckpt_path: str | None
    error: str | None
    submitted_at: str
    started_at: str | None
    completed_at: str | None


class Tier3Repository:
    def submit(self, user_id: int, guild_id: int, wav_dir: str, wav_count: int) -> int:
        with get_connection() as conn:
            cur = conn.execute(
                "INSERT INTO tier3_jobs (user_id, guild_id, wav_dir, wav_count) VALUES (?, ?, ?, ?)",
                (user_id, guild_id, wav_dir, wav_count),
            )
            conn.commit()
            return cur.lastrowid

    def update_status(self, job_id: int, status: str, error: str | None = None,
                       ckpt_path: str | None = None) -> None:
        ts_field = {
            "training":  "started_at",
            "ready":     "completed_at",
            "failed":    "completed_at",
        }.get(status)
        with get_connection() as conn:
            if ts_field:
                conn.execute(
                    f"UPDATE tier3_jobs SET status=?, error=?, ckpt_path=?, "
                    f"{ts_field}=strftime('%Y-%m-%d %H:%M:%S','now','localtime') "
                    f"WHERE job_id=?",
                    (status, error, ckpt_path, job_id),
                )
            else:
                conn.execute(
                    "UPDATE tier3_jobs SET status=?, error=?, ckpt_path=? WHERE job_id=?",
                    (status, error, ckpt_path, job_id),
                )
            conn.commit()

    def latest_for(self, user_id: int, guild_id: int) -> Tier3Job | None:
        with get_connection() as conn:
            row = conn.execute(
                "SELECT * FROM tier3_jobs WHERE user_id=? AND guild_id=? "
                "ORDER BY job_id DESC LIMIT 1",
                (user_id, guild_id),
            ).fetchone()
        if not row:
            return None
        return Tier3Job(
            job_id=row["job_id"], user_id=row["user_id"], guild_id=row["guild_id"],
            status=row["status"], wav_count=row["wav_count"], wav_dir=row["wav_dir"],
            ckpt_path=row["ckpt_path"], error=row["error"],
            submitted_at=row["submitted_at"], started_at=row["started_at"],
            completed_at=row["completed_at"],
        )

    def queued(self) -> list[Tier3Job]:
        with get_connection() as conn:
            rows = conn.execute(
                "SELECT * FROM tier3_jobs WHERE status='queued' ORDER BY job_id ASC"
            ).fetchall()
        return [Tier3Job(**dict(r)) for r in rows]
