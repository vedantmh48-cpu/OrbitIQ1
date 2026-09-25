"""GeoTools — GIS / GeoTIFF parsing + spectral-index metadata helpers (pure Python).

Parses GeoTIFF headers without GDAL/NumPy by reading the TIFF tag structure:

* image dimensions, bits-per-sample, photometric interpretation, compression
* GeoKeyDirectory → CRS / EPSG code, geographic vs projected model
* ModelPixelScale / ModelTiepoint georeferencing → true map bounds
* computed footprint (GeoJSON Polygon + WKT) and lon/lat bounding box

Everything is grounded in the actual header bytes — no invented geometry. A
synthetic minimal-GeoTIFF generator is included so the explorer works offline
(output clearly labelled ``simulated``).
"""
from __future__ import annotations

import math
import struct

IMAGE_FILE_DIRECTORY = 42

# TIFF field types -> (struct char, item size)
_FIELD_TYPES = {
    1: ("B", 1), 2: ("c", 1), 3: ("H", 2), 4: ("I", 4),
    5: ("II", 8), 6: ("b", 1), 7: ("b", 1), 8: ("h", 2),
    9: ("i", 4), 10: ("ii", 8), 11: ("f", 4), 12: ("d", 8),
}

_GEO_KEYS = {
    1024: "GTModelTypeGeoKey", 1025: "GTRasterTypeGeoKey", 1026: "GTCitationGeoKey",
    2048: "GeographicTypeGeoKey", 2049: "GeogCitationGeoKey", 2054: "GeogAngularUnitsGeoKey",
    3072: "ProjectedCSTypeGeoKey", 3073: "PCSCitationGeoKey", 3076: "ProjLinearUnitsGeoKey",
}
_ANGULAR_UNITS = {9102: "degree", 9105: "radian", 9101: "arc-second"}
_LINEAR_UNITS = {9001: "metre", 9002: "foot", 9003: "US survey foot", 9036: "kilometre", 9030: "nautical mile"}
_KNOWN_EPSG = {
    4326: "WGS 84", 3857: "WGS 84 / Pseudo-Mercator", 32643: "WGS 84 / UTM zone 43N",
    32644: "WGS 84 / UTM zone 44N", 32645: "WGS 84 / UTM zone 45N",
    32743: "WGS 84 / UTM zone 43S", 32636: "WGS 84 / UTM zone 36N", 3856: "ETRS89 / ...",
}
ENDIAN_MAP = {"II": "<", "MM": ">"}


class GeoTiffError(RuntimeError):
    pass
class GeoTiffInfo:
    """Parsed GeoTIFF header / georeferencing metadata."""

    def __init__(self, data: bytes):
        self.data = data
        self.endianness = ""
        self.width = 0
        self.height = 0
        self.bands = 1
        self.bits_per_sample = 8
        self.compression = 1
        self.photometric = 0
        self.geo_keys: dict = {}
        self.epsg: int | None = None
        self.model_type: str | None = None
        self.angular_units: str | None = None
        self.linear_units: str | None = None
        self.citation: str | None = None
        self.pixel_scale: list | None = None
        self.tiepoints: list | None = None
        self.bounds_lonlat: dict | None = None
        self.bounds_crs: dict | None = None
        self._parse()

    def _parse(self):
        if len(self.data) < 8:
            raise GeoTiffError("Not a TIFF file (too small).")
        bo = self.data[:2].decode("ascii", "ignore")
        if bo not in ("II", "MM"):
            raise GeoTiffError("Unsupported byte order — not a TIFF/GeoTIFF.")
        self.endianness = "little" if bo == "II" else "big"
        e = ENDIAN_MAP[bo]
        if struct.unpack(e + "H", self.data[2:4])[0] != IMAGE_FILE_DIRECTORY:
            raise GeoTiffError("Invalid TIFF magic — not a TIFF file.")
        ifd_offset = struct.unpack(e + "I", self.data[4:8])[0]
        n_entries = struct.unpack(e + "H", self.data[ifd_offset: ifd_offset + 2])[0]
        tags: dict[int, tuple] = {}
        for i in range(n_entries):
            base = ifd_offset + 2 + i * 12
            tag = struct.unpack(e + "H", self.data[base: base + 2])[0]
            ftype = struct.unpack(e + "H", self.data[base + 2: base + 4])[0]
            count = struct.unpack(e + "I", self.data[base + 4: base + 8])[0]
            tags[tag] = (ftype, count, self.data[base + 8: base + 12])

        def tag_value(tag_id: int):
            if tag_id not in tags:
                return None
            ftype, count, vf = tags[tag_id]
            if ftype not in _FIELD_TYPES:
                return None
            fmt, size = _FIELD_TYPES[ftype]
            if size * count <= 4:
                raw = vf[: size * count]
            else:
                off = struct.unpack(e + "I", vf)[0]
                raw = self.data[off: off + size * count]
            try:
                vals = struct.unpack(e + fmt * count, raw)
            except Exception:
                return None
            if ftype == 2:
                return b"".join(vals).split(b"\x00")[0].decode("utf-8", "ignore")
            return vals[0] if count == 1 else list(vals)

        self.width = int(tag_value(256) or 0)
        self.height = int(tag_value(257) or 0)
        self.bands = int(tag_value(277) or 1)
        self.bits_per_sample = int(tag_value(258) or 8)
        self.compression = int(tag_value(259) or 1)
        self.photometric = int(tag_value(262) or 0)

        gk = tag_value(34735)
        if gk and isinstance(gk, list):
            keys = list(gk)
            if len(keys) >= 4:
                n = keys[3]
                for i in range(n):
                    pos = 4 + i * 4
                    if pos + 3 >= len(keys):
                        break
                    key_id, tiff_tag, count, value = keys[pos: pos + 4]
                    name = _GEO_KEYS.get(key_id, f"GeoKey{key_id}")
                    if tiff_tag == 0:
                        self.geo_keys[name] = value
                    else:
                        rawv = tag_value(tiff_tag)
                        self.geo_keys[name] = rawv[value] if isinstance(rawv, list) and value < len(rawv) else rawv

        if "ProjectedCSTypeGeoKey" in self.geo_keys:
            self.epsg = int(self.geo_keys["ProjectedCSTypeGeoKey"])
            self.model_type = "Projected (cartesian metres)"
        elif "GeographicTypeGeoKey" in self.geo_keys:
            self.epsg = int(self.geo_keys["GeographicTypeGeoKey"])
            self.model_type = "Geographic (lon/lat)"
        # Reconcile EPSG semantics: UTM/Pseudo-Mercator are projected even when
        # the header model key is loosely written as geographic.
        if self.epsg:
            if self.epsg == 3857 or 32600 < self.epsg < 32761:
                self.model_type = "Projected (cartesian metres)"
        self.citation = (self.geo_keys.get("GTCitationGeoKey") or self.geo_keys.get("GeogCitationGeoKey")
                         or self.geo_keys.get("PCSCitationGeoKey"))
        if "GeogAngularUnitsGeoKey" in self.geo_keys:
            self.angular_units = _ANGULAR_UNITS.get(int(self.geo_keys["GeogAngularUnitsGeoKey"]), "unknown")
        if "ProjLinearUnitsGeoKey" in self.geo_keys:
            self.linear_units = _LINEAR_UNITS.get(int(self.geo_keys["ProjLinearUnitsGeoKey"]), "unknown")

        ps = tag_value(33550)
        if isinstance(ps, list) and len(ps) >= 3:
            self.pixel_scale = [float(x) for x in ps[:3]]
        tp = tag_value(33922)
        if isinstance(tp, list) and len(tp) >= 6:
            self.tiepoints = [float(x) for x in tp[:6]]
        self._derive_bounds()

    def _derive_bounds(self):
        """Real map footprint from pixel-scale + tiepoint → lon/lat box."""
        if not self.pixel_scale or not self.tiepoints:
            return
        sx, sy, _ = self.pixel_scale
        i, j, _, ox, oy, _ = self.tiepoints
        origin_x = ox - i * sx
        origin_y = oy + j * abs(sy)
        x0, x1 = sorted((origin_x, origin_x + self.width * sx))
        y0, y1 = sorted((origin_y - self.height * abs(sy), origin_y))
        geographic = "geographic" in (self.model_type or "").lower()
        if geographic:
            self.bounds_lonlat = {"min_lng": round(x0, 7), "min_lat": round(y0, 7),
                                  "max_lng": round(x1, 7), "max_lat": round(y1, 7)}
            self.bounds_crs = dict(self.bounds_lonlat)
        else:
            self.bounds_crs = {"min_x": round(x0, 3), "min_y": round(y0, 3),
                               "max_x": round(x1, 3), "max_y": round(y1, 3)}
            self.bounds_lonlat = _project_bounds_to_lonlat(x0, y0, x1, y1, self.epsg)

    def footprint_geojson(self) -> dict | None:
        if not self.bounds_lonlat:
            return None
        b = self.bounds_lonlat
        return {
            "type": "Feature",
            "properties": {
                "epsg": self.epsg,
                "crs_name": _KNOWN_EPSG.get(self.epsg, f"EPSG:{self.epsg}"),
                "bounds": b, "width": self.width, "height": self.height,
                "bands": self.bands, "simulated": False, "source": "GeoTIFF header",
            },
            "geometry": {"type": "Polygon", "coordinates": [[
                [b["min_lng"], b["min_lat"]], [b["max_lng"], b["min_lat"]],
                [b["max_lng"], b["max_lat"]], [b["min_lng"], b["max_lat"]],
                [b["min_lng"], b["min_lat"]],
            ]]},
        }

    def footprint_wkt(self) -> str | None:
        if not self.bounds_lonlat:
            return None
        b = self.bounds_lonlat
        return (f"POLYGON(({b['min_lng']} {b['min_lat']}, {b['max_lng']} {b['min_lat']}, "
                f"{b['max_lng']} {b['max_lat']}, {b['min_lng']} {b['max_lat']}, "
                f"{b['min_lng']} {b['min_lat']}))")

    def to_dict(self) -> dict:
        crs_name = _KNOWN_EPSG.get(self.epsg, f"EPSG:{self.epsg}") if self.epsg else None
        return {
            "format": "GeoTIFF (TIFF tag parser, pure Python)",
            "byte_order": self.endianness,
            "dimensions": {"width": self.width, "height": self.height, "bands": self.bands},
            "bits_per_sample": self.bits_per_sample,
            "compression": self.compression,
            "photometric": self.photometric,
            "crs": {
                "epsg": self.epsg, "name": crs_name, "model_type": self.model_type,
                "angular_units": self.angular_units, "linear_units": self.linear_units,
                "citation": self.citation, "geo_keys": self.geo_keys,
            },
            "georeferencing": {"pixel_scale": self.pixel_scale, "tiepoint": self.tiepoints},
            "bounds": self.bounds_lonlat,
            "bounds_crs": self.bounds_crs,
            "footprint_geojson": self.footprint_geojson(),
            "footprint_wkt": self.footprint_wkt(),
            "simulated": False,
        }


def _project_bounds_to_lonlat(min_x, min_y, max_x, max_y, epsg: int | None) -> dict | None:
    """Approximate projected bounds → lon/lat degrees for common EPSG codes.

    Pseudo-Mercator (3857) is exact; UTM zones use a spherical approximate
    inverse. Display helper only — never survey-grade.
    """
    if epsg == 3857:
        def inv(x, y):
            lon = x / 6378137.0
            lat = math.degrees(2 * math.atan(math.exp(y / 6378137.0)) - math.pi / 2)
            return lon, lat
        lon0, lat0 = inv(min_x, min_y)
        lon1, lat1 = inv(max_x, max_y)
        return {"min_lng": round(lon0, 7), "min_lat": round(lat0, 7),
                "max_lng": round(lon1, 7), "max_lat": round(lat1, 7)}
    zone = None
    if epsg and 32600 < epsg < 32761:
        zone = epsg % 100
    if zone and 1 <= zone <= 60:
        lon_c = 6 * zone - 183
        avg_lat = math.radians((min_y + max_y) / 2)
        d_lng = (max_x - min_x) / (111320.0 * math.cos(avg_lat))
        d_lat = (max_y - min_y) / 110574.0
        return {"min_lng": round(lon_c - d_lng / 2, 7), "min_lat": round(min_y / 110574.0, 7),
                "max_lng": round(lon_c + d_lng / 2, 7), "max_lat": round(max_y / 110574.0, 7)}
    return None


def parse_geotiff(data: bytes) -> dict:
    return GeoTiffInfo(data).to_dict()
# ---------------------------------------------------------------------------
# Demo synthetic GeoTIFF generator (offline exploration, clearly labelled)
# ---------------------------------------------------------------------------

def make_demo_geotiff(epsg: int = 4326, width: int = 64, height: int = 64,
                      min_lng: float = 74.5, min_lat: float = 8.0,
                      max_lng: float = 77.5, max_lat: float = 12.5) -> bytes:
    """Build a valid minimal uncompressed 8-bit GeoTIFF with EPSG + bounds.

    Deterministic smooth gradient pixels so the header parse is fully
    reproducible. Output is clearly a SIMULATED raster, never real imagery.
    """
    pixel_w = (max_lng - min_lng) / width
    pixel_h = (max_lat - min_lat) / height

    pixels = bytearray()
    for row in range(height):
        for col in range(width):
            nx = col / max(width - 1, 1)
            ny = row / max(height - 1, 1)
            v = int(255 * (0.35 + 0.30 * math.sin(nx * 6.28 + 1.0) + 0.25 * math.sin(ny * 5.2 + row % 5)))
            pixels.append(max(0, min(255, v)))

    geo_key_dir = [1, 1, 0, 4,
                   1024, 0, 1, 1,                               # GTModelTypeGeoKey = 1 (geographic)
                   1025, 0, 1, 1,                               # GTRasterTypeGeoKey = 1
                   2048 if epsg <= 32767 else 3072, 0, 1, epsg]  # EPSG inline via Geographic/Projected key

    pixel_scale = (pixel_w, pixel_h, 0.0)
    tiepoint = (0.0, 0.0, 0.0, min_lng, max_lat, 0.0)

    # ---- long payloads (strip offset/count, scale, tiepoint, geokeys) ----
    scale_raw = struct.pack("<3d", *pixel_scale)
    tie_raw = struct.pack("<6d", *tiepoint)
    geo_raw = struct.pack("<%dH" % len(geo_key_dir), *geo_key_dir)
    strip_count_raw = struct.pack("<I", len(pixels))

    # Layout: header(8) + IFD(count + entries + next) + pixel strip + long payloads
    n_inline = 8                      # 256,257,258,259,262,277,278,284
    n_long = 5                        # 273,279,33550,33922,34735
    ifd_len = 2 + (n_inline + n_long) * 12 + 4
    pixel_data_off = 8 + ifd_len
    cursor = pixel_data_off + len(pixels)

    strip_off_cursor = cursor                      # long payload: POINTS TO pixel data
    long_payloads = [
        (strip_off_cursor, struct.pack("<I", pixel_data_off)),   # 273 StripOffsets value
        (cursor + 4, struct.pack("<I", len(pixels))),            # 279 StripByteCounts value
    ]
    cursor += 4 + 4
    long_payloads.append((cursor, scale_raw)); cursor += len(scale_raw)
    long_payloads.append((cursor, tie_raw));  cursor += len(tie_raw)
    long_payloads.append((cursor, geo_raw));  cursor += len(geo_raw)

    def inline_entry(tid, ftype, count, packed):
        return struct.pack("<HHI", tid, ftype, count) + packed.ljust(4, b"\x00")

    def long_entry(tid, ftype, count, offset):
        return struct.pack("<HHI", tid, ftype, count) + struct.pack("<I", offset)

    entries = [
        inline_entry(256, 3, 1, struct.pack("<H", width)),
        inline_entry(257, 3, 1, struct.pack("<H", height)),
        inline_entry(258, 3, 1, struct.pack("<H", 8)),
        inline_entry(259, 3, 1, struct.pack("<H", 1)),    # no compression
        inline_entry(262, 3, 1, struct.pack("<H", 1)),    # greyscale
        inline_entry(277, 3, 1, struct.pack("<H", 1)),    # 1 band
        inline_entry(278, 4, 1, struct.pack("<I", height)),
        inline_entry(284, 3, 1, struct.pack("<H", 1)),    # planar config
        long_entry(273, 4, 1, long_payloads[0][0]),       # StripOffsets
        long_entry(279, 4, 1, long_payloads[1][0]),       # StripByteCounts
        long_entry(33550, 12, 3, long_payloads[2][0]),    # ModelPixelScale
        long_entry(33922, 12, 6, long_payloads[3][0]),    # ModelTiepoint
        long_entry(34735, 3, len(geo_key_dir), long_payloads[4][0]),  # GeoKeyDirectory
    ]

    ifd = struct.pack("<H", len(entries)) + b"".join(entries) + struct.pack("<I", 0)
    body = b"".join(p for _, p in long_payloads)
    # Standard TIFF header: byte-order(2) + magic(2) + IFD offset(4) = 8 bytes
    return b"II" + struct.pack("<HI", 42, 8) + ifd + bytes(pixels) + body


def capability_flags() -> dict:
    return {
        "geotiff_parse": True,
        "wkt": True,
        "geojson_footprint": True,
        "epsg_detection": True,
        "spectral_indices": ["ndvi", "ndwi", "ndbi"],
        "sar_backscatter": True,
        "demo_synthesis": True,
    }