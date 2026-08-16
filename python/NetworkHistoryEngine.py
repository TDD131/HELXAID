"""
Network History Analytics Engine for HELXTATS.
Provides high-performance analytical queries, timeline aggregations,
and export utilities for historical network data stored in SQLite.

Component Name: NetworkHistoryEngine
"""

import os
import sqlite3
import time
import csv
import json
from datetime import datetime, timedelta
from typing import Dict, List, Any, Tuple, Optional


def get_db_path() -> str:
    """Return the absolute path to the SQLite network history database."""
    appdata_dir = os.path.join(os.environ.get("APPDATA", os.path.expanduser("~")), "HELXAID")
    os.makedirs(appdata_dir, exist_ok=True)
    return os.path.join(appdata_dir, "network_history.db")


def _get_time_threshold(timeframe: str) -> int:
    """Calculate the starting timestamp epoch for a given timeframe string."""
    now = int(time.time())
    if timeframe == "Today":
        # Beginning of today (local time)
        today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
        return int(today.timestamp())
    elif timeframe == "3 Hours":
        return now - (3 * 3600)
    elif timeframe == "24 Hours":
        return now - (24 * 3600)
    elif timeframe == "Last 7 Days" or timeframe == "7 Days":
        return now - (7 * 24 * 3600)
    elif timeframe == "Last 30 Days" or timeframe == "30 Days":
        return now - (30 * 24 * 3600)
    elif timeframe == "All Time" or timeframe == "Total History":
        return 0
    return now - (30 * 24 * 3600)


def get_usage_summary(timeframe: str = "Last 30 Days") -> Dict[str, Any]:
    """
    Retrieve high-level metric summaries for hero cards:
    Total bytes, Daily average, Top bandwidth consumer app, Peak day, Active app count.
    """
    db_file = get_db_path()
    if not os.path.exists(db_file):
        return {
            "total_bytes": 0,
            "daily_avg_bytes": 0,
            "top_app_name": "None",
            "top_app_bytes": 0,
            "top_app_pct": 0.0,
            "peak_day_str": "N/A",
            "peak_day_bytes": 0,
            "active_apps_count": 0
        }

    start_ts = _get_time_threshold(timeframe)
    now = int(time.time())

    summary = {
        "total_bytes": 0,
        "daily_avg_bytes": 0,
        "top_app_name": "None",
        "top_app_bytes": 0,
        "top_app_pct": 0.0,
        "peak_day_str": "N/A",
        "peak_day_bytes": 0,
        "active_apps_count": 0
    }

    try:
        with sqlite3.connect(db_file, timeout=5.0) as conn:
            conn.execute("PRAGMA journal_mode=WAL;")
            
            # 1. Total bytes in timeframe
            cursor = conn.execute(
                "SELECT SUM(bytes), COUNT(DISTINCT process_name) FROM network_usage WHERE timestamp >= ?",
                (start_ts,)
            )
            row = cursor.fetchone()
            total_bytes = int(row[0]) if row and row[0] is not None else 0
            apps_count = int(row[1]) if row and row[1] is not None else 0
            summary["total_bytes"] = total_bytes
            summary["active_apps_count"] = apps_count

            # 2. Daily average
            if timeframe == "Today":
                num_days = 1
            elif timeframe in ("3 Hours", "24 Hours"):
                num_days = 1
            elif "7" in timeframe:
                num_days = 7
            elif "30" in timeframe:
                num_days = 30
            else:
                # All time
                cur_first = conn.execute("SELECT MIN(timestamp) FROM network_usage")
                first_row = cur_first.fetchone()
                if first_row and first_row[0]:
                    days_diff = max(1, (now - first_row[0]) // 86400)
                    num_days = days_diff
                else:
                    num_days = 1

            summary["daily_avg_bytes"] = total_bytes // max(1, num_days)

            # 3. Top process
            top_cursor = conn.execute(
                """
                SELECT process_name, SUM(bytes) as app_total
                FROM network_usage
                WHERE timestamp >= ?
                GROUP BY process_name
                ORDER BY app_total DESC
                LIMIT 1
                """,
                (start_ts,)
            )
            top_row = top_cursor.fetchone()
            if top_row:
                summary["top_app_name"] = str(top_row[0])
                summary["top_app_bytes"] = int(top_row[1])
                if total_bytes > 0:
                    summary["top_app_pct"] = round((summary["top_app_bytes"] / total_bytes) * 100.0, 1)

            # 4. Peak day
            # Group by 86400s (day boundary)
            peak_cursor = conn.execute(
                """
                SELECT (timestamp / 86400) * 86400 as day_epoch, SUM(bytes) as day_total
                FROM network_usage
                WHERE timestamp >= ?
                GROUP BY day_epoch
                ORDER BY day_total DESC
                LIMIT 1
                """,
                (start_ts,)
            )
            peak_row = peak_cursor.fetchone()
            if peak_row and peak_row[0]:
                peak_dt = datetime.fromtimestamp(peak_row[0])
                summary["peak_day_str"] = peak_dt.strftime("%d %b %Y")
                summary["peak_day_bytes"] = int(peak_row[1])

    except Exception as e:
        print(f"[NetworkHistoryEngine] Error in get_usage_summary: {e}")

    return summary


def get_daily_timeline(days: int = 30) -> List[Dict[str, Any]]:
    """
    Retrieve daily data usage totals for the last N days for the timeline bar chart.
    Ensures every single day is populated (with 0 if no traffic).
    """
    db_file = get_db_path()
    timeline: List[Dict[str, Any]] = []
    
    # Generate day buckets from (now - days) to today
    now_dt = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    day_map: Dict[str, int] = {}
    ordered_keys = []

    for i in range(days - 1, -1, -1):
        day_dt = now_dt - timedelta(days=i)
        date_key = day_dt.strftime("%Y-%m-%d")
        day_map[date_key] = 0
        ordered_keys.append((date_key, int(day_dt.timestamp()), day_dt.strftime("%d %b")))

    if os.path.exists(db_file):
        try:
            start_ts = int((now_dt - timedelta(days=days)).timestamp())
            with sqlite3.connect(db_file, timeout=5.0) as conn:
                conn.execute("PRAGMA journal_mode=WAL;")
                cursor = conn.execute(
                    """
                    SELECT date(timestamp, 'unixepoch', 'localtime') as day_str, SUM(bytes)
                    FROM network_usage
                    WHERE timestamp >= ?
                    GROUP BY day_str
                    """,
                    (start_ts,)
                )
                for row in cursor.fetchall():
                    if row[0] in day_map and row[1]:
                        day_map[row[0]] = int(row[1])
        except Exception as e:
            print(f"[NetworkHistoryEngine] Error in get_daily_timeline: {e}")

    for date_key, epoch_ts, label in ordered_keys:
        timeline.append({
            "date_key": date_key,
            "epoch": epoch_ts,
            "label": label,
            "bytes": day_map.get(date_key, 0)
        })

    return timeline


def get_top_apps(timeframe: str = "Last 30 Days", limit: int = 25) -> List[Dict[str, Any]]:
    """
    Retrieve top bandwidth consuming applications sorted descending by total bytes.
    """
    db_file = get_db_path()
    if not os.path.exists(db_file):
        return []

    start_ts = _get_time_threshold(timeframe)
    apps = []

    try:
        with sqlite3.connect(db_file, timeout=5.0) as conn:
            conn.execute("PRAGMA journal_mode=WAL;")
            
            # Fetch total bytes for percentage calculation
            total_cur = conn.execute(
                "SELECT SUM(bytes) FROM network_usage WHERE timestamp >= ?",
                (start_ts,)
            )
            tot_row = total_cur.fetchone()
            total_sum = int(tot_row[0]) if tot_row and tot_row[0] else 1

            cursor = conn.execute(
                """
                SELECT 
                    process_name, 
                    SUM(bytes) as app_bytes,
                    MIN(timestamp) as first_seen,
                    MAX(timestamp) as last_seen
                FROM network_usage
                WHERE timestamp >= ? AND process_name != 'Unknown' AND process_name NOT LIKE 'PID %'
                GROUP BY process_name
                ORDER BY app_bytes DESC
                LIMIT ?
                """,
                (start_ts, limit)
            )

            for row in cursor.fetchall():
                p_name = str(row[0])
                b_val = int(row[1])
                first_ts = int(row[2]) if row[2] else start_ts
                last_ts = int(row[3]) if row[3] else int(time.time())
                pct = round((b_val / total_sum) * 100.0, 1)

                apps.append({
                    "name": p_name,
                    "bytes": b_val,
                    "percentage": pct,
                    "first_seen": datetime.fromtimestamp(first_ts).strftime("%d/%m/%Y"),
                    "last_seen": datetime.fromtimestamp(last_ts).strftime("%d/%m %H:%M")
                })
    except Exception as e:
        print(f"[NetworkHistoryEngine] Error in get_top_apps: {e}")

    return apps


def export_history_to_csv(file_path: str, timeframe: str = "All Time") -> Tuple[bool, str]:
    """Export network timeline records to CSV file."""
    db_file = get_db_path()
    if not os.path.exists(db_file):
        return False, "Database file does not exist."

    start_ts = _get_time_threshold(timeframe)
    try:
        with sqlite3.connect(db_file, timeout=5.0) as conn:
            cursor = conn.execute(
                """
                SELECT 
                    datetime(timestamp, 'unixepoch', 'localtime') as datetime_str,
                    process_name,
                    bytes,
                    ROUND(bytes / (1024.0 * 1024.0), 2) as mb_val
                FROM network_usage
                WHERE timestamp >= ?
                ORDER BY timestamp DESC
                """,
                (start_ts,)
            )
            rows = cursor.fetchall()

        os.makedirs(os.path.dirname(os.path.abspath(file_path)), exist_ok=True)
        with open(file_path, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(["Timestamp", "Process Name", "Bytes", "MegaBytes (MB)"])
            writer.writerows(rows)

        return True, f"Successfully exported {len(rows)} records to {os.path.basename(file_path)}"
    except Exception as e:
        return False, f"Failed to export CSV: {str(e)}"


def export_history_to_json(file_path: str, timeframe: str = "All Time") -> Tuple[bool, str]:
    """Export network history dataset to structured JSON format."""
    db_file = get_db_path()
    if not os.path.exists(db_file):
        return False, "Database file does not exist."

    start_ts = _get_time_threshold(timeframe)
    try:
        with sqlite3.connect(db_file, timeout=5.0) as conn:
            cursor = conn.execute(
                """
                SELECT 
                    timestamp,
                    datetime(timestamp, 'unixepoch', 'localtime') as datetime_str,
                    process_name,
                    bytes
                FROM network_usage
                WHERE timestamp >= ?
                ORDER BY timestamp DESC
                """,
                (start_ts,)
            )
            records = []
            for row in cursor.fetchall():
                records.append({
                    "timestamp": row[0],
                    "datetime": row[1],
                    "process_name": row[2],
                    "bytes": row[3]
                })

        os.makedirs(os.path.dirname(os.path.abspath(file_path)), exist_ok=True)
        with open(file_path, "w", encoding="utf-8") as f:
            json.dump({
                "timeframe": timeframe,
                "exported_at": datetime.now().isoformat(),
                "total_records": len(records),
                "data": records
            }, f, indent=2)

        return True, f"Successfully exported {len(records)} records to {os.path.basename(file_path)}"
    except Exception as e:
        return False, f"Failed to export JSON: {str(e)}"


def purge_process_history(process_name: str) -> bool:
    """Delete all recorded history for a specific process."""
    db_file = get_db_path()
    if not os.path.exists(db_file):
        return False
    try:
        with sqlite3.connect(db_file, timeout=5.0) as conn:
            conn.execute("DELETE FROM network_usage WHERE process_name = ?", (process_name,))
        return True
    except Exception as e:
        print(f"[NetworkHistoryEngine] Error purging process history: {e}")
        return False


def clear_all_network_history() -> bool:
    """Safely wipe all recorded network history rows and reclaim SQLite disk space."""
    db_file = get_db_path()
    if not os.path.exists(db_file):
        return True
    try:
        with sqlite3.connect(db_file, timeout=5.0) as conn:
            conn.execute("DELETE FROM network_usage;")
            conn.execute("DELETE FROM nic_total;")
            conn.execute("VACUUM;")
        return True
    except Exception as e:
        print(f"[NetworkHistoryEngine] Error clearing history DB: {e}")
        return False
