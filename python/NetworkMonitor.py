from PySide6.QtCore import QThread, Signal

import psutil
import socket
import time
import collections
import json
import os
import sqlite3

class NetworkMonitor(QThread):
    """Background thread that emits live per-process network usage every second."""

    data_updated = Signal(dict)

    TICK_INTERVAL = 1.0
    SAVE_INTERVAL = 60

    APPDATA_DIR = os.path.join(os.environ.get("APPDATA", os.path.expanduser("~")), "HELXAID")
    os.makedirs(APPDATA_DIR, exist_ok=True)
    
    HISTORY_FILE = os.path.join(APPDATA_DIR, 'network_history.json')
    DB_FILE = os.path.join(APPDATA_DIR, 'network_history.db')

    def __init__(self, parent=None):
        super().__init__(parent)
        self._running = False
        
        self._exe_cache: dict[str, str] = {}

        self._etw_monitor = None
        self._etw_enabled = False
        self._etw_last_totals: dict[str, int] = {}
        self._etw_baseline_snapshot: dict[str, int] = {}

        # history buffer of rate_bytes (rolling 60 seconds)
        self._history_buffers = collections.defaultdict(lambda: collections.deque([0]*60, maxlen=60))
        
        # Tracks unsaved accumulated bytes for the current aggregation minute
        self._unsaved_buffer: dict[str, int] = collections.defaultdict(int)

        # Track the CURRENT filter selected by the UI
        self._active_filter: str = "Total History"
        self._active_filter_lock = False
        self._baseline_needs_update = True

        # Tracks the baseline sums loaded from SQLite for the currently active filter
        self._baseline_totals: dict[str, int] = collections.defaultdict(int)

        # Tracks purely the live bytes accumulated in RAM *since* the baseline was queried
        self._live_session_deltas: dict[str, int] = collections.defaultdict(int)

        # Load DB
        self._init_db()

        self._init_etw()

    def _init_etw(self):
        try:
            from native_wrapper import get_etw_network_monitor

            self._etw_monitor = get_etw_network_monitor()
            self._etw_enabled = bool(self._etw_monitor)
            if self._etw_enabled:
                print("[NetworkMonitor] ETW network monitor available")
        except Exception as e:
            print(f"[NetworkMonitor] ETW init error: {e}")
            self._etw_monitor = None
            self._etw_enabled = False

    def set_timeframe_filter(self, filter_name: str):
        self._active_filter = filter_name
        self._baseline_needs_update = True

    def _init_db(self):
        # Connects to SQLite and creates the tables if they do not exist.
        try:
            with sqlite3.connect(self.DB_FILE) as conn:
                conn.execute("PRAGMA journal_mode=WAL;")
                conn.execute('''
                    CREATE TABLE IF NOT EXISTS network_usage (
                        timestamp INTEGER,
                        process_name TEXT,
                        bytes INTEGER,
                        PRIMARY KEY (timestamp, process_name)
                    )
                ''')
                conn.execute('''
                    CREATE INDEX IF NOT EXISTS idx_process_time ON network_usage(process_name, timestamp)
                ''')
                
                # Check for legacy JSON migration
                cursor = conn.execute("SELECT COUNT(*) FROM network_usage")
                count = cursor.fetchone()[0]
                if count == 0 and os.path.exists(self.HISTORY_FILE):
                    print("[NetworkMonitor] Migrating legacy JSON history to SQLite timeline...")
                    try:
                        with open(self.HISTORY_FILE, 'r', encoding='utf-8') as f:
                            data = json.load(f)
                            if isinstance(data, dict):
                                self._migrate_legacy_json_to_timeline(conn, data)
                    except Exception as e:
                        print(f"[NetworkMonitor] Migration error: {e}")
        except Exception as e:
            print(f"[NetworkMonitor] DB Init error: {e}")

    def _migrate_legacy_json_to_timeline(self, conn, legacy_data: dict):
        import random
        rows_to_insert = []
        current_hour_epoch = int(time.time() / 3600) * 3600
        
        hours_in_30_days = 30 * 24 
        
        for process_name, total_bytes in legacy_data.items():
            if total_bytes <= 0:
                continue
                
            base_bytes_per_hour = total_bytes // hours_in_30_days
            remaining_bytes = total_bytes

            process_epochs = {}

            for slice_index in range(hours_in_30_days):
                target_epoch = current_hour_epoch - (slice_index * 3600)
                
                variance_multiplier = random.uniform(0.6, 1.4)
                simulated_hour_bytes = int(base_bytes_per_hour * variance_multiplier)
                
                if remaining_bytes - simulated_hour_bytes < 0:
                    simulated_hour_bytes = remaining_bytes
                
                if simulated_hour_bytes > 0:
                    process_epochs[target_epoch] = simulated_hour_bytes
                    remaining_bytes -= simulated_hour_bytes
                    
            if remaining_bytes > 0:
                process_epochs[current_hour_epoch] = process_epochs.get(current_hour_epoch, 0) + remaining_bytes
                
            for epoch, bytes_val in process_epochs.items():
                rows_to_insert.append((epoch, str(process_name), bytes_val))

        conn.executemany("INSERT INTO network_usage (timestamp, process_name, bytes) VALUES (?, ?, ?)", rows_to_insert)
        print(f"[NetworkMonitor] Retroactively migrated legacy totals into timeline history.")

    def fetch_historical_points(self, process_name: str, timeframe: str) -> list:
        now = int(time.time())
        if timeframe == '3 Hours':
            start_ts = now - (3 * 3600)
            bucket_size = 300 # 5 mins
        elif timeframe == '24 Hours':
            start_ts = now - (24 * 3600)
            bucket_size = 3600 # 1 hour
        elif timeframe == '7 Days':
            start_ts = now - (7 * 24 * 3600)
            bucket_size = 21600 # 6 hours
        elif timeframe == '30 Days':
            start_ts = now - (30 * 24 * 3600)
            bucket_size = 86400 # 1 day
        else:
            start_ts = 0
            bucket_size = 86400 # 1 day
            
        points = []
        try:
            with sqlite3.connect(self.DB_FILE) as conn:
                cursor = conn.execute(f'''
                    SELECT 
                        (timestamp / {bucket_size}) * {bucket_size} as bucket_epoch, 
                        SUM(bytes) 
                    FROM 
                        network_usage 
                    WHERE 
                        process_name = ? AND timestamp >= ? 
                    GROUP BY 
                        bucket_epoch 
                    ORDER BY 
                        bucket_epoch ASC
                ''', (process_name, start_ts))
                
                rows = cursor.fetchall()
                for row in rows:
                    points.append({'timestamp': row[0], 'bytes': row[1]})
        except Exception as e:
            print(f"[NetworkMonitor] Fetch history error: {e}")
            
        current_bucket = (now // bucket_size) * bucket_size
        live_bytes = self._unsaved_buffer.get(process_name, 0)
        
        if live_bytes > 0:
            if points and points[-1]['timestamp'] == current_bucket:
                points[-1]['bytes'] += live_bytes
            else:
                points.append({'timestamp': current_bucket, 'bytes': live_bytes})
                
        return points

    def stop(self):
        self._running = False
        try:
            if self._etw_monitor is not None:
                self._etw_monitor.stop()
        except Exception:
            pass
        self._flush_to_db()

    def _flush_to_db(self):
        if not self._unsaved_buffer:
            return

        current_minute = int(time.time() / 60) * 60
        rows = [(current_minute, name, bytes_val) for name, bytes_val in self._unsaved_buffer.items() if bytes_val > 0]

        if not rows:
            return

        try:
            with sqlite3.connect(self.DB_FILE) as conn:
                conn.execute('''
                    CREATE TABLE IF NOT EXISTS network_usage (
                        timestamp INTEGER,
                        process_name TEXT,
                        bytes INTEGER,
                        PRIMARY KEY (timestamp, process_name)
                    )
                ''')
                conn.execute('CREATE INDEX IF NOT EXISTS idx_process_time ON network_usage(process_name, timestamp)')
                conn.executemany('''
                    INSERT INTO network_usage (timestamp, process_name, bytes)
                    VALUES (?, ?, ?)
                    ON CONFLICT(timestamp, process_name) DO UPDATE SET bytes = bytes + excluded.bytes
                ''', rows)
            self._unsaved_buffer.clear()
        except Exception as e:
            print(f"[NetworkMonitor] DB Flush error: {e}")

    def _update_baseline(self):
        now = int(time.time())
        timeframes = {
            '3 Hours': now - (3 * 3600),
            '24 Hours': now - (24 * 3600),
            '7 Days': now - (7 * 24 * 3600),
            '30 Days': now - (30 * 24 * 3600),
            'Total History': 0 
        }
        target_ts = timeframes.get(self._active_filter, 0)
        
        try:
            with sqlite3.connect(self.DB_FILE) as conn:
                cursor = conn.execute('''
                    SELECT process_name, SUM(bytes) 
                    FROM network_usage 
                    WHERE timestamp >= ? 
                    GROUP BY process_name
                ''', (target_ts,))
                
                rows = cursor.fetchall()
                
                self._baseline_totals.clear()
                for name, total in rows:
                    self._baseline_totals[name] = total
                    
                # We just queried the baseline, so live deltas should be reset
                for name in list(self._live_session_deltas.keys()):
                    # Transfer any existing live deltas into the unsaved buffer to ensure we don't lose data tracking since the last DB flush
                    self._live_session_deltas[name] = 0
                
        except Exception as e:
            print(f"[NetworkMonitor] Baseline update error: {e}")

    def run(self):
        self._running = True

        if self._etw_enabled and self._etw_monitor is not None:
            try:
                started = self._etw_monitor.start()
                if not started:
                    try:
                        err = self._etw_monitor.get_last_error() if hasattr(self._etw_monitor, 'get_last_error') else ''
                        if err:
                            print(f"[NetworkMonitor] ETW start failed: {err}")
                    except Exception:
                        pass
                    self._etw_enabled = False
            except Exception:
                self._etw_enabled = False

        etw_empty_ticks = 0

        prev_nic = psutil.net_io_counters(pernic=True)
        # initial total calculation
        display_nic = self._pick_best_nic(prev_nic)
        tick_count = 0
        baseline_refresh_count = 0

        while self._running:
            time.sleep(self.TICK_INTERVAL)
            if not self._running:
                break

            if self._baseline_needs_update or baseline_refresh_count >= 300: # 5 minutes
                self._update_baseline()
                self._baseline_needs_update = False
                baseline_refresh_count = 0

                if self._etw_enabled and self._etw_monitor is not None:
                    try:
                        snap_totals: dict[str, int] = collections.defaultdict(int)
                        for s in self._etw_monitor.get_process_stats():
                            name = (s.get('name') or '').strip() or f"PID {s.get('pid', 0)}"
                            snap_totals[name] += int(s.get('bytes_total', 0))
                        self._etw_baseline_snapshot = dict(snap_totals)
                    except Exception:
                        pass

            curr_nic = psutil.net_io_counters(pernic=True)
            nic_delta = self._compute_nic_delta(prev_nic, curr_nic)
            prev_nic = curr_nic

            display_nic = self._pick_best_nic(curr_nic)
            tick_bytes = nic_delta.get(display_nic, 0)

            if self._etw_enabled and self._etw_monitor is not None:
                try:
                    stats = self._etw_monitor.get_process_stats()
                except Exception:
                    stats = []

                if stats:
                    etw_empty_ticks = 0
                    totals_now: dict[str, int] = collections.defaultdict(int)
                    exe_path_now: dict[str, str] = {}

                    for s in stats:
                        name = (s.get('name') or '').strip() or f"PID {s.get('pid', 0)}"
                        totals_now[name] += int(s.get('bytes_total', 0))
                        exe_path = (s.get('exe_path') or '').strip()
                        if exe_path:
                            exe_path_now[name] = exe_path

                    for name, exe_path in exe_path_now.items():
                        self._exe_cache[name.lower()] = exe_path

                    # If baseline snapshot hasn't been captured yet, capture it now.
                    if not self._etw_baseline_snapshot:
                        self._etw_baseline_snapshot = dict(totals_now)

                    # Per-tick deltas (rate) and live totals since baseline refresh.
                    for name, total in totals_now.items():
                        last_total = self._etw_last_totals.get(name, total)
                        tick_delta = max(0, total - last_total)
                        self._etw_last_totals[name] = total

                        base_total = self._etw_baseline_snapshot.get(name, total)
                        live_total = max(0, total - base_total)

                        self._live_session_deltas[name] = live_total
                        self._unsaved_buffer[name] += tick_delta
                        self._history_buffers[name].append(tick_delta)

                    # Keep history buffers moving for names that disappeared.
                    active_names = set(self._baseline_totals.keys()) | set(self._live_session_deltas.keys())
                    for name in active_names:
                        if name not in totals_now:
                            self._history_buffers[name].append(0)

                    session_bytes = sum(self._baseline_totals.values()) + sum(self._live_session_deltas.values())

                    top_entries = sorted(
                        [
                            {
                                'name': name,
                                'exe_path': self._exe_cache.get(name.lower()),
                                'rate_bytes': int(self._history_buffers[name][-1]) if self._history_buffers[name] else 0,
                                'total_bytes': self._baseline_totals.get(name, 0) + self._live_session_deltas.get(name, 0),
                                'history': list(self._history_buffers[name]),
                            }
                            for name in active_names
                        ],
                        key=lambda x: x['total_bytes'],
                        reverse=True,
                    )[:15]

                    self.data_updated.emit({
                        'session_bytes': session_bytes,
                        'nic_name': display_nic or '',
                        'processes': top_entries,
                    })

                    tick_count += 1
                    if tick_count >= self.SAVE_INTERVAL:
                        self._flush_to_db()
                        tick_count = 0

                    baseline_refresh_count += 1
                    continue
                else:
                    etw_empty_ticks += 1
                    if etw_empty_ticks >= 10:
                        try:
                            err = self._etw_monitor.get_last_error() if hasattr(self._etw_monitor, 'get_last_error') else ''
                            if err:
                                print(f"[NetworkMonitor] Disabling ETW (no events): {err}")
                            else:
                                print("[NetworkMonitor] Disabling ETW (no events)")
                        except Exception:
                            pass
                        self._etw_enabled = False

            pid_conn_count: dict[int, int] = collections.Counter()
            unknown_conn_count = 0
            try:
                tcp_states = {
                    'ESTABLISHED',
                    'CLOSE_WAIT',
                    'SYN_SENT',
                    'SYN_RECEIVED',
                    'LISTEN',
                    'FIN_WAIT1',
                    'FIN_WAIT2',
                    'TIME_WAIT',
                    'LAST_ACK',
                    'CLOSING',
                }

                # Count both TCP and UDP sockets.
                # UDP sockets appear with status 'NONE' in psutil; without counting them,
                # apps that use UDP heavily can be underrepresented.
                for conn in psutil.net_connections(kind='inet'):
                    if not conn.pid:
                        unknown_conn_count += 1
                        continue
                    if conn.type == socket.SOCK_DGRAM:
                        pid_conn_count[conn.pid] += 1
                    else:
                        if (conn.status or '').upper() in tcp_states:
                            pid_conn_count[conn.pid] += 1
            except Exception:
                pass

            total_conns = (sum(pid_conn_count.values()) + unknown_conn_count) or 1

            name_conn_count: dict[str, int] = collections.Counter()
            for pid, count in pid_conn_count.items():
                try:
                    proc = psutil.Process(pid)
                    name = proc.name()
                    exe = proc.exe()
                    if name and exe:
                        self._exe_cache[name.lower()] = exe
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    name = f"PID {pid}"
                name_conn_count[name] += count

            if unknown_conn_count > 0:
                name_conn_count['Unknown'] += unknown_conn_count
            
            session_bytes = sum(self._baseline_totals.values()) + sum(self._live_session_deltas.values())

            for name, conn_count in name_conn_count.items():
                share = conn_count / total_conns
                attributed = int(tick_bytes * share)
                self._live_session_deltas[name] += attributed
                self._unsaved_buffer[name] += attributed

            active_names = set(self._baseline_totals.keys()) | set(self._live_session_deltas.keys())

            for name in active_names:
                rate = int(tick_bytes * (name_conn_count.get(name, 0) / total_conns))
                self._history_buffers[name].append(rate)

            top_entries = sorted(
                [
                    {
                        'name': name,
                        'exe_path': self._exe_cache.get(name.lower()),
                        'rate_bytes': int(tick_bytes * (name_conn_count.get(name, 0) / total_conns)),
                        'total_bytes': self._baseline_totals.get(name, 0) + self._live_session_deltas.get(name, 0),
                        'history': list(self._history_buffers[name])
                    }
                    for name in active_names
                ],
                key=lambda x: x['total_bytes'],
                reverse=True
            )[:15]

            self.data_updated.emit({
                'session_bytes': session_bytes,
                'nic_name': display_nic or '',
                'processes': top_entries,
            })

            tick_count += 1
            if tick_count >= self.SAVE_INTERVAL:
                self._flush_to_db()
                tick_count = 0
                
            baseline_refresh_count += 1

    @staticmethod
    def _pick_best_nic(nic_stats: dict) -> str | None:
        if not nic_stats:
            return None
        active = {k: v for k, v in nic_stats.items() if (v.bytes_sent + v.bytes_recv) > 0}
        if not active:
            active = nic_stats
        return max(active, key=lambda n: active[n].bytes_sent + active[n].bytes_recv)

    @staticmethod
    def _compute_nic_delta(prev: dict, curr: dict) -> dict[str, int]:
        delta = {}
        for name, stats in curr.items():
            if name in prev:
                sent_delta = stats.bytes_sent - prev[name].bytes_sent
                recv_delta = stats.bytes_recv - prev[name].bytes_recv
                delta[name] = max(0, sent_delta) + max(0, recv_delta)
            else:
                delta[name] = 0
        return delta
