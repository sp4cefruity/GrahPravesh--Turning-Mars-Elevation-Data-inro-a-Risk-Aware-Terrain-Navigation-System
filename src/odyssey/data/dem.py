"""Real DEM tile loader (spec 05). Reads a window of a HiRISE PDS3 DTM over HTTP.

No GDAL needed: the DTM is a plain float32 raster, so a window is a set of row slices
fetched with HTTP range requests (about 1 MB per 512 x 512 tile, not the 700 MB file).
Missing cells become NaN in `dem` and False in `valid_mask`. Nothing is filled.
"""
import re
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import requests
import yaml

TILES_YAML = Path(__file__).with_name("tiles.yaml")
CACHE_DIR = Path(__file__).parents[3] / "data" / "tiles"
SIZE = 512
BATCH = 64  # row slices per request; the server accepted 8, Apache-style limits are usually 200


@dataclass(frozen=True)
class DemTile:
    tile_id: str
    dem: np.ndarray        # float32 (SIZE, SIZE), NaN where missing
    valid_mask: np.ndarray  # bool, False where missing
    cell_size_m: float
    sigma_z_m: float       # per-product vertical error, base value for the uncertainty step
    data_source: str       # "cache" or "hirise_window"
    product_id: str
    window: tuple          # (row, col) of the top left pixel in the source DTM


def _config():
    return yaml.safe_load(TILES_YAML.read_text())


def _parts(resp):
    """Return [(start_byte, bytes)] from a 206 reply, single or multipart."""
    ctype = resp.headers.get("Content-Type", "")
    if "multipart/byteranges" not in ctype:
        start = int(re.search(r"bytes (\d+)-", resp.headers["Content-Range"]).group(1))
        return [(start, resp.content)]
    sep = b"--" + ctype.split("boundary=")[1].strip('"').encode()
    out = []
    for chunk in resp.content.split(sep)[1:-1]:
        head, _, body = chunk.partition(b"\r\n\r\n")
        start = int(re.search(rb"bytes (\d+)-", head).group(1))
        out.append((start, body[:-2]))  # drop the CRLF before the next boundary
    return out


def read_window(product, row0, col0, rows=SIZE, cols=SIZE):
    """Fetch a (rows, cols) float32 window. Raises if the server refuses ranges."""
    rb, off, nbytes = product["record_bytes"], product["data_offset"], cols * 4
    if not (0 <= row0 and row0 + rows <= product["lines"] and 0 <= col0 and col0 + cols <= product["samples"]):
        raise ValueError(f"window {row0},{col0} size {rows}x{cols} falls outside the DTM")
    out = np.empty((rows, cols), dtype="<f4")
    got = np.zeros(rows, dtype=bool)
    with requests.Session() as s:
        for i in range(0, rows, BATCH):
            starts = [off + (row0 + r) * rb + col0 * 4 for r in range(i, min(i + BATCH, rows))]
            rng = ",".join(f"{a}-{a + nbytes - 1}" for a in starts)
            resp = s.get(product["url"], headers={"Range": f"bytes={rng}"}, timeout=90)
            if resp.status_code != 206:
                raise RuntimeError(f"server ignored the range request (HTTP {resp.status_code})")
            for start, body in _parts(resp):
                r = (start - off - col0 * 4) // rb - row0
                if len(body) != nbytes:
                    raise RuntimeError(f"short slice for row {r}: {len(body)} of {nbytes} bytes")
                out[r] = np.frombuffer(body, dtype="<f4")
                got[r] = True
    if not got.all():
        raise RuntimeError(f"{(~got).sum()} rows were not returned")
    return out


def load_tile(tile_id, refresh=False):
    """Load one tile from the cache, else fetch its window and cache it."""
    cfg = _config()
    tile = cfg["tiles"][tile_id]
    product = cfg["products"].get(tile["product"])
    if product is None:
        raise KeyError(f"{tile_id}: product {tile['product']} is not defined in tiles.yaml yet")
    if tile["window"] is None:
        raise ValueError(f"{tile_id} has no window in tiles.yaml yet (run the scout, then fill it in)")
    row0, col0 = tile["window"]
    path = CACHE_DIR / f"{tile_id}.npz"

    if path.exists() and not refresh:
        raw, source = np.load(path)["raw"], "cache"
    else:
        raw, source = read_window(product, row0, col0), "hirise_window"
        CACHE_DIR.mkdir(parents=True, exist_ok=True)
        np.savez_compressed(path, raw=raw)

    # Compare bit patterns, not floats: the no-data value is a specific float32 pattern.
    valid = raw.view("<u4") != product["missing_bits"]
    dem = np.where(valid, raw, np.nan).astype(np.float32)
    return DemTile(tile_id, dem, valid, float(product["cell_size_m"]), float(product["sigma_z_m"]),
                   source, product["id"], (row0, col0))
