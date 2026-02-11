import argparse
import hashlib
import os
import time

PAGE = 4096

def cpu_work(N: int) -> None:
    buf = b"x" * 64
    h = b""
    for _ in range(N):
        h = hashlib.sha256(buf + h).digest()

def mem_work(N_mib: int) -> None:
    size = N_mib * 1024 * 1024
    b = bytearray(size)

    # Touch one byte per page to ensure physical backing (RSS growth).
    for i in range(0, size, PAGE):
        b[i] = (i // PAGE) & 0xFF

    # A couple simple passes to keep memory “active”.
    step = 97  # co-prime-ish stride for simple access pattern
    for _ in range(3):
        s = 0
        for i in range(0, size, step * 1024):
            s ^= b[i]
            b[i] = (b[i] + 1) & 0xFF
        if s == 257:  # unreachable, just prevents overly-smart elimination
            print("wow")

def disk_work(N_mib: int) -> None:
    path = "/tmp/io.bin"
    total = N_mib * 1024 * 1024
    chunk = 1024 * 1024  # 1 MiB

    # Write
    with open(path, "wb") as f:
        remaining = total
        block = os.urandom(min(chunk, total))
        while remaining > 0:
            to_write = min(chunk, remaining)
            f.write(block[:to_write])
            remaining -= to_write
        f.flush()
        os.fsync(f.fileno())

    # Read + hash (forces read I/O)
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
    # Mixed: half memory, CPU proportional, half disk
    mem_mib = max(16, N // 2)
    disk_mib = max(16, N // 2)
    cpu_iters = N * 50_000  # scale CPU with N while staying within reasonable time

    mem_work(mem_mib)
    cpu_work(cpu_iters)
    disk_work(disk_mib)

def main():
    p = argparse.ArgumentParser()
    p.add_argument("--workload", choices=["cpu", "mem", "disk", "mix"], required=True)
    p.add_argument("--N", type=int, required=True)
    args = p.parse_args()

    # Small start marker (doesn't leak contents; runner doesn't read logs anyway)
    # print(f"start {args.workload} N={args.N}", flush=True)

    if args.workload == "cpu":
        cpu_work(args.N)
    elif args.workload == "mem":
        mem_work(args.N)
    elif args.workload == "disk":
        disk_work(args.N)
    elif args.workload == "mix":
        mix_work(args.N)

if __name__ == "__main__":
    main()

