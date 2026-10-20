"""Build a generic lightning icon from geometry, without input images/metadata."""
from pathlib import Path
import struct
import zlib

ROOT = Path(__file__).resolve().parents[1]


def icon() -> bytes:
    size = 256
    bolt = ((145, 28), (64, 145), (117, 145), (102, 228), (195, 105), (142, 105))

    def inside(x, y):
        result = False
        previous = bolt[-1]
        for point in bolt:
            a, b = previous, point
            if (a[1] > y) != (b[1] > y) and x < (b[0] - a[0]) * (y - a[1]) / (b[1] - a[1]) + a[0]:
                result = not result
            previous = point
        return result

    rows = bytearray()
    for y in range(size):
        rows.append(0)
        for x in range(size):
            rows.extend((255, 213, 79, 255) if inside(x + .5, y + .5) else (0, 96, 100, 255))

    def chunk(kind, data):
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data))

    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", size, size, 8, 6, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(bytes(rows), 9)) + chunk(b"IEND", b""))


def build():
    target = ROOT / "custom_components/nrg/brand/icon.png"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(icon())


if __name__ == "__main__":
    build()
