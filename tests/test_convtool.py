# tests/test_convtool.py — Uji logika inti ConvTool (headless).
#
# Jalankan dari ~/workspace/convtool:
#   .venv-test/bin/python tests/test_convtool.py
#
# Yang diuji: hitung resize (semua preset), resize file nyata,
# images->PDF->images round-trip, resize PDF, baca/tulis EXIF
# round-trip, render watermark Klasik & Job, format tanggal/koordinat.
# GUI tkinter, .exe, dan registry TIDAK bisa diuji headless di VM ini.

import math
import os
import shutil
import sys
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PIL import Image  # noqa: E402

import core  # noqa: E402
import watermark  # noqa: E402

WORK = os.path.join(os.path.dirname(os.path.abspath(__file__)), "work")
FAILURES = []
PASSES = [0]


def check(name, cond, detail=""):
    if cond:
        PASSES[0] += 1
        print("PASS  %s %s" % (name, detail))
    else:
        FAILURES.append(name)
        print("FAIL  %s %s" % (name, detail))


def make_photo(path, w, h, color=(40, 120, 200)):
    """Foto uji: gradasi + beberapa bentuk supaya tidak polos."""
    img = Image.new("RGB", (w, h), color)
    px = img.load()
    for y in range(0, h, 7):
        for x in range(0, w, 7):
            px[x, y] = ((x * 255 // max(w, 1)) % 256,
                        (y * 255 // max(h, 1)) % 256, 128)
    img.save(path, "JPEG", quality=92)
    return path


def make_photo_with_exif(path, w, h, lat, lon, dt):
    make_photo(path, w, h)
    tmp = path + ".tmp.jpg"
    core.save_image_with_exif(path, tmp, new_datetime=dt,
                              new_lat=lat, new_lon=lon)
    os.replace(tmp, path)
    return path


def test_fit_size():
    print("\n== fit_size ==")
    # Landscape 4000x3000 ke tiap preset (fit).
    for name, (tw, th) in core.PRESETS.items():
        rw, rh = core.fit_size(4000, 3000, tw, th, "fit", True)
        check("fit %s muat target" % name, rw <= tw and rh <= th,
              "%dx%d -> %dx%d (target %dx%d)" % (4000, 3000, rw, rh, tw, th))
        check("fit %s aspek benar" % name,
              abs(rw / rh - 4000 / 3000) < 0.02, "")
    # Portrait 3000x4000 ke Large.
    rw, rh = core.fit_size(3000, 4000, 1920, 1080, "fit", True)
    check("fit portrait Large", rw <= 1920 and rh <= 1080
          and abs(rw / rh - 0.75) < 0.02, "%dx%d" % (rw, rh))
    # Gambar kecil tidak diperbesar bila smaller_only ON.
    check("kecil tidak diperbesar (ON)",
          core.fit_size(100, 80, 854, 480, "fit", True) == (100, 80), "")
    # ...tapi diperbesar bila OFF.
    check("kecil diperbesar (OFF)",
          core.fit_size(100, 80, 854, 480, "fit", False) == (600, 480), "")
    # Fill menutupi target.
    rw, rh = core.fit_size(4000, 3000, 854, 480, "fill", True)
    check("fill menutupi target", rw >= 854 and rh >= 480, "%dx%d" % (rw, rh))
    # Stretch tepat target.
    check("stretch tepat target",
          core.fit_size(4000, 3000, 854, 480, "stretch", True) == (854, 480),
          "")


def test_resize_file():
    print("\n== resize_image_file ==")
    src = make_photo(os.path.join(WORK, "foto4000.jpg"), 4000, 3000)
    for name, (tw, th) in core.PRESETS.items():
        dst = core.output_path_for_resize(src, name)
        w, h, fmt = core.resize_image_file(src, dst, tw, th, "fit", True)
        check("resize %s dimensi" % name, w <= tw and h <= th
              and abs(w / h - 4 / 3) < 0.02, "%dx%d" % (w, h))
        check("resize %s nama file" % name,
              os.path.basename(dst) == "foto4000 (%s).jpg" % name, dst)
        check("resize %s file ada" % name,
              os.path.exists(dst) and os.path.getsize(dst) > 1000, "")
    # Custom 1024x640 seperti screenshot.
    dst = core.output_path_for_resize(src, "Custom")
    w, h, _ = core.resize_image_file(src, dst, 1024, 640, "fit", True)
    check("resize Custom 1024x640", (w, h) == (853, 640), "%dx%d" % (w, h))
    # Overwrite kecil: gambar 100x80 ke Small tetap 100x80 (smaller_only).
    small = make_photo(os.path.join(WORK, "kecil.jpg"), 100, 80)
    dst2 = os.path.join(WORK, "kecil (Small).jpg")
    w, h, _ = core.resize_image_file(small, dst2, 854, 480, "fit", True)
    check("kecil tetap 100x80", (w, h) == (100, 80), "%dx%d" % (w, h))
    # PNG output.
    dst3 = core.output_path_for_resize(src, "Small", ".png")
    w, h, fmt = core.resize_image_file(src, dst3, 854, 480, "fit", True,
                                       out_format="PNG")
    check("resize ke PNG", fmt == "PNG" and dst3.endswith(".png"), fmt)


def test_pdf_roundtrip():
    print("\n== images -> PDF -> images ==")
    imgs = [make_photo(os.path.join(WORK, "p%d.jpg" % i), 1200, 900)
            for i in (1, 2, 3)]
    pdf = os.path.join(WORK, "gabung.pdf")
    n = core.images_to_pdf(imgs, pdf)
    check("images_to_pdf 3 halaman", n == 3, "n=%d" % n)
    check("pdf_page_count", core.pdf_page_count(pdf) == 3, "")
    made = core.pdf_to_images(pdf, WORK, "gabung", 800, fmt="PNG")
    check("pdf_to_images 3 file", len(made) == 3, str(made))
    for m in made:
        with Image.open(m) as im:
            check("pdf_to_images sisi terpanjang 800: %s" % os.path.basename(m),
                  max(im.width, im.height) == 800, "%dx%d" % im.size)
    # JPG output juga.
    made_jpg = core.pdf_to_images(pdf, WORK, "gabung", 400, fmt="JPG")
    check("pdf_to_images JPG", len(made_jpg) == 3
          and all(p.endswith(".jpg") for p in made_jpg), "")


def test_resize_pdf():
    print("\n== resize_pdf ==")
    import pymupdf
    src = os.path.join(WORK, "a4.pdf")
    doc = pymupdf.open()
    page = doc.new_page(width=842, height=595)  # A4 landscape (point)
    page.insert_text((100, 100), "Halo ConvTool", fontsize=40)
    doc.save(src)
    doc.close()
    # Target Small 854x480 px -> 640.5 x 360 pt.
    dst = core.output_path_for_resize(src, "Small", ".pdf")
    n = core.resize_pdf(src, dst, 854, 480)
    check("resize_pdf 1 halaman", n == 1, "")
    d2 = pymupdf.open(dst)
    r = d2[0].rect
    d2.close()
    check("resize_pdf ukuran halaman = target",
          abs(r.width - 640.5) < 0.6 and abs(r.height - 360) < 0.6,
          "%.1f x %.1f pt" % (r.width, r.height))
    check("resize_pdf nama file",
          os.path.basename(dst) == "a4 (Small).pdf", dst)


def test_exif_roundtrip():
    print("\n== EXIF round-trip ==")
    p = make_photo_with_exif(
        os.path.join(WORK, "exif.jpg"), 1600, 1200,
        -7.276971, 112.747416, datetime(2026, 11, 11, 10, 30, 0))
    # Tambah Make/Model lalu baca.
    im = Image.open(p)
    ex = im.getexif()
    ex[271] = "Samsung"
    ex[272] = "SM-A525F"
    im.save(p, "JPEG", exif=ex, quality=95)
    r = core.read_exif(p)
    check("exif datetime", r["datetime"] == "2026:11:11 10:30:00",
          str(r["datetime"]))
    check("exif lat", r["lat"] is not None and abs(r["lat"] + 7.276971) < 1e-5,
          str(r["lat"]))
    check("exif lon", r["lon"] is not None and abs(r["lon"] - 112.747416) < 1e-5,
          str(r["lon"]))
    check("exif make/model", r["make"] == "Samsung"
          and r["model"] == "SM-A525F", "%s %s" % (r["make"], r["model"]))
    # Edit: ubah datetime + GPS, pastikan make/model tetap.
    dst = os.path.join(WORK, "exif_exifedit.jpg")
    core.save_image_with_exif(p, dst, new_datetime=datetime(2026, 11, 12, 8, 15, 0),
                              new_lat=-7.3, new_lon=112.8)
    r2 = core.read_exif(dst)
    check("exif edit datetime", r2["datetime"] == "2026:11:12 08:15:00",
          str(r2["datetime"]))
    check("exif edit lat/lon",
          abs(r2["lat"] + 7.3) < 1e-5 and abs(r2["lon"] - 112.8) < 1e-5,
          "%s %s" % (r2["lat"], r2["lon"]))
    check("exif edit preserve make", r2["make"] == "Samsung",
          str(r2["make"]))
    # Tanpa GPS -> (None, None).
    plain = make_photo(os.path.join(WORK, "plain.jpg"), 800, 600)
    r3 = core.read_exif(plain)
    check("exif tanpa GPS", r3["lat"] is None and r3["lon"] is None, "")


def test_formats():
    print("\n== format teks ==")
    dt = datetime(2026, 9, 24, 9, 22)
    check("format_classic_date",
          watermark.format_classic_date(dt).startswith("Kamis, 24/09/2026 09:22 GMT "),
          watermark.format_classic_date(dt))
    check("format_job_date",
          watermark.format_job_date(datetime(2026, 11, 2, 7, 23))
          == "2026-11-02(Sen)  07:23(AM)",
          watermark.format_job_date(datetime(2026, 11, 2, 7, 23)))
    check("latlng_line",
          watermark.latlng_line(-7.276971, 112.747416)
          == "Lat -7.276971° Long 112.747416°",
          watermark.latlng_line(-7.276971, 112.747416))


def test_place_from_address():
    print("\n== nama Tempat dari Nominatim ==")
    sidosermo = {"office": "Kantor Kelurahan Sidosermo",
                 "road": "Jalan Sidosermo PDK IV",
                 "neighbourhood": "RW 07",
                 "village": "Sidosermo", "municipality": "Wonocolo",
                 "city": "Surabaya", "state": "Jawa Timur",
                 "postcode": "60239", "country": "Indonesia"}
    check("place Wonocolo",
          core.place_from_address(sidosermo)
          == "Kecamatan Wonocolo, Jawa Timur, Indonesia",
          str(core.place_from_address(sidosermo)))
    ngagel = {"village": "Ngagel", "municipality": "Wonokromo",
              "city": "Surabaya", "state": "Jawa Timur",
              "country": "Indonesia"}
    check("place Wonokromo",
          core.place_from_address(ngagel)
          == "Kecamatan Wonokromo, Jawa Timur, Indonesia",
          str(core.place_from_address(ngagel)))
    check("place tanpa kecamatan",
          core.place_from_address({"village": "Sidosermo",
                                   "state": "Jawa Timur"}) is None,
          str(core.place_from_address({"village": "Sidosermo",
                                       "state": "Jawa Timur"})))
    check("place sudah berawalan Kecamatan",
          core.place_from_address({"municipality": "Kecamatan Wonocolo",
                                   "state": "Jawa Timur",
                                   "country": "Indonesia"})
          == "Kecamatan Wonocolo, Jawa Timur, Indonesia",
          str(core.place_from_address(
              {"municipality": "Kecamatan Wonocolo",
               "state": "Jawa Timur", "country": "Indonesia"})))


def test_map_tiles():
    print("\n== tile peta (butuh internet; sketsa bila offline) ==")
    img, drawn = core.stitch_map(-7.276971, 112.747416, 400, 300, "road")
    check("stitch_map road ukuran", img.size == (400, 300), str(img.size))
    print("      tile jalan asli terunduh: %s (False = sketsa/offline)" % drawn)
    img2, drawn2 = core.stitch_map(-7.276971, 112.747416, 400, 300, "sat")
    check("stitch_map sat ukuran", img2.size == (400, 300), str(img2.size))
    print("      tile satelit asli terunduh: %s (False = sketsa/offline)" % drawn2)


def test_watermark():
    print("\n== watermark Klasik & Job ==")
    src = make_photo_with_exif(
        os.path.join(WORK, "wm_src.jpg"), 1600, 1200,
        -7.276971, 112.747416, datetime(2026, 11, 11, 10, 30, 0))
    addr = ("Jl. Sidosermo II No. 12, Sidosermo, Wonocolo, "
            "Surabaya, Jawa Timur 60239, Indonesia")
    place = "Kecamatan Wonocolo, Jawa Timur, Indonesia"
    dt = datetime(2026, 11, 11, 10, 30, 0)
    for style in ("klasik", "job"):
        dst = watermark.watermark_output_path(src, style)
        watermark.apply_watermark(src, dst, style, -7.276971, 112.747416,
                                  dt, addr, place=place)
        check("watermark %s file ada" % style,
              os.path.exists(dst) and os.path.getsize(dst) > 10000,
              "%d byte" % os.path.getsize(dst) if os.path.exists(dst) else "")
        with Image.open(dst) as im:
            check("watermark %s ukuran tetap 1600x1200" % style,
                  im.size == (1600, 1200), str(im.size))
            if style == "job":
                # Strip Job HARUS abu-abu padat #7d7d7d (bukan
                # transparan): sampel titik di strip yang jauh dari
                # teks/peta/cuaca (x=1000, y=950; toleransi JPEG).
                px = im.convert("RGB").getpixel((1000, 950))
                check("watermark job strip padat #7d7d7d",
                      all(abs(c - 125) <= 6 for c in px), str(px))
        r = core.read_exif(dst)
        check("watermark %s EXIF GPS dipertahankan" % style,
              r["lat"] is not None and abs(r["lat"] + 7.276971) < 1e-5,
              str(r["lat"]))
        check("watermark %s EXIF datetime dipertahankan" % style,
              r["datetime"] == "2026:11:11 10:30:00", str(r["datetime"]))
        check("watermark %s nama file" % style,
              os.path.basename(dst) == "wm_src_%s.jpg" % style, dst)
    # Render langsung (tanpa file) untuk cek tidak crash dengan alamat kosong.
    img = Image.open(src)
    out = watermark.render_klasik(img, -7.276971, 112.747416, dt, "")
    check("render_klasik alamat kosong", out.size == (1600, 1200), "")
    out2 = watermark.render_job(img, -7.276971, 112.747416, dt, "")
    check("render_job alamat kosong", out2.size == (1600, 1200), "")
    # Job tanpa cuaca + Klasik dengan baris cuaca + skala 70%.
    out3 = watermark.render_job(img, -7.276971, 112.747416, dt, addr,
                                place=place, show_weather=False)
    check("render_job tanpa cuaca", out3.size == (1600, 1200), "")
    out4 = watermark.render_klasik(img, -7.276971, 112.747416, dt, addr,
                                   place=place, weather_text="Cerah 31°C",
                                   s=0.7)
    check("render_klasik cuaca + skala 70%", out4.size == (1600, 1200), "")
    # Ikon cuaca keempat kondisi tidak crash.
    for kind in ("sunny", "partly", "cloudy", "rain"):
        layer = Image.new("RGBA", (400, 300), (0, 0, 0, 0))
        core.draw_weather(layer, kind, 200, 150, 150)
    check("draw_weather 4 kondisi", True, "")


def test_pickers_parse():
    print("\n== pickers_parse ==")
    import pickers
    check("parse_date valid",
          pickers.parse_date_str("2026-11-10") is not None, "")
    check("parse_date invalid",
          pickers.parse_date_str("2026-13-40") is None, "")
    check("parse_date kosong", pickers.parse_date_str("") is None, "")
    check("parse_time valid",
          pickers.parse_time_str("10:17") == (10, 17), "")
    check("parse_time 25:00 invalid",
          pickers.parse_time_str("25:00") is None, "")
    check("parse_time 10:60 invalid",
          pickers.parse_time_str("10:60") is None, "")


def test_map_pixel_roundtrip():
    print("\n== map_pixel_roundtrip ==")
    lat0, lon0 = -7.310251, 112.754608
    for (w, h) in ((360, 240), (800, 600)):
        lat, lon = core.map_pixel_to_latlon(lat0, lon0, w, h,
                                            w / 2.0, h / 2.0)
        check("map_pixel tengah (%dx%d)" % (w, h),
              abs(lat - lat0) < 1e-6 and abs(lon - lon0) < 1e-6, "")
        lat2, lon2 = core.map_pixel_to_latlon(lat0, lon0, w, h,
                                              w / 2.0 + 100, h / 2.0 + 100)
        check("map_pixel pojok (%dx%d)" % (w, h),
              lat2 < lat0 and lon2 > lon0
              and abs(lat2 - lat0) < 0.05 and abs(lon2 - lon0) < 0.05,
              "%.6f,%.6f" % (lat2, lon2))


def test_exif_extra_tags():
    print("\n== exif_extra_tags ==")
    src = make_photo(os.path.join(WORK, "tags.jpg"), 800, 600)
    dst = os.path.join(WORK, "tags_exifedit.jpg")
    core.save_image_with_exif(
        src, dst, extra_tags={"Make": "samsung", "Model": "SM-A525F",
                              "ImageDescription": "Ground Check",
                              "XResolution": "72"})
    info = core.read_exif(dst)
    check("extra Make", info["make"] == "samsung", "")
    check("extra Model", info["model"] == "SM-A525F", "")
    tags = dict(info["tags"])
    check("extra ImageDescription",
          tags.get("ImageDescription") == "Ground Check", "")
    check("extra XResolution", tags.get("XResolution", "").startswith("72"),
          tags.get("XResolution", ""))
    # Tag tak dikenal / Orientation diabaikan, tidak crash.
    dst2 = os.path.join(WORK, "tags2_exifedit.jpg")
    core.save_image_with_exif(src, dst2, extra_tags={"Orientation": "6",
                                                     "TidakAda": "x"})
    info2 = core.read_exif(dst2)
    tags2 = dict(info2["tags"])
    check("Orientation tetap 1", tags2.get("Orientation") in ("1", 1),
          str(tags2.get("Orientation")))


def test_images_to_pdf_options():
    print("\n== images_to_pdf_options ==")
    import pymupdf
    a = make_photo(os.path.join(WORK, "pdf_a.jpg"), 1600, 1200)
    b = make_photo(os.path.join(WORK, "pdf_b.jpg"), 800, 1200)
    out = os.path.join(WORK, "opt_a4.pdf")
    n = core.images_to_pdf([a, b], out)
    doc = pymupdf.open(out)
    check("pdf default A4 portrait", n == 2 and len(doc) == 2
          and abs(doc[0].rect.width - 595.0) < 1
          and abs(doc[0].rect.height - 842.0) < 1, "")
    doc.close()
    out0 = os.path.join(WORK, "opt_a4_1.pdf")
    core.images_to_pdf([a], out0)
    out2 = os.path.join(WORK, "opt_folio_land.pdf")
    n2 = core.images_to_pdf([a], out2, page_size="Folio",
                            orientation="landscape")
    doc = pymupdf.open(out2)
    check("pdf Folio landscape", n2 == 1
          and abs(doc[0].rect.width - 935.43) < 1
          and abs(doc[0].rect.height - 609.45) < 1, "")
    doc.close()
    out3 = os.path.join(WORK, "opt_fill.pdf")
    n3 = core.images_to_pdf([a], out3, fill=True)
    doc = pymupdf.open(out3)
    check("pdf fill", n3 == 1 and len(doc) == 1, "")
    doc.close()
    out4 = os.path.join(WORK, "opt_small.pdf")
    n4 = core.images_to_pdf([a], out4, resize="Small")
    check("pdf resize Small", n4 == 1
          and os.path.getsize(out4) < os.path.getsize(out0),
          "%d < %d" % (os.path.getsize(out4), os.path.getsize(out0)))
    out5 = os.path.join(WORK, "opt_fill_small.pdf")
    n5 = core.images_to_pdf([a, b], out5, page_size="A5",
                            orientation="landscape", fill=True,
                            resize="Small")
    check("pdf A5 landscape fill Small", n5 == 2, "")


def test_fit_within():
    print("\n== fit_within ==")
    check("fit landscape ke kolom sempit",
          core.fit_within(4000, 3000, 418, 480) == (418, 313), "")
    check("fit portrait ke kolom sempit",
          core.fit_within(3000, 4000, 418, 480) == (360, 480), "")
    check("fit tidak pernah memperbesar",
          core.fit_within(200, 100, 418, 480) == (200, 100), "")
    check("fit bujur sangkar",
          core.fit_within(1000, 1000, 418, 480) == (418, 418), "")


def test_preview_downscale():
    print("\n== preview_downscale ==")
    # Pratinjau dirender dari salinan kecil (maks 1200 px), bukan
    # full 4000x3000 — layout proporsional sama, jauh lebih cepat.
    img = Image.new("RGB", (4000, 3000), (40, 120, 200))
    img.thumbnail((1200, 1200))
    check("downscale 4000x3000 -> 1200x900", img.size == (1200, 900), "")
    out = watermark.render_klasik(
        img, -7.310251, 112.754608, datetime(2026, 11, 10, 10, 17),
        "Jalan Sidosermo IV Gang 11, Sidosermo, Wonocolo",
        place="Kecamatan Wonocolo, Jawa Timur, Indonesia", s=1.0)
    check("render pratinjau kecil", out.size == (1200, 900), "")
    tw, th = core.fit_within(out.width, out.height, 418, 480)
    check("pratinjau muat di kolom", (tw, th) == (418, 313), "")


def main():
    if os.path.exists(WORK):
        shutil.rmtree(WORK)
    os.makedirs(WORK)
    test_fit_size()
    test_resize_file()
    test_pdf_roundtrip()
    test_resize_pdf()
    test_exif_roundtrip()
    test_formats()
    test_place_from_address()
    test_map_tiles()
    test_watermark()
    test_pickers_parse()
    test_map_pixel_roundtrip()
    test_exif_extra_tags()
    test_images_to_pdf_options()
    test_fit_within()
    test_preview_downscale()
    print("\n==================================")
    print("LOLOS: %d   GAGAL: %d" % (PASSES[0], len(FAILURES)))
    if FAILURES:
        print("Yang gagal:", ", ".join(FAILURES))
        return 1
    print("SEMUA UJI LOLOS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
