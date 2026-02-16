import argparse
import hashlib
import os
import time

PAGE = 4096

def cpu_work(N: int) -> None:
    # CPU-bound: repeated hashing on small buffer
    buf = b"x" * 64
    h = b""
    for _ in range(N):
        h = hashlib.sha256(buf + h).digest()

def mem_work(N_mib: int) -> None:
    # Memory-bound: allocate and touch N MiB to force RSS growth
    size = N_mib * 1024 * 1024
    b = bytearray(size)

    # Touch one byte per page to ensure physical backing.
    for i in range(0, size, PAGE):
        b[i] = (i // PAGE) & 0xFF

    # A few passes to keep memory active.
    step = 97
    for _ in range(3):
        s = 0
        for i in range(0, size, step * 1024):
            s ^= b[i]
            b[i] = (b[i] + 1) & 0xFF
        if s == 257:
            print("wow")

def disk_work(N_mib: int) -> None:
    # Disk I/O-bound: write + fsync + read + hash a file of N MiB
    path = "/tmp/io.bin"
    total = N_mib * 1024 * 1024
    chunk = 1024 * 1024  # 1 MiB

    with open(path, "wb") as f:
        remaining = total
        block = os.urandom(min(chunk, total))
        while remaining > 0:
            to_write = min(chunk, remaining)
            f.write(block[:to_write])
            remaining -= to_write
        f.flush()
        os.fsync(f.fileno())

    h = hashlib.sha256()
    with open(path, "rb") as f:
        while True:
            data = f.read(chunk)
            if not data:
                break
            h.update(data)
    _ = h.digest()

    try:
        os.remove(path)
    except FileNotFoundError:
        pass

def mix_work(N: int) -> None:
    # Mixed: half memory + CPU proportional + half disk
    mem_mib = max(16, N // 2)
    disk_mib = max(16, N // 2)
    cpu_iters = N * 50_000

    mem_work(mem_mib)
    cpu_work(cpu_iters)
    disk_work(disk_mib)

def main():
    p = argparse.ArgumentParser()
    p.add_argument("--workload", choices=["cpu", "mem", "disk", "mix"], required=True)
    p.add_argument("--N", type=int, required=True)
    # Hold after completion so host telemetry sampling is reliable
    p.add_argument("--hold_ms", type=int, default=750)
    args = p.parse_args()

    if args.workload == "cpu":
        cpu_work(args.N)
    elif args.workload == "mem":
        mem_work(args.N)
    elif args.workload == "disk":
        disk_work(args.N)
    elif args.workload == "mix":
        mix_work(args.N)

    time.sleep(args.hold_ms / 1000.0)

if __name__ == "__main__":
    main()

