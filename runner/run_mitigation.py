import csv
import os
import random
import subprocess
import time
import uuid
from pathlib import Path
from dataclasses import dataclass
from typing import Optional

IMAGE = "twc:mvp"
OUT_CSV = "data/mitigation_dataset.csv"

@dataclass
class CgSample:
    usage_usec: int
    mem_current: int
    rbytes: int
    wbytes: int

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

def get_cgroup_dir_from_pid(pid: int) -> Optional[Path]:
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
    try:
        text = path.read_text()
    except (FileNotFoundError, OSError) as e:
        raise FileNotFoundError(str(path)) from e

    d: dict[str, int] = {}
    for ln in text.strip().splitlines():
        if not ln.strip():
            continue
        k, v = ln.split()
        d[k] = int(v)
    return d

def read_io_bytes(cg: Path) -> tuple[int, int]:
    rbytes = 0
    wbytes = 0
    io_path = cg / "io.stat"
    if not io_path.exists():
        return 0, 0

    try:
        lines = io_path.read_text().strip().splitlines()
    except (FileNotFoundError, OSError):
        return 0, 0

    for ln in lines:
        toks = ln.split()
        for t in toks[1:]:
            if t.startswith("rbytes="):
                rbytes += int(t.split("=", 1)[1])
            elif t.startswith("wbytes="):
                wbytes += int(t.split("=", 1)[1])
    return rbytes, wbytes

def sample_cgroup(cg: Path) -> CgSample:
    cpu = read_kv_file(cg / "cpu.stat")
    usage_usec = cpu.get("usage_usec", 0)

    try:
        mem_current = int((cg / "memory.current").read_text().strip())
    except (FileNotFoundError, OSError) as e:
        raise FileNotFoundError(str(cg / "memory.current")) from e

    rbytes, wbytes = read_io_bytes(cg)
    return CgSample(usage_usec, mem_current, rbytes, wbytes)

def wait_for_cgroup(pid: int, timeout_s: float = 1.5) -> Optional[Path]:
    t_end = time.time() + timeout_s
    while time.time() < t_end:
        cg = get_cgroup_dir_from_pid(pid)
        if cg is not None:
            if (cg / "cpu.stat").exists() and (cg / "memory.current").exists():
                return cg
        time.sleep(0.05)
    return None

def run_one(secret_N: int, mitigation: str, rep: int, size_mib: int = 128, hold_ms: int = 2000, poll_interval_s: float = 0.1) -> dict:
    run_id = str(uuid.uuid4())
    name = f"twc_mitig_{mitigation}_{secret_N}_{rep}_{run_id[:8]}"

    cmd = [
        "docker", "run", "-d",
        "--name", name,
        "--cpus=1",
        "--memory=512m",
        "--network", "none",
        IMAGE,
        "--workload", "secret",
        "--N", str(secret_N),
        "--size_mib", str(size_mib),
        "--mitigation", mitigation,
        "--hold_ms", str(hold_ms),
    ]

    t0 = time.monotonic_ns()
    sh(cmd, check=True)

    pid = get_container_pid(name)
    if pid <= 0:
        exit_code = get_exit_code(name)
        subprocess.run(["docker", "rm", "-f", name], check=False, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        t1 = time.monotonic_ns()
        return {
            "run_id": run_id,
            "workload": "secret",
            "secret_N": secret_N,
            "mitigation": mitigation,
            "rep": rep,
            "runtime_ms": (t1 - t0) / 1e6,
            "avg_cpu_percent": 0.0,
            "max_mem_mib": 0.0,
            "blk_read_mib": 0.0,
            "blk_write_mib": 0.0,
            "exit_code": exit_code,
        }

    cg = wait_for_cgroup(pid)
    if cg is None:
        exit_code = get_exit_code(name)
        t1 = time.monotonic_ns()
        subprocess.run(["docker", "rm", "-f", name], check=False, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return {
            "run_id": run_id,
            "workload": "secret",
            "secret_N": secret_N,
            "mitigation": mitigation,
            "rep": rep,
            "runtime_ms": (t1 - t0) / 1e6,
            "avg_cpu_percent": 0.0,
            "max_mem_mib": 0.0,
            "blk_read_mib": 0.0,
            "blk_write_mib": 0.0,
            "exit_code": exit_code,
        }

    s0 = sample_cgroup(cg)
    last = s0
    mem_peak = s0.mem_current

    while True:
        try:
            s = sample_cgroup(cg)
            last = s
            mem_peak = max(mem_peak, s.mem_current)
        except FileNotFoundError:
            break

        if not is_running(name):
            break

        time.sleep(poll_interval_s)

    t1 = time.monotonic_ns()
    runtime_s = (t1 - t0) / 1e9
    runtime_ms = runtime_s * 1000.0

    cpu_delta_s = max(0.0, (last.usage_usec - s0.usage_usec) / 1e6)
    avg_cpu_percent = (cpu_delta_s / runtime_s * 100.0) if runtime_s > 0 else 0.0

    blk_read_mib = max(0, last.rbytes - s0.rbytes) / (1024**2)
    blk_write_mib = max(0, last.wbytes - s0.wbytes) / (1024**2)
    max_mem_mib = mem_peak / (1024**2)

    exit_code = get_exit_code(name)
    subprocess.run(["docker", "rm", "-f", name], check=False, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    return {
        "run_id": run_id,
        "workload": "secret",
        "secret_N": secret_N,
        "mitigation": mitigation,
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

    secret_levels = [0, 1, 2, 3]
    mitigations = ["none", "low", "high"]
    reps_per_cell = 30
    size_mib = 128

    schedule = []
    for m in mitigations:
        for n in secret_levels:
            for rep in range(reps_per_cell):
                schedule.append((n, m, rep))

    random.seed(303)
    random.shuffle(schedule)

    if os.path.exists(OUT_CSV):
        os.remove(OUT_CSV)

    for (n, m, rep) in schedule:
        row = run_one(n, m, rep, size_mib=size_mib)

        print(
            f"mit={m:4s} N={n} rep={rep:02d} "
            f"rt_ms={row['runtime_ms']:.1f} cpu%={row['avg_cpu_percent']:.1f} "
            f"mem={row['max_mem_mib']:.1f} wMiB={row['blk_write_mib']:.1f} exit={row['exit_code']}"
        )

        write_header = not os.path.exists(OUT_CSV)
        with open(OUT_CSV, "a", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=list(row.keys()))
            if write_header:
                writer.writeheader()
            writer.writerow(row)

if __name__ == "__main__":
    main()

