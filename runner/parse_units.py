import re

UNIT_MULT = {
    "B": 1,
    "KB": 1000,
    "MB": 1000**2,
    "GB": 1000**3,
    "TB": 1000**4,
    "KiB": 1024,
    "MiB": 1024**2,
    "GiB": 1024**3,
    "TiB": 1024**4,
}

def parse_size_to_bytes(s: str) -> float:
    s = s.strip()
    if s == "0" or s == "0B":
        return 0.0
    m = re.match(r"^([0-9]*\.?[0-9]+)\s*([A-Za-z]+)$", s)
    if not m:
        raise ValueError(f"Cannot parse size: {s}")
    val = float(m.group(1))
    unit = m.group(2)
    if unit not in UNIT_MULT:
        raise ValueError(f"Unknown unit {unit} in {s}")
    return val * UNIT_MULT[unit]

def parse_mem_usage(mem_usage_field: str) -> float:
    # "123.4MiB / 512MiB" -> bytes used
    used = mem_usage_field.split("/")[0].strip()
    return parse_size_to_bytes(used)

def parse_block_io(block_io_field: str) -> tuple[float, float]:
    # "1.2MB / 3.4MB" -> (read_bytes, write_bytes)
    parts = block_io_field.split("/")
    read_s = parts[0].strip()
    write_s = parts[1].strip()
    return parse_size_to_bytes(read_s), parse_size_to_bytes(write_s)

