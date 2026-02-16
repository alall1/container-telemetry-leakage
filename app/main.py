import argparse
import hashlib
import os
import time
import gzip
from io import BytesIO

PAGE = 4096

def cpu_work(N: int) -> None:
    buf = b"x" * 64
    h = b""
    for _ in range(N):
        h = hashlib.sha256(buf + h).digest()

def mem_work(N_mib: int) -> None:
    size = N_mib * 1024 * 1024
    b = bytearray(size)

    for i in range(0, size, PAGE):
        b[i] = 1

    # Stream through the whole buffer a couple times (strong, stable RSS signal)
    for _ in range(2):
        for i in range(0, size, 64):
            b[i] = (b[i] + 1) & 0xFF

def disk_work(N_mib: int) -> None:
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
    mem_mib = max(16, N // 2)
    disk_mib = max(16, N // 2)
    cpu_iters = N * 50_000

    mem_work(mem_mib)
    cpu_work(cpu_iters)
    disk_work(disk_mib)

def make_entropy_buffer(secret_N: int, size_mib: int) -> bytes:
    size = size_mib * 1024 * 1024

    if secret_N == 0:
        return b"\x00" * size

    if secret_N == 1:
        pat = b"ABCD"
        return (pat * (size // len(pat) + 1))[:size]

    if secret_N == 2:
        # Medium entropy: pseudo-random from small alphabet
        alphabet = b"abcdefghijklmnop"  # 16 bytes
        out = bytearray(size)
        x = 0x12345678
        for i in range(size):
            # tiny LCG for determinism, no external deps
            x = (1103515245 * x + 12345) & 0x7fffffff
            out[i] = alphabet[x & 0x0F]
        return bytes(out)

    # secret_N == 3 (high entropy)
    return os.urandom(size)

def secret_work(secret_N: int, size_mib: int) -> None:
    """
    Secret leakage workload:
    - Generate fixed-size data whose compressibility depends on secret_N
    - gzip-compress it
    - Write compressed output to disk + fsync
    """
    raw = make_entropy_buffer(secret_N, size_mib)

    # gzip compress in-memory
    bio = BytesIO()
    with gzip.GzipFile(fileobj=bio, mode="wb", compresslevel=6) as gz:
        gz.write(raw)
    comp = bio.getvalue()

    # Write compressed output
    out_path = "/tmp/secret.gz"
    with open(out_path, "wb") as f:
        f.write(comp)
        f.flush()
        os.fsync(f.fileno())

    try:
        os.remove(out_path)
    except FileNotFoundError:
        pass

def main():
    p = argparse.ArgumentParser()
    p.add_argument("--workload", choices=["cpu", "mem", "disk", "mix", "secret"], required=True)
    p.add_argument("--N", type=int, required=True)
    p.add_argument("--size_mib", type=int, default=128)  # used by secret workload only
    p.add_argument("--hold_ms", type=int, default=2000)
    args = p.parse_args()

    if args.workload == "cpu":
        cpu_work(args.N)
    elif args.workload == "mem":
        mem_work(args.N)
    elif args.workload == "disk":
        disk_work(args.N)
    elif args.workload == "mix":
        mix_work(args.N)
    elif args.workload == "secret":
        if args.N not in (0, 1, 2, 3):
            raise SystemExit("secret workload requires --N in {0,1,2,3}")
        secret_work(args.N, args.size_mib)

    time.sleep(args.hold_ms / 1000.0)

if __name__ == "__main__":
    main()

