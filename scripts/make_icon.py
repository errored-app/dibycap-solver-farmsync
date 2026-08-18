r"""Draw `assets/FarmsyncSolver.ico`, the icon the build stamps on the exe.

    uv run python -m scripts.make_icon

The icon is committed, so this only runs when the mark changes. It is written by
hand rather than with an image library, because the build must not gain a
dependency just to own a 20 KB file.
"""
from __future__ import annotations

import struct
import zlib
from pathlib import Path

OUTPUT = Path(__file__).resolve().parent.parent / "assets" / "FarmsyncSolver.ico"
SIZES = (256, 64, 48, 32, 16)
LARGEST = max(SIZES)

BACKGROUND = (24, 30, 38, 255)  # near-black, so the mark reads on any taskbar
MARK = (61, 214, 140, 255)  # the green of a run that is working
Pixel = tuple[int, int, int, int]


def _rounded_square(size: int) -> list[list[Pixel]]:
    """The tile the mark sits on. Corners are cut to a radius of size/5."""
    radius = size / 5
    rows: list[list[Pixel]] = []
    for y in range(size):
        row: list[Pixel] = []
        for x in range(size):
            near_x = min(x + 0.5, size - x - 0.5)
            near_y = min(y + 0.5, size - y - 0.5)
            inside = True
            if near_x < radius and near_y < radius:
                gap_x, gap_y = radius - near_x, radius - near_y
                inside = gap_x * gap_x + gap_y * gap_y <= radius * radius
            row.append(BACKGROUND if inside else (0, 0, 0, 0))
        rows.append(row)
    return rows


def _draw_f(rows: list[list[Pixel]], size: int) -> None:
    """A block `F`: one upright, a full top bar, a shorter middle bar."""
    unit = size / 16
    stroke = max(1, round(unit * 2))
    left, top = round(unit * 4), round(unit * 3)
    bottom, right = round(unit * 13), round(unit * 12)
    middle = round(unit * 7)

    def fill(x0: int, y0: int, x1: int, y1: int) -> None:
        for y in range(max(0, y0), min(size, y1)):
            for x in range(max(0, x0), min(size, x1)):
                rows[y][x] = MARK

    fill(left, top, left + stroke, bottom)  # upright
    fill(left, top, right, top + stroke)  # top bar
    fill(left, middle, right - round(unit * 2), middle + stroke)  # middle bar


def _png(rows: list[list[Pixel]]) -> bytes:
    size = len(rows)
    raw = b"".join(b"\x00" + bytes(channel for pixel in row for channel in pixel) for row in rows)

    def chunk(kind: bytes, payload: bytes) -> bytes:
        body = kind + payload
        return struct.pack(">I", len(payload)) + body + struct.pack(">I", zlib.crc32(body))

    header = struct.pack(">IIBBBBB", size, size, 8, 6, 0, 0, 0)
    return (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", header)
        + chunk(b"IDAT", zlib.compress(raw, 9))
        + chunk(b"IEND", b"")
    )


def _scaled(rows: list[list[Pixel]], size: int) -> list[list[Pixel]]:
    source = len(rows)
    return [[rows[y * source // size][x * source // size] for x in range(size)] for y in range(size)]


def icon_bytes() -> bytes:
    """A PNG-in-ICO file holding every size in `SIZES`."""
    largest = _rounded_square(LARGEST)
    _draw_f(largest, LARGEST)

    images = [_png(largest if size == LARGEST else _scaled(largest, size)) for size in SIZES]

    offset = 6 + 16 * len(images)
    directory = b""
    for size, image in zip(SIZES, images):
        # 0 in the width/height byte means 256, which is why it is masked.
        directory += struct.pack(
            "<BBBBHHII", size & 0xFF, size & 0xFF, 0, 0, 1, 32, len(image), offset
        )
        offset += len(image)

    return struct.pack("<HHH", 0, 1, len(images)) + directory + b"".join(images)


def main() -> int:
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_bytes(icon_bytes())
    print(f"wrote {OUTPUT} ({OUTPUT.stat().st_size} bytes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
