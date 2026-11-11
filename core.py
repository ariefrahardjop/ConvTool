# core.py — Logika inti ConvTool (tanpa tkinter, bisa diuji headless).
#
# Berisi: preset ukuran, hitung resize, resize gambar, baca/tulis EXIF
# (Pillow saja), reverse-geocode Nominatim, unduh & jahit tile peta,
# serta operasi PDF (PyMuPDF).
#
# Semua fungsi di sini TIDAK menampilkan GUI dan TIDAK membaca registry,
# sehingga seluruhnya bisa diuji dari baris perintah di Linux maupun
# Windows.

import concurrent.futures
import io
import json
import math
import os
import tempfile
import urllib.request
import urllib.error
from datetime import datetime

from PIL import Image, ImageDraw, ImageFont, ImageOps
from PIL.ExifTags import IFD
from PIL.TiffImagePlugin import IFDRational

import pymupdf

# ---------------------------------------------------------------- presets

# Preset ukuran (lebar x tinggi, piksel) — sama seperti dialog
# "Image Resizer for Windows" di screenshot yang dikirim user.
PRESETS = {
    "Small":  (854, 480),
    "Medium": (1366, 768),
    "Large":  (1920, 1080),
    "Phone":  (320, 569),
}
PRESET_ORDER = ["Small", "Medium", "Large", "Phone", "Custom"]

JPEG_QUALITY_DEFAULT = 90

# ---------------------------------------------------------------- util


def clamp(v, lo, hi):
    return max(lo, min(hi, v))


def fit_within(w, h, max_w, max_h):
    """(w, h) diskalakan agar muat dalam (max_w, max_h) dengan aspek
    dipertahankan; tidak pernah diperbesar. Dipakai ukuran pratinjau
    watermark: gambar pratinjau HARUS muat dalam lebar kolomnya,
    kalau tidak jendela (resizable=False) memotong gambar — foto
    landscape terpotong dan teks alamat di kartu tidak kelihatan."""
    scale = min(max_w / float(w), max_h / float(h), 1.0)
    return (max(1, int(w * scale)), max(1, int(h * scale)))


def suffix_for_size(preset_name):
    """Akhiran nama file hasil resize, mis. ' (Small)'."""
    return " (%s)" % preset_name


def output_path_for_resize(src_path, preset_name, out_ext=None):
    """Nama file hasil resize: 'nama (Small).jpg' di folder yang sama."""
    folder = os.path.dirname(src_path)
    stem = os.path.splitext(os.path.basename(src_path))[0]
    if out_ext is None:
        out_ext = os.path.splitext(src_path)[1] or ".jpg"
    if not out_ext.startswith("."):
        out_ext = "." + out_ext
    return os.path.join(folder, stem + suffix_for_size(preset_name) + out_ext)


# ---------------------------------------------------------------- hitung resize


def fit_size(w, h, tw, th, mode="fit", smaller_only=True):
    """Hitung ukuran hasil resize (lebar, tinggi) dengan aspek dipertahankan.

    mode:
      "fit"     — muat di dalam target (tidak ada bagian terpotong)
      "fill"    — tutupi target penuh (hasil akhir dipotong tengah ke target)
      "stretch" — paksa tepat ukuran target (aspek bisa berubah)
    smaller_only=True berarti gambar tidak pernah diperbesar.
    Untuk "fill", kembalian adalah ukuran SETELAH resize SEBELUM crop;
    pemanggil memotong tengah ke (min(rw, tw), min(rh, th)).
    """
    if w <= 0 or h <= 0 or tw <= 0 or th <= 0:
        raise ValueError("ukuran harus > 0")
    if mode == "stretch":
        if smaller_only and w <= tw and h <= th:
            return (w, h)
        return (tw, th)
    if mode == "fit":
        scale = min(tw / w, th / h)
    elif mode == "fill":
        scale = max(tw / w, th / h)
    else:
        raise ValueError("mode tidak dikenal: %r" % mode)
    if smaller_only:
        scale = min(scale, 1.0)
    return (max(1, int(round(w * scale))), max(1, int(round(h * scale))))


def resize_image(img, tw, th, mode="fit", smaller_only=True):
    """Resize PIL Image sesuai fit_size; untuk 'fill' dipotong tengah."""
    rw, rh = fit_size(img.width, img.height, tw, th, mode, smaller_only)
    out = img.resize((rw, rh), Image.LANCZOS)
    if mode == "fill":
        cw, ch = min(rw, tw), min(rh, th)
        left = (rw - cw) // 2
        top = (rh - ch) // 2
        out = out.crop((left, top, left + cw, top + ch))
    return out


# ---------------------------------------------------------------- resize file


def _clean_exif_for_output(exif):
    """EXIF untuk file hasil resize: orientasi dinormalkan ke 1 dan
    tag dimensi piksel dihapus (nilainya sudah tidak berlaku)."""
    if exif is None:
        return None
    try:
        exif[274] = 1  # Orientation
        for tag in (40962, 40963):  # PixelXDimension, PixelYDimension
            if tag in exif:
                del exif[tag]
    except Exception:
        pass
    return exif


def resize_image_file(src_path, dst_path, tw, th, mode="fit",
                      smaller_only=True, quality=JPEG_QUALITY_DEFAULT,
                      out_format="same", ignore_orientation=True):
    """Resize satu file gambar dan simpan ke dst_path.

    out_format: "same" (ikut format asli), "JPEG", atau "PNG".
    ignore_orientation=True: abaikan tag EXIF Orientation (pakai piksel
    apa adanya, seperti checkbox default di Image Resizer).
    Mengembalikan (lebar_baru, tinggi_baru, format_simpan).

    Membaca sumber di dalam `with` lalu menutupnya SEBELUM menyimpan,
    supaya aman juga bila dst_path == src_path (timpa file asli).
    """
    with Image.open(src_path) as img:
        if not ignore_orientation:
            img = ImageOps.exif_transpose(img)
        exif = None
        try:
            exif = img.getexif()
        except Exception:
            exif = None
        out = resize_image(img, tw, th, mode, smaller_only)
        fmt_orig = (img.format or "JPEG").upper()
        if fmt_orig == "JPG":
            fmt_orig = "JPEG"
    fmt = out_format
    if fmt == "same":
        # "same" = ikut format asli, TAPI bila ekstensi dst_path sudah
        # menentukan format lain (mis. sumber PNG disimpan ke .jpg),
        # ekstensi tujuan yang menang — supaya isi file selalu cocok
        # dengan namanya.
        known = {".jpg": "JPEG", ".jpeg": "JPEG", ".png": "PNG",
                 ".webp": "WEBP", ".bmp": "BMP", ".gif": "GIF",
                 ".tif": "TIFF", ".tiff": "TIFF"}
        fmt = known.get(os.path.splitext(dst_path)[1].lower(), fmt_orig)
    save_kw = {}
    if fmt == "JPEG":
        save_kw["quality"] = int(quality)
        save_kw["optimize"] = True
        if out.mode in ("RGBA", "LA", "PA"):
            bg = Image.new("RGB", out.size, (255, 255, 255))
            bg.paste(out, mask=out.split()[-1])
            out = bg
        elif out.mode != "RGB":
            out = out.convert("RGB")
        exif_out = _clean_exif_for_output(exif)
        if exif_out is not None:
            save_kw["exif"] = exif_out
    elif fmt in ("PNG", "WEBP"):
        exif_out = _clean_exif_for_output(exif)
        if exif_out is not None:
            save_kw["exif"] = exif_out
    out.save(dst_path, fmt, **save_kw)
    return (out.width, out.height, fmt)


# ---------------------------------------------------------------- EXIF


def _sub_ifd(exif, tag):
    """Ambil sub-IFD (Exif/GPS) sebagai dict biasa dan pastikan dict itu
    tersimpan di EXIF utama, supaya perubahan ikut tersimpan saat save.
    WAJIB dict biasa — Image.Exif sebagai nilai sub-IFD membuat
    Pillow 13 gagal saat tobytes() (mencari offset di fp yang tak ada).
    """
    try:
        d = exif.get_ifd(tag)
    except Exception:
        d = {}
    if not isinstance(d, dict):
        d = {}
    exif[tag] = d
    return d


def read_exif(path):
    """Baca EXIF sebuah gambar. Kembalian: dict dengan kunci:
    datetime (str 'YYYY:MM:DD HH:MM:SS' atau None),
    lat, lon (float atau None), make, model (str),
    tags (list (nama, nilai) semua tag utama, read-only),
    raw (objek PIL Image.Exif untuk dipakai ulang bila perlu).
    Catatan: DateTimeOriginal (36867) tinggal di sub-IFD Exif, bukan
    IFD0 — dibaca lewat get_ifd(IFD.Exif)."""
    img = Image.open(path)
    exif = img.getexif()
    result = {"datetime": None, "lat": None, "lon": None,
              "make": None, "model": None, "tags": [], "raw": exif}
    try:
        sub = exif.get_ifd(IFD.Exif)
        dt = sub.get(36867) if isinstance(sub, dict) else None
        if not dt:
            dt = exif.get(306)
        if dt:
            result["datetime"] = str(dt)
    except Exception:
        pass
    try:
        result["make"] = _clean_str(exif.get(271))
        result["model"] = _clean_str(exif.get(272))
    except Exception:
        pass
    try:
        lat, lon = gps_from_exif(exif)
        result["lat"], result["lon"] = lat, lon
    except Exception:
        pass
    try:
        from PIL.ExifTags import TAGS
        seen = set()
        for tag_id, value in list(exif.items()):
            if tag_id in (IFD.Exif, IFD.GPSInfo):
                continue
            name = TAGS.get(tag_id, "Tag %d" % tag_id)
            seen.add(tag_id)
            result["tags"].append((name, _short_value(value)))
        sub = exif.get_ifd(IFD.Exif)
        if isinstance(sub, dict):
            for tag_id, value in sub.items():
                if tag_id in seen or tag_id == IFD.Interop:
                    continue
                name = TAGS.get(tag_id, "Tag %d" % tag_id)
                result["tags"].append((name, _short_value(value)))
    except Exception:
        pass
    return result


def _clean_str(v):
    if v is None:
        return None
    if isinstance(v, bytes):
        try:
            return v.decode("utf-8", "replace").strip("\x00 ").strip()
        except Exception:
            return None
    return str(v).strip()


def _short_value(v):
    s = _clean_str(v)
    if s is None:
        return ""
    if len(s) > 120:
        return s[:117] + "..."
    return s


def _rational_to_float(v):
    try:
        return float(v)
    except Exception:
        pass
    try:
        return v.numerator / v.denominator
    except Exception:
        return 0.0


def _dms_to_decimal(dms, ref):
    if not dms or len(dms) < 3:
        return None
    d = _rational_to_float(dms[0])
    m = _rational_to_float(dms[1])
    s = _rational_to_float(dms[2])
    dec = d + m / 60.0 + s / 3600.0
    if ref in ("S", "W"):
        dec = -dec
    return dec


def gps_from_exif(exif):
    """Ambil (lat, lon) dari EXIF Pillow; (None, None) bila tidak ada."""
    try:
        gps = exif.get_ifd(IFD.GPSInfo)
    except Exception:
        return (None, None)
    if not gps:
        return (None, None)
    lat = _dms_to_decimal(gps.get(2), gps.get(1))
    lon = _dms_to_decimal(gps.get(4), gps.get(3))
    return (lat, lon)


def _decimal_to_dms(dec):
    a = abs(float(dec))
    d = int(a)
    m_f = (a - d) * 60.0
    m = int(m_f)
    s = (m_f - m) * 60.0
    return ((d, 1), (m, 1), (int(round(s * 10000)), 10000))


def set_gps_in_exif(exif, lat, lon):
    """Set GPS ke objek PIL Image.Exif (membuat/menimpa IFD GPS).
    Nilai sub-IFD disimpan sebagai dict biasa (lihat _sub_ifd)."""
    gps = _sub_ifd(exif, IFD.GPSInfo)
    gps[0] = b"\x02\x02\x00\x00"  # GPSVersionID 2.2.0.0
    gps[1] = "N" if lat >= 0 else "S"
    gps[2] = tuple(IFDRational(n, d) for (n, d) in _decimal_to_dms(lat))
    gps[3] = "E" if lon >= 0 else "W"
    gps[4] = tuple(IFDRational(n, d) for (n, d) in _decimal_to_dms(lon))
    return exif


def set_datetime_in_exif(exif, dt):
    """Set DateTimeOriginal (sub-IFD Exif) + DateTime (IFD0)."""
    sub = _sub_ifd(exif, IFD.Exif)
    sub[36867] = format_exif_datetime(dt)
    exif[306] = format_exif_datetime(dt)
    return exif


def parse_exif_datetime(s):
    """'YYYY:MM:DD HH:MM:SS' -> datetime; None bila tidak valid."""
    if not s:
        return None
    try:
        return datetime.strptime(str(s).strip(), "%Y:%m:%d %H:%M:%S")
    except Exception:
        return None


def format_exif_datetime(dt):
    return dt.strftime("%Y:%m:%d %H:%M:%S")


def _apply_extra_tags(exif, extra_tags):
    """Terapkan edit tag IFD0 dari dialog EXIF Editor. Nama tag yang
    dikenali: Make, Model, ImageDescription, Artist, Copyright,
    Software (teks) dan XResolution, YResolution (angka). Orientation
    SENGAJA tidak ada di sini: hasil selalu ditegakkan sehingga
    Orientation harus tetap 1."""
    string_tags = {270: "ImageDescription", 271: "Make", 272: "Model",
                   305: "Software", 315: "Artist", 33432: "Copyright"}
    float_tags = {282: "XResolution", 283: "YResolution"}
    by_name = {v: k for k, v in string_tags.items()}
    by_name.update({v: k for k, v in float_tags.items()})
    for name, value in (extra_tags or {}).items():
        tag_id = by_name.get(name)
        if tag_id is None:
            continue
        if tag_id in float_tags:
            try:
                f = float(value)
                exif[tag_id] = IFDRational(int(round(f * 100)), 100)
            except (TypeError, ValueError):
                continue
        else:
            exif[tag_id] = str(value)


def save_image_with_exif(src_path, dst_path, new_datetime=None,
                         new_lat=None, new_lon=None, quality=95,
                         extra_tags=None):
    """Simpan salinan gambar dengan EXIF diubah (datetime dan/atau GPS).
    Semua tag EXIF lain dipertahankan apa adanya. extra_tags: dict
    nama tag IFD0 -> nilai baru (lihat _apply_extra_tags).
    Kualitas JPEG 95 agar tidak ada penurunan kualitas yang terasa pada
    file edit. Mengembalikan dict hasil read_exif(dst_path).
    """
    img = Image.open(src_path)
    img = ImageOps.exif_transpose(img)  # hasil edit selalu tegak
    exif = img.getexif()
    if new_datetime is not None:
        set_datetime_in_exif(exif, new_datetime)
    if new_lat is not None and new_lon is not None:
        set_gps_in_exif(exif, new_lat, new_lon)
    exif[274] = 1  # Orientation sudah diterapkan
    if extra_tags:
        _apply_extra_tags(exif, extra_tags)
    fmt = (img.format or "JPEG").upper()
    if fmt == "JPG":
        fmt = "JPEG"
    save_kw = {"exif": exif}
    if fmt == "JPEG":
        save_kw["quality"] = int(quality)
        if img.mode in ("RGBA", "LA", "PA"):
            bg = Image.new("RGB", img.size, (255, 255, 255))
            bg.paste(img, mask=img.split()[-1])
            img = bg
        elif img.mode != "RGB":
            img = img.convert("RGB")
    img.save(dst_path, fmt, **save_kw)
    return read_exif(dst_path)


# ---------------------------------------------------------------- geocode


def reverse_geocode(lat, lon, timeout=10):
    """Alamat dari koordinat via Nominatim (OpenStreetMap).
    Mengembalikan display_name (str) atau None bila offline/gagal.
    User-Agent wajib diisi sesuai kebijakan penggunaan Nominatim.
    """
    name, _addr = reverse_geocode_full(lat, lon, timeout=timeout)
    return name


def reverse_geocode_full(lat, lon, timeout=10):
    """Seperti reverse_geocode, tapi mengembalikan
    (display_name, dict address terstruktur) — dict-nya dipakai
    untuk menurunkan nama Tempat (kecamatan). (None, {}) bila gagal.
    """
    url = ("https://nominatim.openstreetmap.org/reverse"
           "?format=jsonv2&lat=%.6f&lon=%.6f&zoom=18&addressdetails=1"
           % (lat, lon))
    req = urllib.request.Request(
        url, headers={"User-Agent": "ConvTool/1.0 (Windows desktop app)"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            data = json.loads(r.read().decode("utf-8"))
        name = data.get("display_name")
        addr = data.get("address") or {}
        return (name if name else None,
                addr if isinstance(addr, dict) else {})
    except Exception:
        return (None, {})


def place_from_address(addr):
    """'Kecamatan Wonocolo, Jawa Timur, Indonesia' dari dict address
    Nominatim (addressdetails=1). Kecamatan dicari di municipality,
    city_district, county — BUKAN village/suburb (itu kelurahan).
    None bila kecamatan tidak ditemukan."""
    if not addr:
        return None
    kec = None
    for key in ("municipality", "city_district", "county"):
        v = (addr.get(key) or "").strip()
        if v:
            kec = v
            break
    if not kec:
        return None
    low = kec.lower()
    if low.startswith("kecamatan"):
        label = kec
    elif low.startswith("kec."):
        label = "Kecamatan " + kec[4:].strip()
    else:
        label = "Kecamatan " + kec
    parts = [label]
    state = (addr.get("state") or "").strip()
    if state:
        parts.append(state)
    country = (addr.get("country") or "").strip()
    if country:
        parts.append(country)
    return ", ".join(parts)


# ---------------------------------------------------------------- tile peta

_TILE_CACHE_DIR = os.path.join(tempfile.gettempdir(), "ConvTool_tiles")
_TILE_TIMEOUT = 5


def tile_url(style, z, x, y):
    """URL satu tile. style 'sat' (Esri satelit) atau 'road' (OSM jalan)."""
    if style == "sat":
        return ("https://server.arcgisonline.com/ArcGIS/rest/services/"
                "World_Imagery/MapServer/tile/%d/%d/%d" % (z, y, x))
    return "https://tile.openstreetmap.de/%d/%d/%d.png" % (z, x, y)


def tile_fallback_url(style, z, x, y):
    if style == "sat":
        return ("https://services.arcgisonline.com/ArcGIS/rest/services/"
                "World_Imagery/MapServer/tile/%d/%d/%d" % (z, y, x))
    return ("https://server.arcgisonline.com/ArcGIS/rest/services/"
            "World_Street_Map/MapServer/tile/%d/%d/%d" % (z, y, x))


def _latlon_to_tile_px(lat, lon, z):
    n = 2.0 ** z
    x = (lon + 180.0) / 360.0 * n
    r = math.radians(lat)
    y = (1.0 - math.log(math.tan(r) + 1.0 / math.cos(r)) / math.pi) / 2.0 * n
    return (x * 256.0, y * 256.0)


def fetch_tile(style, z, x, y):
    """Unduh satu tile 256x256 (cache di folder temp). None bila gagal."""
    try:
        os.makedirs(_TILE_CACHE_DIR, exist_ok=True)
    except Exception:
        pass
    cache_name = "%s_%d_%d_%d.png" % (style, z, x, y)
    cache_path = os.path.join(_TILE_CACHE_DIR, cache_name)
    try:
        if os.path.exists(cache_path) and os.path.getsize(cache_path) > 100:
            return Image.open(cache_path).convert("RGB")
    except Exception:
        pass
    for url in (tile_url(style, z, x, y), tile_fallback_url(style, z, x, y)):
        try:
            req = urllib.request.Request(
                url, headers={"User-Agent": "ConvTool/1.0 (Windows desktop app)"})
            with urllib.request.urlopen(req, timeout=_TILE_TIMEOUT) as r:
                data = r.read()
            if len(data) < 100:
                continue
            tile = Image.open(io.BytesIO(data)).convert("RGB")
            try:
                tile.save(cache_path, "PNG")
            except Exception:
                pass
            return tile
        except Exception:
            continue
    return None


def stitch_map(lat, lon, w, h, style):
    """Jahit tile menjadi peta berukuran (w, h) dengan lat/lon di tengah.
    style 'sat' = Esri zoom 17, 'road' = OSM zoom 15. Bila semua tile
    gagal (offline), kembalikan peta sketsa. Selalu mengembalikan
    PIL Image RGB — tidak pernah None.
    Mengembalikan (gambar, True) bila tile asli, (gambar, False) bila sketsa.
    """
    w, h = int(w), int(h)
    z = 17 if style == "sat" else 15
    cx, cy = _latlon_to_tile_px(lat, lon, z)
    scale_f = max(w, h) / 256.0
    view_w, view_h = w / scale_f, h / scale_f
    x0 = int(math.floor((cx - view_w / 2) / 256))
    x1 = int(math.floor((cx + view_w / 2) / 256))
    y0 = int(math.floor((cy - view_h / 2) / 256))
    y1 = int(math.floor((cy + view_h / 2) / 256))
    max_t = (1 << z) - 1
    canvas = Image.new("RGB", (w, h),
                       (93, 112, 82) if style == "sat" else (232, 239, 228))
    drawn = False
    # Unduh tile secara paralel (4 worker) — unduhan sekuensial membuat
    # pratinjau peta terasa "gagal" di koneksi lambat (timeout x 4 tile).
    jobs = []
    for tx in range(x0, x1 + 1):
        for ty in range(y0, y1 + 1):
            if ty < 0 or ty > max_t:
                continue
            jobs.append((tx, ty))
    tiles = {}
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
        futs = {pool.submit(fetch_tile, style, z, tx % (max_t + 1), ty):
                (tx, ty) for (tx, ty) in jobs}
        for fut in concurrent.futures.as_completed(futs):
            try:
                tiles[futs[fut]] = fut.result()
            except Exception:
                tiles[futs[fut]] = None
    for (tx, ty), tile in tiles.items():
        if tile is None:
            continue
        dx = int(round((tx * 256 - (cx - view_w / 2)) * scale_f))
        dy = int(round((ty * 256 - (cy - view_h / 2)) * scale_f))
        ts = int(round(256 * scale_f)) + 1
        canvas.paste(tile.resize((ts, ts), Image.LANCZOS), (dx, dy))
        drawn = True
    if not drawn:
        canvas = _sketch_map(w, h, style)
    # Pin merah di tengah + label "Google" di kiri bawah (seperti referensi).
    draw = ImageDraw.Draw(canvas, "RGBA")
    _draw_pin(draw, w / 2.0, h / 2.0, min(w, h) * 0.085)
    _draw_google_label(canvas, w * 0.055, h - w * 0.045,
                       min(w * 0.17, h * 0.2), style == "sat")
    return (canvas, drawn)


def map_pixel_to_latlon(center_lat, center_lon, w, h, px, py, zoom=15):
    """Kebalikan pemetaan tile stitch_map: piksel (px, py) pada peta
    berukuran (w, h) yang berpusat di (center_lat, center_lon) ->
    (lat, lon). Dipakai klik-pilih koordinat di EXIF Editor."""
    z = zoom
    n = 2.0 ** z
    world = n * 256.0
    cx, cy = _latlon_to_tile_px(center_lat, center_lon, z)
    scale_f = max(w, h) / 256.0
    view_w, view_h = w / scale_f, h / scale_f
    tx = cx - view_w / 2 + px / scale_f
    ty = cy - view_h / 2 + py / scale_f
    lon = tx / world * 360.0 - 180.0
    lat = math.degrees(math.atan(math.sinh(math.pi * (1 - 2 * ty / world))))
    return (lat, lon)


def _sketch_map(w, h, style):
    """Peta sketsa bila offline: bidang + garis jalan diagonal."""
    base = (93, 112, 82) if style == "sat" else (232, 239, 228)
    img = Image.new("RGB", (w, h), base)
    draw = ImageDraw.Draw(img, "RGBA")
    line_col = (255, 255, 255, 89) if style == "sat" else (255, 255, 255, 255)
    lw = max(3, int(w * 0.045))
    for i in range(-1, 4):
        draw.line([(i * w * 0.32, h), (i * w * 0.32 + w * 0.25, 0)],
                  fill=line_col, width=lw)
        draw.line([(0, i * h * 0.34), (w, i * h * 0.34 - h * 0.18)],
                  fill=line_col, width=lw)
    if style != "sat":
        # Danau biru miring di kanan atas.
        draw.ellipse([w * 0.62, h * 0.07, w * 1.02, h * 0.33],
                     fill=(140, 180, 230, 128))
    return img


def _cubic_bezier(p0, p1, p2, p3, n=28):
    """Titik-titik kurva Bezier kubik (dipakai pin & awan cuaca)."""
    pts = []
    for i in range(n + 1):
        t = i / n
        mt = 1 - t
        x = (mt ** 3 * p0[0] + 3 * mt * mt * t * p1[0]
             + 3 * mt * t * t * p2[0] + t ** 3 * p3[0])
        y = (mt ** 3 * p0[1] + 3 * mt * mt * t * p1[1]
             + 3 * mt * t * t * p2[1] + t ** 3 * p3[1])
        pts.append((x, y))
    return pts


def _draw_pin(draw, cx, cy, r):
    """Pin tetesan merah gaya Google (seperti drawPin aplikasi web):
    kepala bundar (kurva Bezier) + ujung lancip di bawah,
    titik gelap di dalam, bayangan lembut di bawah pin."""
    tip = (cx, cy + r * 1.55)
    top = (cx, cy - r * 0.55)
    left = _cubic_bezier(tip, (cx - r * 1.02, cy + r * 0.35),
                         (cx - r * 1.02, cy - r * 0.55), top)
    right = _cubic_bezier(top, (cx + r * 1.02, cy - r * 0.55),
                          (cx + r * 1.02, cy + r * 0.35), tip)
    pts = left + right[1:]
    shadow = [(x, y + r * 0.12) for (x, y) in pts]
    draw.polygon(shadow, fill=(0, 0, 0, 90))
    draw.polygon(pts, fill=(230, 33, 23, 255))
    draw.ellipse([cx - r * 0.44, cy - r * 0.56, cx + r * 0.44, cy + r * 0.32],
                 fill=(122, 13, 8, 255))


def _draw_google_label(img, x, baseline_y, size, satellite):
    """Teks 'Google' huruf per huruf, font BOLD seperti aplikasi web
    (jalan: warna Google per huruf; satelit: putih ber-outline gelap).
    baseline_y = garis dasar teks (seperti canvas); jarak antar huruf
    0.98x lebar huruf."""
    try:
        font = ImageFont.truetype(_font_path(True), int(max(10, size)))
    except Exception:
        font = ImageFont.load_default()
    draw = ImageDraw.Draw(img, "RGBA")
    colors = [(66, 133, 244), (234, 67, 53), (251, 188, 5),
              (66, 133, 244), (52, 168, 83), (234, 67, 53)]
    cx = x
    for i, ch in enumerate("Google"):
        col = (255, 255, 255, 255) if satellite else colors[i] + (255,)
        if satellite:
            for dx, dy in ((-1, 0), (1, 0), (0, -1), (0, 1),
                           (-1, -1), (1, -1), (-1, 1), (1, 1)):
                draw.text((cx + dx, baseline_y + dy), ch,
                          font=font, fill=(0, 0, 0, 217), anchor="ls")
        draw.text((cx, baseline_y), ch, font=font, fill=col, anchor="ls")
        cx += draw.textlength(ch, font=font) * 0.98


# ---------------------------------------------------------------- cuaca (Job)


def _cloud_polygon(cx, cy, w):
    """Titik-titik awan (cloudPath aplikasi web): 3 segmen Bezier."""
    h = w * 0.52
    pts = _cubic_bezier((cx - w / 2, cy + h / 2),
                        (cx - w / 2, cy - h * 0.05),
                        (cx - w * 0.32, cy - h * 0.12),
                        (cx - w * 0.27, cy - h * 0.28))
    pts += _cubic_bezier((cx - w * 0.27, cy - h * 0.28),
                         (cx - w * 0.2, cy - h * 0.62),
                         (cx + w * 0.12, cy - h * 0.66),
                         (cx + w * 0.24, cy - h * 0.34))[1:]
    pts += _cubic_bezier((cx + w * 0.24, cy - h * 0.34),
                         (cx + w * 0.44, cy - h * 0.3),
                         (cx + w / 2, cy - h * 0.02),
                         (cx + w / 2, cy + h / 2))[1:]
    return pts


def _gradient_polygon(base, pts, top_color, bottom_color):
    """Gambar poligon berisi gradien vertikal (atas -> bawah)
    di atas gambar RGBA."""
    xs = [p[0] for p in pts]
    ys = [p[1] for p in pts]
    x0, y0 = int(min(xs)), int(min(ys))
    x1, y1 = int(max(xs)) + 1, int(max(ys)) + 1
    w, h = max(1, x1 - x0), max(1, y1 - y0)
    grad = Image.new("RGBA", (w, h))
    px = grad.load()
    for yy in range(h):
        t = yy / max(1, h - 1)
        col = tuple(int(round(top_color[i]
                              + (bottom_color[i] - top_color[i]) * t))
                    for i in range(3)) + (255,)
        for xx in range(w):
            px[xx, yy] = col
    mask = Image.new("L", (w, h), 0)
    ImageDraw.Draw(mask).polygon(
        [(x - x0, y - y0) for (x, y) in pts], fill=255)
    base.paste(grad, (x0, y0), mask)


def _sun_disc(draw, cx, cy, r):
    """Matahari: lingkaran gradien radial #ffe082 (tengah) -> #ffb300."""
    steps = 14
    for i in range(steps, 0, -1):
        t = i / steps
        col = (255,
               int(round(224 * (1 - t) + 179 * t)),
               int(round(130 * (1 - t) + 0 * t)))
        rr = r * t
        draw.ellipse([cx - rr, cy - rr, cx + rr, cy + rr], fill=col + (255,))


def draw_weather(layer, kind, cx, cy, w):
    """Gambar ikon cuaca gaya aplikasi web (sunny/partly/cloudy/rain)
    pada layer RGBA. (cx, cy) = tengah area ikon, w = lebar area."""
    d = ImageDraw.Draw(layer, "RGBA")
    if kind in ("sunny", "partly"):
        sx = cx if kind == "sunny" else cx - w * 0.22
        sy = cy if kind == "sunny" else cy - w * 0.18
        sr = w * 0.2
        for i in range(8):
            a = i * math.pi / 4
            d.line([(sx + math.cos(a) * sr * 1.2,
                     sy + math.sin(a) * sr * 1.2),
                    (sx + math.cos(a) * sr * 1.55,
                     sy + math.sin(a) * sr * 1.55)],
                   fill=(247, 181, 0, 255),
                   width=max(1, int(round(w * 0.045))))
        _sun_disc(d, sx, sy, sr)
    if kind != "sunny":
        if kind in ("cloudy", "rain"):
            pts = _cloud_polygon(cx + w * 0.17, cy - w * 0.07, w * 0.72)
            d.polygon(pts, fill=(91, 102, 112, 255))
        fx = cx + (w * 0.1 if kind == "partly" else 0)
        pts = _cloud_polygon(fx, cy + w * 0.05, w * 0.92)
        shadow = [(x + w * 0.02, y + w * 0.03) for (x, y) in pts]
        d.polygon(shadow, fill=(0, 0, 0, 64))
        _gradient_polygon(layer, pts, (255, 255, 255), (207, 216, 220))
        if kind == "rain":
            for o in (-0.28, 0, 0.28):
                d.line([(cx + o * w, cy + w * 0.34),
                        (cx + o * w - w * 0.07, cy + w * 0.52)],
                       fill=(79, 195, 247, 255),
                       width=max(1, int(round(w * 0.05))))


# ---------------------------------------------------------------- font


def _font_path(bold=False):
    """Cari file TTF: Arial di Windows, DejaVu/Liberation di Linux.
    Dipakai watermark & pratinjau peta; fallback ditangani pemanggil."""
    names = []
    if bold:
        names = ["arialbd.ttf", "DejaVuSans-Bold.ttf",
                 "LiberationSans-Bold.ttf"]
    else:
        names = ["arial.ttf", "DejaVuSans.ttf", "LiberationSans-Regular.ttf"]
    dirs = [r"C:\Windows\Fonts",
            "/usr/share/fonts/truetype/dejavu",
            "/usr/share/fonts/truetype/liberation",
            "/usr/share/fonts/truetype/msttcorefonts"]
    for d in dirs:
        for n in names:
            p = os.path.join(d, n)
            if os.path.exists(p):
                return p
    raise FileNotFoundError("font tidak ditemukan: %s" % names[0])


def load_font(px, bold=False):
    try:
        return ImageFont.truetype(_font_path(bold), int(max(8, round(px))))
    except Exception:
        return ImageFont.load_default()


# ---------------------------------------------------------------- PDF


# Ukuran kertas dalam point (72 DPI). Folio/F4 = 215 x 330 mm.
PAPER_SIZES = {
    "A4": (595.0, 842.0),
    "Folio": (609.45, 935.43),
    "Letter": (612.0, 792.0),
    "Legal": (612.0, 1008.0),
    "A5": (420.0, 595.0),
}
PAPER_ORDER = ["A4", "Folio", "Letter", "Legal", "A5"]


def _image_bytes_for_pdf(path, resize=None):
    """Untuk insert_image PyMuPDF: JPEG bisa langsung pakai filename;
    format lain (WEBP/BMP/GIF/PNG transparan) dikonversi dulu ke PNG
    bytes via Pillow — PyMuPDF tidak mengenal WEBP ('unknown image
    file format'). Bila resize = nama preset (Small/Medium/Large),
    gambar dikecilkan dulu agar muat dalam preset (JPEG bytes,
    kualitas 90) sehingga PDF yang dihasilkan lebih kecil.
    Mengembalikan None bila filename bisa dipakai langsung, atau
    bytes gambar."""
    if resize:
        target = PRESETS.get(resize)
        if target is not None:
            with Image.open(path) as im:
                im = ImageOps.exif_transpose(im)
                if im.mode in ("RGBA", "LA", "PA"):
                    bg = Image.new("RGB", im.size, (255, 255, 255))
                    bg.paste(im, mask=im.split()[-1])
                    im = bg
                elif im.mode != "RGB":
                    im = im.convert("RGB")
                im.thumbnail(target, Image.LANCZOS)
                buf = io.BytesIO()
                im.save(buf, "JPEG", quality=90)
                return buf.getvalue()
    ext = os.path.splitext(path)[1].lower()
    if ext in (".jpg", ".jpeg"):
        return None
    with Image.open(path) as im:
        if im.mode in ("RGBA", "LA", "PA"):
            bg = Image.new("RGB", im.size, (255, 255, 255))
            bg.paste(im, mask=im.split()[-1])
            im = bg
        elif im.mode != "RGB":
            im = im.convert("RGB")
        buf = io.BytesIO()
        im.save(buf, "PNG")
        return buf.getvalue()


def _image_bytes_for_pdf_fill(path, page_w, page_h, resize=None):
    """Gambar untuk mode full: dipotong tengah (center-crop) mengikuti
    rasio halaman, lalu opsional di-resize ke preset. Selalu bytes
    JPEG (kualitas 90)."""
    with Image.open(path) as im:
        im = ImageOps.exif_transpose(im)
        if im.mode in ("RGBA", "LA", "PA"):
            bg = Image.new("RGB", im.size, (255, 255, 255))
            bg.paste(im, mask=im.split()[-1])
            im = bg
        elif im.mode != "RGB":
            im = im.convert("RGB")
        target_ratio = page_w / page_h
        w, h = im.size
        ratio = w / h
        if ratio > target_ratio:
            new_w = int(h * target_ratio)
            x0 = (w - new_w) // 2
            im = im.crop((x0, 0, x0 + new_w, h))
        else:
            new_h = int(w / target_ratio)
            y0 = (h - new_h) // 2
            im = im.crop((0, y0, w, y0 + new_h))
        if resize:
            target = PRESETS.get(resize)
            if target is not None:
                im.thumbnail(target, Image.LANCZOS)
        buf = io.BytesIO()
        im.save(buf, "JPEG", quality=90)
        return buf.getvalue()


def images_to_pdf(image_paths, output_path, page_size="A4",
                  orientation="portrait", fill=False, resize=None):
    """Gabung beberapa gambar jadi satu PDF; tiap gambar satu halaman.
    page_size: kunci PAPER_SIZES (default A4). orientation:
    'portrait'/'landscape'. fill=True: gambar dipotong tengah agar
    memenuhi seluruh halaman tanpa margin ('full'). fill=False:
    gambar dimuat penuh dengan aspek dipertahankan di dalam margin
    0,5 inci. resize: nama preset (Small/Medium/Large) untuk
    mengecilkan gambar sebelum dimasukkan (PDF lebih kecil), atau
    None = Original. Mengembalikan jumlah halaman yang ditulis."""
    doc = pymupdf.open()
    margin = 36  # 0,5 inci
    page_w, page_h = PAPER_SIZES.get(page_size, PAPER_SIZES["A4"])
    if orientation == "landscape":
        page_w, page_h = page_h, page_w
    for path in image_paths:
        page = doc.new_page(width=page_w, height=page_h)
        if fill:
            rect = pymupdf.Rect(0, 0, page_w, page_h)
            data = _image_bytes_for_pdf_fill(path, page_w, page_h, resize)
            page.insert_image(rect, stream=data, keep_proportion=False)
        else:
            rect = pymupdf.Rect(margin, margin, page_w - margin,
                                page_h - margin)
            data = _image_bytes_for_pdf(path, resize)
            if data is None:
                page.insert_image(rect, filename=path, keep_proportion=True)
            else:
                page.insert_image(rect, stream=data, keep_proportion=True)
    doc.save(output_path, garbage=4, deflate=True)
    count = len(doc)
    doc.close()
    return count


def pdf_to_images(pdf_path, out_dir, base_name, longest_px, fmt="PNG"):
    """Render tiap halaman PDF jadi gambar. longest_px = sisi terpanjang
    dalam piksel. Nama hasil: base_p001.png dst di out_dir.
    Mengembalikan list path hasil."""
    doc = pymupdf.open(pdf_path)
    out = []
    fmt = fmt.upper()
    ext = "png" if fmt == "PNG" else "jpg"
    for i, page in enumerate(doc):
        zoom = longest_px / max(page.rect.width, page.rect.height)
        pix = page.get_pixmap(matrix=pymupdf.Matrix(zoom, zoom))
        name = "%s_p%03d.%s" % (base_name, i + 1, ext)
        dst = os.path.join(out_dir, name)
        pix.save(dst)
        out.append(dst)
    doc.close()
    return out


def resize_pdf(pdf_path, output_path, target_w_px, target_h_px):
    """Buat PDF baru: tiap halaman jadi berukuran target (px pada 96 DPI
    -> point = px * 72 / 96), konten diskalakan agar muat dan diletakkan
    di tengah halaman. Konten tidak pernah diperbesar (skala maks 1,0).
    Mengembalikan jumlah halaman."""
    tw_pt = target_w_px * 72.0 / 96.0
    th_pt = target_h_px * 72.0 / 96.0
    src = pymupdf.open(pdf_path)
    dst = pymupdf.open()
    for page in src:
        scale = min(tw_pt / page.rect.width, th_pt / page.rect.height, 1.0)
        cw, ch = page.rect.width * scale, page.rect.height * scale
        newpage = dst.new_page(width=tw_pt, height=th_pt)
        x0 = (tw_pt - cw) / 2.0
        y0 = (th_pt - ch) / 2.0
        newpage.show_pdf_page(pymupdf.Rect(x0, y0, x0 + cw, y0 + ch),
                              src, page.number)
    dst.save(output_path, garbage=4, deflate=True)
    count = len(dst)
    src.close()
    dst.close()
    return count


def pdf_page_count(pdf_path):
    doc = pymupdf.open(pdf_path)
    n = len(doc)
    doc.close()
    return n
