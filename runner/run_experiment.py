import csv
import os
import random
import subprocess
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

IMAGE = "twc:mvp"
OUT_CSV = "data/dataset.csv"

CLK_TCK = os.sysconf(os.sysconf_names["SC_CLK_TCK"])

@dataclass
class TelemetrySample:
    cpu_seconds: float        # total CPU time (user+sys) in seconds
    rss_bytes: int            # resident set size in bytes
    read_bytes: int           # bytes read (best-effort)
    write_bytes: int          # bytes written (best-effort)

def sh(cmd: list[str], check=True) -> str:
    r = subprocess.run(
        cmd,
        check=check,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    return (r.stdout or "").strip()

def is_running(name: str) -> bool:
    r = subprocess.run(
        ["docker", "inspect", "-f", "{{.State.Running}}", name],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
    )
    return r.stdout.strip().lower() == "true"

def get_exit_code(name: str) -> int:
    r = subprocess.run(
        ["docker", "inspect", "-f", "{{.State.ExitCode}}", name],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
    )
    try:
        return int(r.stdout.strip())
    except Exception:
        return 1

def get_container_pid(name: str) -> int:
    r = subprocess.run(
        ["docker", "inspect", "-f", "{{.State.Pid}}", name],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
    )
    try:
        return int(r.stdout.strip())
    except Exception:
        return 0

# ---------- /proc fallback (always available if pid exists) ----------

def proc_exists(pid: int) -> bool:
    return Path(f"/proc/{pid}").exists()

def read_proc_cpu_seconds(pid: int) -> float:
    # /proc/<pid>/stat: utime at field 14, stime at field 15 (clock ticks)
    with open(f"/proc/{pid}/stat", "r") as f:
        parts = f.read().split()
    utime_ticks = int(parts[13])
    stime_ticks = int(parts[14])
    return (utime_ticks + stime_ticks) / CLK_TCK

def read_proc_rss_bytes(pid: int) -> int:
    # /proc/<pid>/status: VmRSS in kB
    rss_kb = 0
    with open(f"/proc/{pid}/status", "r") as f:
        for line in f:
            if line.startswith("VmRSS:"):
                rss_kb = int(line.split()[1])
                break
    return rss_kb * 1024

def read_proc_io_bytes(pid: int) -> tuple[int, int]:
    # /proc/<pid>/io: read_bytes, write_bytes (bytes)
    read_b = 0
    write_b = 0
    with open(f"/proc/{pid}/io", "r") as f:
        for line in f:
            if line.startswith("read_bytes:"):
                read_b = int(line.split()[1])
            elif line.startswith("write_bytes:"):
                write_b = int(line.split()[1])
    return read_b, write_b

def sample_proc(pid: int) -> TelemetrySample:
    cpu_s = read_proc_cpu_seconds(pid)
    rss_b = read_proc_rss_bytes(pid)
    r_b, w_b = read_proc_io_bytes(pid)
    return TelemetrySample(cpu_s, rss_b, r_b, w_b)

# ---------- cgroup v2 (preferred when present) ----------

def get_cgroup_dir_from_pid(pid: int) -> Optional[Path]:
    # cgroup v2 line: "0::/system.slice/docker-<id>.scope"
    try:
        with open(f"/proc/{pid}/cgroup", "r") as f:
            for line in f:
                parts = line.strip().split(":")
                if len(parts) == 3 and parts[0] == "0":
                    rel = parts[2]
                    return Path("/sys/fs/cgroup") / rel.lstrip("/")
    except FileNotFoundError:
        return None
    return None

def read_kv_file(path: Path) -> dict[str, int]:
    d: dict[str, int] = {}
    for ln in path.read_text().strip().splitlines():
        if not ln.strip():
            continue
        k, v = ln.split()
        d[k] = int(v)
    return d

def cgroup_available(cg: Path) -> bool:
    # We require at least memory.current and cpu.stat to be present.
    return (cg / "memory.current").exists() and (cg / "cpu.stat").exists()

def sample_cgroup(cg: Path) -> TelemetrySample:
    # CPU usage in usec via cpu.stat (usage_usec)
    cpu = read_kv_file(cg / "cpu.stat")
    usage_usec = cpu.get("usage_usec", 0)
    cpu_s = usage_usec / 1e6

    rss_b = int((cg / "memory.current").read_text().strip())

    # io.stat sums rbytes/wbytes across devices
    rbytes = 0
    wbytes = 0
    io_path = cg / "io.stat"
    if io_path.exists():
        for ln in io_path.read_text().strip().splitlines():
            toks = ln.split()
            for t in toks[1:]:
                if t.startswith("rbytes="):
                    rbytes += int(t.split("=", 1)[1])
                elif t.startswith("wbytes="):
                    wbytes += int(t.split("=", 1)[1])

    return TelemetrySample(cpu_s, rss_b, rbytes, wbytes)

# ---------- runner ----------

def run_one(workload: str, N: int, intensity: str, rep: int,
            hold_ms: int = 750, poll_interval_s: float = 0.2) -> dict:
    run_id = str(uuid.uuid4())
    name = f"twc_{workload}_{intensity}_{rep}_{run_id[:8]}"

    cmd = [
        "docker", "run", "-d",
        "--name", name,
        "--cpus=1",
        "--memory=512m",
        "--network", "none",
        IMAGE,
        "--workload", workload,
        "--N", str(N),
        "--hold_ms", str(hold_ms),
    ]

    t0 = time.monotonic_ns()
    _cid = sh(cmd, check=True)

    # Get PID; if it's 0, container likely exited instantly
    pid = get_container_pid(name)
    if pid <= 0:
        exit_code = get_exit_code(name)
        subprocess.run(["docker", "rm", "-f", name], check=False, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        t1 = time.monotonic_ns()
        return {
            "run_id": run_id,
            "workload": workload,
            "intensity": intensity,
            "N": N,
            "rep": rep,
            "runtime_ms": (t1 - t0) / 1e6,
            "avg_cpu_percent": 0.0,
            "max_mem_mib": 0.0,
            "blk_read_mib": 0.0,
            "blk_write_mib": 0.0,
            "exit_code": exit_code,
        }

    cg = get_cgroup_dir_from_pid(pid)
    use_cg = (cg is not None and cgroup_available(cg))

    # Baseline sample (retry a bit in case the cgroup appears slightly later)
    s0 = None
    for _ in range(10):
        if not proc_exists(pid):
            break
        try:
            if use_cg:
                s0 = sample_cgroup(cg)  # type: ignore[arg-type]
            else:
                s0 = sample_proc(pid)
            break
        except FileNotFoundError:
            time.sleep(0.05)

    if s0 is None:
        # Could not sample at all; record minimal info
        exit_code = get_exit_code(name)
        t1 = time.monotonic_ns()
        subprocess.run(["docker", "rm", "-f", name], check=False, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return {
            "run_id": run_id,
            "workload": workload,
            "intensity": intensity,
            "N": N,
            "rep": rep,
            "runtime_ms": (t1 - t0) / 1e6,
            "avg_cpu_percent": 0.0,
            "max_mem_mib": 0.0,
            "blk_read_mib": 0.0,
            "blk_write_mib": 0.0,
            "exit_code": exit_code,
        }

    cpu0 = s0.cpu_seconds
    r0, w0 = s0.read_bytes, s0.write_bytes
    mem_peak = s0.rss_bytes

    # Poll while container runs
    while True:
        if not proc_exists(pid):
            break
        try:
            s = sample_cgroup(cg) if use_cg else sample_proc(pid)  # type: ignore[arg-type]
            mem_peak = max(mem_peak, s.rss_bytes)
        except FileNotFoundError:
            # Container/cgroup may have disappeared; stop sampling
            break

        if not is_running(name):
            break

        time.sleep(poll_interval_s)

    t1 = time.monotonic_ns()
    runtime_s = (t1 - t0) / 1e9
    runtime_ms = runtime_s * 1000.0

    # Final sample best-effort
    cpu1 = cpu0
    r1, w1 = r0, w0
    if proc_exists(pid):
        try:
            sf = sample_cgroup(cg) if use_cg else sample_proc(pid)  # type: ignore[arg-type]
            cpu1 = sf.cpu_seconds
            r1, w1 = sf.read_bytes, sf.write_bytes
            mem_peak = max(mem_peak, sf.rss_bytes)
        except FileNotFoundError:
            pass

    cpu_delta_s = max(0.0, cpu1 - cpu0)
    avg_cpu_percent = (cpu_delta_s / runtime_s * 100.0) if runtime_s > 0 else 0.0

    blk_read_mib = max(0, r1 - r0) / (1024**2)
    blk_write_mib = max(0, w1 - w0) / (1024**2)
    max_mem_mib = mem_peak / (1024**2)

    exit_code = get_exit_code(name)

    subprocess.run(["docker", "rm", "-f", name], check=False, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    return {
        "run_id": run_id,
        "workload": workload,
        "intensity": intensity,
        "N": N,
        "rep": rep,
        "runtime_ms": runtime_ms,
        "avg_cpu_percent": avg_cpu_percent,
        "max_mem_mib": max_mem_mib,
        "blk_read_mib": blk_read_mib,
        "blk_write_mib": blk_write_mib,
        "exit_code": exit_code,
    }

def main():
    os.makedirs("data", exist_ok=True)

    levels = {
        "low":  {"cpu": 2_000_000,  "mem": 64,  "disk": 64,  "mix": 64},
        "med":  {"cpu": 6_000_000,  "mem": 192, "disk": 192, "mix": 192},
        "high": {"cpu": 12_000_000, "mem": 320, "disk": 320, "mix": 320},
    }

    workloads = ["cpu", "mem", "disk", "mix"]
    reps = 30

    schedule = []
    for w in workloads:
        for intensity in ["low", "med", "high"]:
            for rep in range(reps):
                schedule.append((w, intensity, rep))

    random.seed(1337)
    random.shuffle(schedule)

    for (w, intensity, rep) in schedule:
        N = levels[intensity][w]
        row = run_one(w, N, intensity, rep)

        print(
            f"{w:4s} {intensity:4s} rep={rep:02d} "
            f"rt_ms={row['runtime_ms']:.1f} cpu%={row['avg_cpu_percent']:.1f} "
            f"mem={row['max_mem_mib']:.1f} rMiB={row['blk_read_mib']:.1f} wMiB={row['blk_write_mib']:.1f} "
            f"exit={row['exit_code']}"
        )

        write_header = not os.path.exists(OUT_CSV)
        with open(OUT_CSV, "a", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=list(row.keys()))
            if write_header:
                writer.writeheader()
            writer.writerow(row)

if __name__ == "__main__":
    main()

