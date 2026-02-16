import csv
import os
import random
import subprocess
import time
import uuid
from dataclasses import dataclass
from pathlib import Path

IMAGE = "twc:mvp"
OUT_CSV = "data/dataset.csv"

@dataclass
class CgroupSample:
    mem_current_bytes: int
    mem_peak_bytes: int | None
    cpu_usage_usec: int
    io_rbytes: int
    io_wbytes: int

def sh(cmd: list[str], check=True) -> str:
    r = subprocess.run(
        cmd,
        check=check,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    return (r.stdout or "").strip()

def get_container_pid(name: str) -> int:
    # 0 if not running; for our sampling we call this right after start
    return int(sh(["docker", "inspect", "-f", "{{.State.Pid}}", name]))

def get_cgroup_dir_from_pid(pid: int) -> Path:
    # cgroup v2: /proc/<pid>/cgroup contains "0::/system.slice/docker-<id>.scope"
    with open(f"/proc/{pid}/cgroup", "r") as f:
        for line in f:
            parts = line.strip().split(":")
            if len(parts) == 3 and parts[0] == "0":
                rel = parts[2]
                return Path("/sys/fs/cgroup") / rel.lstrip("/")
    raise RuntimeError("Could not find cgroup v2 path for pid")

def read_kv_file(path: Path) -> dict[str, int]:
    d: dict[str, int] = {}
    txt = path.read_text().strip().splitlines()
    for ln in txt:
        if not ln.strip():
            continue
        k, v = ln.split()
        d[k] = int(v)
    return d

def read_memory_current(cg: Path) -> int:
    return int((cg / "memory.current").read_text().strip())

def read_memory_peak_if_available(cg: Path) -> int | None:
    p = cg / "memory.peak"
    if p.exists():
        return int(p.read_text().strip())
    return None

def read_cpu_usage_usec(cg: Path) -> int:
    cpu = read_kv_file(cg / "cpu.stat")
    return cpu.get("usage_usec", 0)

def read_io_bytes(cg: Path) -> tuple[int, int]:
    # Sum rbytes/wbytes across devices
    rbytes = 0
    wbytes = 0
    txt = (cg / "io.stat").read_text().strip().splitlines()
    for ln in txt:
        toks = ln.split()
        for t in toks[1:]:
            if t.startswith("rbytes="):
                rbytes += int(t.split("=", 1)[1])
            elif t.startswith("wbytes="):
                wbytes += int(t.split("=", 1)[1])
    return rbytes, wbytes

def sample_cgroup(cg: Path) -> CgroupSample:
    mem_cur = read_memory_current(cg)
    mem_peak = read_memory_peak_if_available(cg)
    cpu_usec = read_cpu_usage_usec(cg)
    rbytes, wbytes = read_io_bytes(cg)
    return CgroupSample(mem_cur, mem_peak, cpu_usec, rbytes, wbytes)

def is_running(name: str) -> bool:
    state = subprocess.run(
        ["docker", "inspect", "-f", "{{.State.Running}}", name],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
    ).stdout.strip().lower()
    return state == "true"

def run_one(workload: str, N: int, intensity: str, rep: int, hold_ms: int = 750, poll_interval_s: float = 0.2) -> dict:
    run_id = str(uuid.uuid4())
    name = f"twc_{workload}_{intensity}_{rep}_{run_id[:8]}"

    # Start detached so we can sample host telemetry while it runs
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
    cid = sh(cmd)

    # Find cgroup path for the container process
    pid = get_container_pid(name)
    if pid <= 0:
        # Container exited extremely quickly or failed to start
        exit_code = int(sh(["docker", "inspect", "-f", "{{.State.ExitCode}}", name], check=False) or "1")
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

    # Baselines
    s0 = sample_cgroup(cg)
    cpu0 = s0.cpu_usage_usec
    r0, w0 = s0.io_rbytes, s0.io_wbytes

    mem_peak_sampled = s0.mem_current_bytes
    mem_peak_file = s0.mem_peak_bytes or 0

    # Poll until exit
    while True:
        s = sample_cgroup(cg)
        mem_peak_sampled = max(mem_peak_sampled, s.mem_current_bytes)
        if s.mem_peak_bytes is not None:
            mem_peak_file = max(mem_peak_file, s.mem_peak_bytes)

        if not is_running(name):
            break
        time.sleep(poll_interval_s)

    t1 = time.monotonic_ns()
    runtime_s = (t1 - t0) / 1e9
    runtime_ms = runtime_s * 1000.0

    # Final sample
    s1 = sample_cgroup(cg)
    cpu1 = s1.cpu_usage_usec
    r1, w1 = s1.io_rbytes, s1.io_wbytes

    cpu_delta_usec = max(0, cpu1 - cpu0)
    # With --cpus=1, avg CPU% ≈ (cpu_time / wall_time) * 100
    avg_cpu_percent = ((cpu_delta_usec / 1e6) / runtime_s * 100.0) if runtime_s > 0 else 0.0

    blk_read_mib = max(0, r1 - r0) / (1024**2)
    blk_write_mib = max(0, w1 - w0) / (1024**2)

    mem_peak_bytes = mem_peak_file if mem_peak_file > 0 else mem_peak_sampled
    max_mem_mib = mem_peak_bytes / (1024**2)

    exit_code = int(sh(["docker", "inspect", "-f", "{{.State.ExitCode}}", name], check=False) or "0")

    # Cleanup
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

    # Keep intensity mapping explicit and simple
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

    # Shuffle to reduce drift effects
    random.seed(1337)
    random.shuffle(schedule)

    for (w, intensity, rep) in schedule:
        N = levels[intensity][w]
        row = run_one(w, N, intensity, rep)

        print(
            f"{w:4s} {intensity:4s} rep={rep:02d} "
            f"rt_ms={row['runtime_ms']:.1f} cpu%={row['avg_cpu_percent']:.1f} "
            f"mem_peak={row['max_mem_mib']:.1f} rMiB={row['blk_read_mib']:.1f} wMiB={row['blk_write_mib']:.1f} "
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

