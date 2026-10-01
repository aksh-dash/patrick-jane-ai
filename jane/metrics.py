"""Live host telemetry for the SYSTEM STATUS panel."""
from __future__ import annotations

import shutil
import subprocess
import time

import psutil

_DISK_REF_BPS = 200 * 1024 * 1024  # 200 MB/s treated as "100% busy" when busy_time is absent

_prev_net = psutil.net_io_counters()
_prev_disk = psutil.disk_io_counters()
_prev_t = time.time()

_HAS_NVIDIA = shutil.which("nvidia-smi") is not None
_gpu_cache = (0.0, None)  # (timestamp, value)


def _gpu_percent() -> float | None:
    """NVIDIA only. Returns None when no supported GPU probe exists."""
    global _gpu_cache
    if not _HAS_NVIDIA:
        return None
    now = time.time()
    if now - _gpu_cache[0] < 2.0:
        return _gpu_cache[1]
    try:
        out = subprocess.run(
            ["nvidia-smi", "--query-gpu=utilization.gpu", "--format=csv,noheader,nounits"],
            capture_output=True, text=True, timeout=3,
        )
        value = float(out.stdout.strip().splitlines()[0])
    except Exception:
        value = None
    _gpu_cache = (now, value)
    return value


def _human_rate(bps: float) -> str:
    if bps >= 1024 * 1024:
        return f"{bps / 1024 / 1024:.1f}M/s"
    return f"{bps / 1024:.1f}K/s"


def sample() -> dict:
    """One telemetry frame. Rates are deltas since the previous call."""
    global _prev_net, _prev_disk, _prev_t

    now = time.time()
    elapsed = max(now - _prev_t, 1e-3)

    net = psutil.net_io_counters()
    disk = psutil.disk_io_counters()

    net_bps = ((net.bytes_sent - _prev_net.bytes_sent)
               + (net.bytes_recv - _prev_net.bytes_recv)) / elapsed

    disk_busy = getattr(disk, "busy_time", None)
    prev_busy = getattr(_prev_disk, "busy_time", None)
    if disk_busy is not None and prev_busy is not None:
        disk_pct = min(100.0, (disk_busy - prev_busy) / (elapsed * 1000.0) * 100.0)
    else:
        disk_bps = ((disk.read_bytes - _prev_disk.read_bytes)
                    + (disk.write_bytes - _prev_disk.write_bytes)) / elapsed
        disk_pct = min(100.0, disk_bps / _DISK_REF_BPS * 100.0)

    _prev_net, _prev_disk, _prev_t = net, disk, now

    gpu = _gpu_percent()
    return {
        "cpu": round(psutil.cpu_percent(interval=None), 1),
        "mem": round(psutil.virtual_memory().percent, 1),
        "net": round(net_bps, 1),
        "net_label": _human_rate(net_bps),
        "gpu": None if gpu is None else round(gpu, 1),
        "disk": round(disk_pct, 1),
        "uptime": int(now - psutil.boot_time()),
    }


def summary() -> str:
    """Compact one-liner Jane can read out loud."""
    s = sample()
    gpu = "unavailable" if s["gpu"] is None else f"{s['gpu']}%"
    return (f"CPU {s['cpu']}%, memory {s['mem']}%, disk {s['disk']}%, "
            f"GPU {gpu}, network {s['net_label']}")
