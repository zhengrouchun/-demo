"""Inspect transparent PNGs with Python's standard library; never edits an image."""
import json
from pathlib import Path
import struct
import zlib

ROOT = Path(__file__).resolve().parents[1]


def inspect(path):
    data = path.read_bytes()
    assert data[:8] == b"\x89PNG\r\n\x1a\n", path
    width, height, depth, color, compression, filtering, interlace = struct.unpack(">IIBBBBB", data[16:29])
    assert depth == 8 and color in (4, 6) and interlace == 0, (path, depth, color, interlace)
    channels = 4 if color == 6 else 2
    compressed = bytearray()
    offset = 8
    while offset < len(data):
        length = struct.unpack(">I", data[offset:offset + 4])[0]
        if data[offset + 4:offset + 8] == b"IDAT": compressed.extend(data[offset + 8:offset + 8 + length])
        offset += length + 12
    raw = zlib.decompress(compressed)
    stride = width * channels + 1
    assert len(raw) == height * stride
    previous = bytearray(width)
    low, high, transparent = 255, 0, 0
    for y in range(height):
        base = y * stride
        method = raw[base]
        alpha = bytearray(raw[base + channels:base + stride:channels])
        assert method <= 4
        if method:
            left = upper_left = 0
            for x, encoded in enumerate(alpha):
                upper = previous[x]
                if method == 1: predictor = left
                elif method == 2: predictor = upper
                elif method == 3: predictor = (left + upper) // 2
                else:
                    p = left + upper - upper_left
                    a, b, c = abs(p - left), abs(p - upper), abs(p - upper_left)
                    predictor = left if a <= b and a <= c else upper if b <= c else upper_left
                alpha[x] = left = (encoded + predictor) & 255
                upper_left = upper
        previous = alpha
        low, high = min(low, min(alpha)), max(high, max(alpha))
        transparent += alpha.count(0)
    assert low == 0 and high == 255 and transparent > width * height * .1, (path, low, high, transparent)
    return {"name": path.name, "size": [width, height], "alpha_range": [low, high], "transparent_pixels": transparent, "bytes": len(data)}


if __name__ == "__main__":
    directory = ROOT / "app/frontend/public/pet/gushiye"
    result = [inspect(directory / (name + ".png")) for name in ["idle", "blink", "touch", "wave", "surprise", "drag", "sleep"]]
    assert all(row["size"] == result[0]["size"] for row in result)
    print(json.dumps({"ok": True, "assets": result}, ensure_ascii=False))
