import csv
import os
import random
import subprocess
import time
import uuid
from dataclasses import dataclass

from parse_units import parse_block_io, parse_mem_usage

IMAGE = "twc:mvp"
OUT_CSV = "data/dataset.csv"

@dataclass
class StatSample:
    t_s: float
    cpu_percent: float
    mem_bytes: float
    blk_read_bytes: float
    blk_write_bytes: float

def sh(cmd: list[str], check=True, capture=True) -> str:
    r = subprocess.run(
        cmd,
        check=check,
        text=True,
        stdout=subprocess.PIPE if capture else None,
        stderr=subprocess.PIPE if capture else None,
    )
    return (r.stdout or "").strip()

def docker_stats_once(name: str) -> StatSample | None:
    # If container already exited, docker stats may fail; return None.
    fmt = "{{.CPUPerc}},{{.MemUsage}},{{.BlockIO}}"
    try:
        out = sh(["docker", "stats", "--no-stream", "--format", fmt, name])
        if not out:
            return None
        cpu_s, mem_s, blk_s = out.split(",", 2)
        cpu_percent = float(cpu_s.strip().replace("%", "") or 0.0)
        mem_b = parse_mem_usage(mem_s)
        r_b, w_b = parse_block_io(blk_s)
        return StatSample(time.time(), cpu_percent, mem_b, r_b, w_b)
    except subprocess.CalledProcessError:
        return None

def run_one(workload: str, N: int, intensity: str, rep: int, poll_interval_s: float = 0.2) -> dict:
    run_id = str(uuid.uuid4())
    name = f"twc_{workload}_{intensity}_{rep}_{run_id[:8]}"

    # Start container detached so we can poll stats while it runs.
    # --rm cleans up container after exit; but we need it present for stats until exit.
    # We'll remove explicitly at end to be safe.
    cmd = [
        "docker", "run", "-d",
        "--name", name,
        "--cpus=1",
        "--memory=512m",
        "--network", "none",
        IMAGE,
        "--workload", workload,
        "--N", str(N),
    ]

    t0 = time.monotonic_ns()
    cid = sh(cmd)
    samples: list[StatSample] = []

    # Poll stats until container exits
    while True:
        s = docker_stats_once(name)
        if s is not None:
            samples.append(s)

        # Check if container is still running
        try:
            state = sh(["docker", "inspect", "-f", "{{.State.Running}}", name])
        except subprocess.CalledProcessError:
            state = "false"
        if state.strip().lower() != "true":
            break

        time.sleep(poll_interval_s)

    # Wait to ensure it’s fully done, collect exit code
    exit_code = int(sh(["docker", "inspect", "-f", "{{.State.ExitCode}}", name]) or "0")
    t1 = time.monotonic_ns()
    runtime_ms = (t1 - t0) / 1e6

    # Final stats snapshot (sometimes last poll misses final block I/O)
    s_final = docker_stats_once(name)
    if s_final is not None:
        samples.append(s_final)

    # Cleanup
    try:
        subprocess.run(["docker", "rm", "-f", name], check=False, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except Exception:
        pass

    # Aggregate features
    if samples:
        avg_cpu = sum(s.cpu_percent for s in samples) / len(samples)
        max_mem_mib = max(s.mem_bytes for s in samples) / (1024**2)
        # Use last sample’s block I/O as cumulative
        last = samples[-1]
        blk_r_mib = last.blk_read_bytes / (1024**2)
        blk_w_mib = last.blk_write_bytes / (1024**2)
    else:
        avg_cpu = 0.0
        max_mem_mib = 0.0
        blk_r_mib = 0.0
        blk_w_mib = 0.0

    return {
        "run_id": run_id,
        "workload": workload,
        "intensity": intensity,
        "N": N,
        "rep": rep,
        "runtime_ms": runtime_ms,
        "avg_cpu_percent": avg_cpu,
        "max_mem_mib": max_mem_mib,
        "blk_read_mib": blk_r_mib,
        "blk_write_mib": blk_w_mib,
        "exit_code": exit_code,
    }

def main():
    os.makedirs("data", exist_ok=True)

    # Intensity levels: pick a single consistent mapping
    levels = {
        "low":   {"cpu": 2_000_000,  "mem": 64,  "disk": 64,  "mix": 64},
        "med":   {"cpu": 6_000_000,  "mem": 192, "disk": 192, "mix": 192},
        "high":  {"cpu": 12_000_000, "mem": 320, "disk": 320, "mix": 320},
    }

    workloads = ["cpu", "mem", "disk", "mix"]
    reps = 30

    rows = []
    schedule = []
    for w in workloads:
        for intensity in ["low", "med", "high"]:
            for rep in range(reps):
                schedule.append((w, intensity, rep))

    # Shuffle to reduce drift effects (still “no co-tenant interference”)
    random.seed(1337)
    random.shuffle(schedule)

    for (w, intensity, rep) in schedule:
        N = levels[intensity][w]
        row = run_one(w, N, intensity, rep)
        rows.append(row)
        print(f"{w:4s} {intensity:4s} rep={rep:02d} runtime_ms={row['runtime_ms']:.1f} mem_peak={row['max_mem_mib']:.1f}")

        # Append incrementally to avoid losing progress if something fails
        write_header = not os.path.exists(OUT_CSV)
        with open(OUT_CSV, "a", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=list(row.keys()))
            if write_header:
                writer.writeheader()
            writer.writerow(row)

if __name__ == "__main__":
    main()

