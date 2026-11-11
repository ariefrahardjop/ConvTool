# watermark.py — Render watermark Klasik & Job Timestamp (Pillow).
#
# Geometri & teks mengikuti aplikasi web Stempel Foto GPS Web
# (~/workspace/ts-spaces/stempel-foto-gps-web/index.html,
# fungsi drawClassic / drawJob + drawMap / drawPin / drawGoogle /
# drawFlagID / drawWeather) — BUKAN Galeriku (ada perbedaan:
# Galeriku memakai koma desimal & strip Job transparan, sedangkan
# aplikasi web memakai titik desimal & strip Job padat).
#
# KLASIK:
#   kartu gelap translusen lebar 83% W terpusat (margin 8,5% tiap sisi),
#   margin bawah 5% W; peta satelit Esri zoom 17 persegi 18,8% W di kiri;
#   pill "GPS Map Camera" menyatu di kanan atas kartu; judul tempat +
#   bendera Indonesia; alamat maks 3 baris; "Lat x° Long y°" (TITIK
#   desimal, 6 angka); tanggal "Kamis, 24/09/2026 09:22 GMT +07:00";
#   baris cuaca opsional di bawah tanggal.
# JOB (Job Timestamp):
#   strip abu-abu PADAT #7d7d7d selebar foto di bawah foto
#   (ukuran foto TIDAK bertambah); peta jalan OSM zoom 15 lebar 25% W;
#   alamat 1 baris; tempat maks 3 baris besar rata tengah; Lat/Long;
#   tanggal "2026-11-02(Sen) 07:23(AM)"; cuaca di kanan strip
#   (ikon + suhu C/F, default Berawan 28 C, seperti aplikasi web).
#   TANPA field Nama Pekerjaan/Catatan/Altitude/Akurasi.
#
# Data (GPS + tanggal/jam + alamat) diambil dari EXIF foto bila ada;
# bila GPS tidak ada, pemanggil wajib mengisi lat/lon manual dulu.
# Output: file BARU (_klasik / _job), GPS + DateTimeOriginal asli
# dipertahankan, orientasi diterapkan (hasil selalu tegak).

import os
from datetime import datetime

from PIL import Image, ImageDraw, ImageFont, ImageOps

import core

DAY_ID = ["Minggu", "Senin", "Selasa", "Rabu", "Kamis", "Jumat", "Sabtu"]
DAY_AB = ["Min", "Sen", "Sel", "Rab", "Kam", "Jum", "Sab"]

# Warna kartu Klasik: rgba(15, 15, 15, 148) — sama seperti aplikasi web.
KLASIK_CARD = (15, 15, 15, 148)
JOB_STRIP_RGB = (125, 125, 125)


# ---------------------------------------------------------------- format teks


def gmt_label(dt):
    """'GMT +07:00' dari offset zona waktu lokal pada tanggal itu."""
    off = dt.astimezone().utcoffset()
    total_min = int(off.total_seconds() // 60) if off is not None else 0
    sign = "+" if total_min >= 0 else "-"
    a = abs(total_min)
    return "GMT %s%02d:%02d" % (sign, a // 60, a % 60)


def format_classic_date(dt):
    """'Kamis, 24/09/2026 09:22 GMT +07:00'."""
    dow = (dt.weekday() + 1) % 7  # Senin=0 -> Minggu=0
    return "%s, %02d/%02d/%04d %02d:%02d %s" % (
        DAY_ID[dow], dt.day, dt.month, dt.year,
        dt.hour, dt.minute, gmt_label(dt))


def format_job_date(dt):
    """'2026-11-02(Sen) 07:23(AM)' — jam 12-jam + AM/PM."""
    dow = (dt.weekday() + 1) % 7
    h12 = dt.hour % 12
    if h12 == 0:
        h12 = 12
    return "%04d-%02d-%02d(%s)  %02d:%02d(%s)" % (
        dt.year, dt.month, dt.day, DAY_AB[dow],
        h12, dt.minute, "AM" if dt.hour < 12 else "PM")


def latlng_line(lat, lon):
    """'Lat -7.276971° Long 112.747416°' — 6 desimal, TITIK desimal,
    sama seperti aplikasi web Stempel (toFixed(6))."""
    return "Lat %.6f° Long %.6f°" % (lat, lon)


def _split_place(address):
    """Pecah alamat jadi bagian-bagian (pisah koma), maks 3, untuk
    baris tengah Job / judul Klasik."""
    parts = [p.strip() for p in (address or "").split(",")]
    return [p for p in parts if p][:3]


# ---------------------------------------------------------------- helper gambar


def _rounded_rect(draw, box, radius, fill=None, outline=None, width=1):
    draw.rounded_rectangle(box, radius=radius, fill=fill,
                           outline=outline, width=width)


def _wrap_text(draw, text, font, max_w, max_lines):
    """Bagi teks jadi maks max_lines baris selebar max_w (ellipsis
    di baris akhir)."""
    words = text.split()
    lines = []
    cur = ""
    for w in words:
        test = w if not cur else cur + " " + w
        if draw.textlength(test, font=font) > max_w and cur:
            lines.append(cur)
            cur = w
            if len(lines) == max_lines:
                break
        else:
            cur = test
    else:
        if cur:
            lines.append(cur)
    if len(lines) == max_lines and cur and lines[-1] != cur:
        # Ellipsis di baris terakhir bila masih ada sisa kata.
        last = lines[-1]
        while last and draw.textlength(last + "...", font=font) > max_w:
            last = last.rsplit(" ", 1)[0] if " " in last else last[:-1]
        lines[-1] = last + "..."
    return lines[:max_lines]


def _fit_font_size(draw, text, start_size, max_w, bold=False, min_size=6):
    """Perkecil ukuran font sampai teks muat dalam max_w."""
    size = start_size
    while size > min_size:
        font = core.load_font(size, bold)
        if draw.textlength(text, font=font) <= max_w:
            return font
        size -= 1
    return core.load_font(min_size, bold)


def _make_flag(w, h):
    """Bendera Indonesia (gambar RGBA) seperti drawFlagID aplikasi web:
    merah #e70011 di atas, putih di bawah, sudut membulat,
    kilau gradien horizontal (gelap di tepi, terang di tengah),
    garis tepi tipis."""
    w, h = int(max(2, round(w))), int(max(2, round(h)))
    mask = Image.new("L", (w, h), 0)
    ImageDraw.Draw(mask).rounded_rectangle(
        [0, 0, w, h], radius=h * 0.14, fill=255)
    body = Image.new("RGBA", (w, h), (255, 255, 255, 255))
    d = ImageDraw.Draw(body)
    d.rectangle([0, 0, w, h / 2], fill=(231, 0, 17, 255))
    sheen = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    sd = ImageDraw.Draw(sheen)
    for xx in range(w):
        t = xx / max(1, w - 1)
        if t <= 0.5:
            u = t / 0.5
            col = tuple(int(round(0 + (255 - 0) * u)) for _ in range(3))
            a = int(round(36 + (26 - 36) * u))
        else:
            u = (t - 0.5) / 0.5
            col = tuple(int(round(255 + (0 - 255) * u)) for _ in range(3))
            a = int(round(26 + (36 - 26) * u))
        sd.line([(xx, 0), (xx, h)], fill=col + (a,))
    body = Image.alpha_composite(body, sheen)
    body.putalpha(mask)
    out = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    out.paste(body, (0, 0), body)
    od = ImageDraw.Draw(out)
    od.rounded_rectangle([0, 0, w, h], radius=h * 0.14,
                         outline=(0, 0, 0, 77),
                         width=max(1, int(round(h * 0.05))))
    return out


def _icon_path():
    """Ikon GPS Map Camera yang dibundel (copot dari aset Stempel Web).
    Dicari di folder bundle PyInstaller (sys._MEIPASS), lalu di sebelah
    file ini (assets/), lalu di folder kerja."""
    import sys
    bases = []
    meipass = getattr(sys, "_MEIPASS", None)
    if meipass:
        bases.append(os.path.join(meipass, "assets"))
    here = os.path.dirname(os.path.abspath(__file__))
    bases.append(os.path.join(here, "assets"))
    bases.append(here)
    for base in bases:
        cand = os.path.join(base, "gps-map-camera-icon.png")
        if os.path.exists(cand):
            return cand
    return None


def _draw_pill_icon(draw, img, x, y, size):
    """Ikon kecil di pill 'GPS Map Camera': pakai file ikon bila ada,
    kalau tidak gambar lensa kamera sederhana."""
    path = _icon_path()
    if path:
        try:
            icon = Image.open(path).convert("RGBA")
            icon = icon.resize((int(size), int(size)), Image.LANCZOS)
            img.paste(icon, (int(x), int(y)), icon)
            return
        except Exception:
            pass
    # Fallback: kotak bulat + lensa.
    r = size / 2
    draw.rounded_rectangle([x, y, x + size, y + size], radius=size * 0.2,
                           fill=(66, 133, 244, 255))
    draw.ellipse([x + size * 0.28, y + size * 0.28,
                  x + size * 0.72, y + size * 0.72],
                 fill=(255, 255, 255, 255))
    draw.ellipse([x + size * 0.38, y + size * 0.38,
                  x + size * 0.62, y + size * 0.62],
                 fill=(66, 133, 244, 255))


# ---------------------------------------------------------------- Klasik


def render_klasik(img, lat, lon, dt, address, place="",
                  weather_text="", s=1.0):
    """Render watermark Klasik di atas PIL Image (RGB). Mengembalikan
    gambar baru (ukuran sama).
    place: judul tempat (bila kosong, dipakai bagian pertama alamat).
    weather_text: baris cuaca opsional di bawah tanggal (boleh '').
    s: skala stempel 1.0 = 100% (seperti slider aplikasi web)."""
    out = img.convert("RGB")
    W, H = out.size
    margin = W * 0.085
    bottom_margin = W * 0.05
    title_s = W * 0.0223 * s
    body_s = W * 0.0155 * s
    small_s = W * 0.0155 * s
    line_gap = 1.38

    show_map = True
    map_w = W * 0.188 if show_map else 0
    gap = W * 0.016 if show_map else 0
    card_x = margin + map_w + gap
    card_w = W - margin - card_x
    pad_in = W * 0.014
    text_w = card_w - pad_in * 2

    place = (place or "").strip()
    if not place:
        place_parts = _split_place(address)
        place = place_parts[0] if place_parts else ""

    # Susun baris teks (ukuran, teks, apakah judul).
    tmp = Image.new("RGB", (10, 10))
    tdraw = ImageDraw.Draw(tmp)
    lines = []  # (teks, ukuran, judul?)
    if place:
        lines.append((place, title_s, True))
    if address:
        body_font = core.load_font(body_s)
        for wl in _wrap_text(tdraw, address, body_font, text_w, 3):
            lines.append((wl, body_s, False))
    lines.append((latlng_line(lat, lon), small_s, False))
    lines.append((format_classic_date(dt), body_s, False))
    if (weather_text or "").strip():
        lines.append((weather_text.strip(), small_s, False))

    text_h = sum(sz * line_gap for (_, sz, _) in lines)
    content_h = text_h + pad_in * 1.25
    map_h = map_w
    card_h = max(map_h, content_h)
    card_y = H - bottom_margin - card_h
    radius = W * 0.009

    # Lapisan overlay untuk kartu translusen + pill.
    overlay = Image.new("RGBA", out.size, (0, 0, 0, 0))
    odraw = ImageDraw.Draw(overlay)
    _rounded_rect(odraw, [card_x, card_y, card_x + card_w, card_y + card_h],
                  radius, fill=KLASIK_CARD)

    # Pill "GPS Map Camera" menyatu di kanan atas kartu.
    pill_fs = W * 0.0144 * s
    pill_font = core.load_font(pill_fs)
    pill_icon_s = pill_fs * 1.5
    pill_w = (pill_icon_s + pill_fs * 0.55
              + tdraw.textlength("GPS Map Camera", font=pill_font)
              + W * 0.014)
    pill_h = pill_icon_s + W * 0.009
    pill_x = W - margin - pill_w
    pill_y = card_y - pill_h
    # Pill: sudut atas membulat, bawah lurus masuk ke kartu.
    odraw.rounded_rectangle([pill_x, pill_y, pill_x + pill_w,
                             pill_y + pill_h + radius],
                            radius=min(radius, pill_w / 2), fill=KLASIK_CARD)
    odraw.rectangle([pill_x, pill_y + pill_h,
                     pill_x + pill_w, pill_y + pill_h + radius],
                    fill=KLASIK_CARD)
    # Bayangan lembut di bawah kartu+pil (seperti aplikasi web):
    # siluet overlay dihitamkan, digeser sedikit ke bawah, di-blur.
    from PIL import ImageFilter
    shadow = Image.new("RGBA", out.size, (0, 0, 0, 0))
    shadow.paste(Image.new("RGBA", out.size, (0, 0, 0, 115)),
                 (0, int(round(W * 0.0025))), overlay.split()[3])
    shadow = shadow.filter(ImageFilter.GaussianBlur(
        radius=max(1.0, W * 0.004)))
    out = Image.alpha_composite(out.convert("RGBA"), shadow)
    out = Image.alpha_composite(out, overlay)

    draw = ImageDraw.Draw(out, "RGBA")
    _draw_pill_icon(draw, out, pill_x + W * 0.006,
                    pill_y + (pill_h - pill_icon_s) / 2, pill_icon_s)
    draw.text((pill_x + W * 0.006 + pill_icon_s + pill_fs * 0.55,
               pill_y + pill_h / 2 + pill_fs * 0.35),
              "GPS Map Camera", font=pill_font, fill=(255, 255, 255, 255),
              anchor="ls")

    # Peta satelit di kiri kartu.
    if show_map:
        map_img, _ = core.stitch_map(lat, lon, int(map_w), int(map_h), "sat")
        mask = Image.new("L", (int(map_w), int(map_h)), 0)
        mdraw = ImageDraw.Draw(mask)
        mdraw.rounded_rectangle([0, 0, int(map_w), int(map_h)],
                                radius=min(12, map_w * 0.05), fill=255)
        out.paste(map_img, (int(margin), int(card_y + card_h - map_h)), mask)
        # Garis tepi peta (seperti aplikasi web).
        draw = ImageDraw.Draw(out, "RGBA")
        draw.rounded_rectangle(
            [int(margin), int(card_y + card_h - map_h),
             int(margin + map_w), int(card_y + card_h)],
            radius=min(12, map_w * 0.05),
            outline=(0, 0, 0, 70), width=2)

    # Teks di dalam kartu.
    draw = ImageDraw.Draw(out, "RGBA")
    ty = card_y + pad_in * 0.55 + (card_h - content_h) / 2
    for (text, sz, is_title) in lines:
        font = core.load_font(sz, bold=is_title)
        ty += sz
        draw.text((card_x + pad_in, ty), text, font=font,
                  fill=(255, 255, 255, 255), anchor="ls")
        if is_title:
            tw = draw.textlength(text, font=font)
            fh, fw = sz * 0.62, sz * 0.62 * 1.5
            if card_x + pad_in + tw + fw + pad_in <= card_x + card_w:
                flag = _make_flag(fw, fh)
                out.paste(flag,
                          (int(card_x + pad_in + tw + sz * 0.35),
                           int(ty - sz * 0.78)),
                          flag)
        ty += sz * (line_gap - 1)
    return out.convert("RGB")


# ---------------------------------------------------------------- Job


def render_job(img, lat, lon, dt, address, place="", temp_c=28,
               cond="cloudy", show_weather=True, s=1.0):
    """Render watermark Job Timestamp di atas PIL Image (RGB).
    Strip abu-abu PADAT #7d7d7d sebagai overlay di bawah foto
    (ukuran foto TIDAK bertambah) — seperti aplikasi web.
    place: baris tengah (bila kosong, dipakai bagian alamat).
    temp_c/cond/show_weather: cuaca di kanan strip (default aplikasi
    web: Berawan 28 C, tampil). s: skala stempel 1.0 = 100%."""
    out = img.convert("RGB")
    W, H = out.size
    map_w = W * 0.25
    big_s = W * 0.0235 * s
    small_s = W * 0.0108 * s
    date_s = W * 0.02 * s
    temp_s = W * 0.0235 * s
    coord_s = W * 0.0135 * s
    line_gap = 1.28
    panel_x = map_w
    panel_w = W - map_w
    weather_w = W * 0.135 if show_weather else W * 0.02
    center_w = panel_w - weather_w - W * 0.015

    place = (place or "").strip()
    parts = _split_place(place) if place else _split_place(address)
    if not parts and address:
        parts = [address.strip()]
    mid_lines = parts[:3]

    content_h = (small_s * 1.7 + len(mid_lines) * big_s * line_gap
                 + coord_s * 1.5 + date_s * 1.55)
    bar_h = max(content_h, W * 0.155 * s)
    y0 = H - bar_h

    # Strip abu-abu PADAT (aplikasi web memakai #7d7d7d solid).
    draw = ImageDraw.Draw(out)
    draw.rectangle([panel_x, y0, panel_x + panel_w, y0 + bar_h],
                   fill=JOB_STRIP_RGB)

    # Peta jalan di kiri strip (opak, tidak diredupkan).
    map_img, _ = core.stitch_map(lat, lon, int(map_w), int(bar_h), "road")
    mask = Image.new("L", (int(map_w), int(bar_h)), 0)
    mdraw = ImageDraw.Draw(mask)
    mdraw.rounded_rectangle([0, 0, int(map_w), int(bar_h)],
                            radius=min(12, map_w * 0.05), fill=255)
    out.paste(map_img, (0, int(y0)), mask)
    draw = ImageDraw.Draw(out, "RGBA")
    draw.rounded_rectangle([0, int(y0), int(map_w), int(y0 + bar_h)],
                           radius=min(12, map_w * 0.05),
                           outline=(0, 0, 0, 70), width=2)

    # Alamat 1 baris di atas strip.
    if address:
        max_w = panel_w - W * 0.03 - (weather_w * 0.55 if show_weather else 0)
        addr_font = _fit_font_size(draw, address, small_s, max_w)
        draw.text((panel_x + W * 0.026, y0 + small_s * 1.55), address,
                  font=addr_font, fill=(255, 255, 255, 255), anchor="ls")
    ty = y0 + small_s * 1.7 + (bar_h - content_h) / 2
    for t in mid_lines:
        font = _fit_font_size(draw, t, big_s, center_w)
        fs = font.size
        w2 = draw.textlength(t, font=font)
        ty += fs
        draw.text((panel_x + (center_w - w2) / 2 + W * 0.008, ty), t,
                  font=font, fill=(255, 255, 255, 255), anchor="ls")
        ty += fs * (line_gap - 1)
    coord = latlng_line(lat, lon)
    font_c = _fit_font_size(draw, coord, coord_s, center_w)
    fs_c = font_c.size
    cw = draw.textlength(coord, font=font_c)
    ty += fs_c * 1.35
    draw.text((panel_x + (center_w - cw) / 2 + W * 0.008, ty), coord,
              font=font_c, fill=(255, 255, 255, 255), anchor="ls")
    dt_line = format_job_date(dt)
    font_d = _fit_font_size(draw, dt_line, date_s, center_w)
    dw = draw.textlength(dt_line, font=font_d)
    draw.text((panel_x + (center_w - dw) / 2 + W * 0.008,
               y0 + bar_h - date_s * 0.42), dt_line,
              font=font_d, fill=(255, 255, 255, 255), anchor="ls")

    # Cuaca di kanan strip (default aplikasi web: Berawan 28 C).
    if show_weather:
        overlay = Image.new("RGBA", out.size, (0, 0, 0, 0))
        wx = panel_x + panel_w - weather_w / 2 - W * 0.008
        core.draw_weather(overlay, cond, wx, y0 + bar_h * 0.24,
                          weather_w * 0.72)
        out = Image.alpha_composite(out.convert("RGBA"), overlay)
        draw = ImageDraw.Draw(out, "RGBA")
        tf = round(temp_c * 9 / 5 + 32)
        t1 = "%d°C" % round(temp_c)
        t2 = "%d°F" % tf
        tfont = core.load_font(temp_s)
        w1 = draw.textlength(t1, font=tfont)
        draw.text((panel_x + panel_w - W * 0.014 - w1,
                   y0 + bar_h * 0.68), t1,
                  font=tfont, fill=(255, 255, 255, 255), anchor="ls")
        w2 = draw.textlength(t2, font=tfont)
        draw.text((panel_x + panel_w - W * 0.014 - w2,
                   y0 + bar_h * 0.68 + temp_s * 1.3), t2,
                  font=tfont, fill=(255, 255, 255, 255), anchor="ls")
    return out.convert("RGB")


# ---------------------------------------------------------------- API file


def apply_watermark(src_path, dst_path, style, lat, lon, dt, address,
                    quality=92, place="", weather_text="", temp_c=28,
                    cond="cloudy", show_weather=True, scale=100):
    """Terapkan watermark ke satu file gambar.
    style: 'klasik' atau 'job'. dt: datetime (atau None -> sekarang).
    address: str alamat (boleh '' bila tidak ada).
    place: judul tempat Klasik / baris tengah Job ('' -> dari alamat).
    weather_text: baris cuaca Klasik ('' -> tidak ada).
    temp_c/cond/show_weather: cuaca strip Job (default web: 28 C Berawan).
    scale: ukuran stempel persen (70-150, default 100).
    Menyimpan file BARU; GPS + DateTimeOriginal asli dipertahankan.
    Mengembalikan path hasil."""
    img = Image.open(src_path)
    img = ImageOps.exif_transpose(img)
    exif = img.getexif()
    if dt is None:
        dt = datetime.now()
    s = (scale or 100) / 100.0
    if style == "klasik":
        out = render_klasik(img, lat, lon, dt, address or "",
                            place=place, weather_text=weather_text, s=s)
    elif style == "job":
        out = render_job(img, lat, lon, dt, address or "", place=place,
                         temp_c=temp_c, cond=cond,
                         show_weather=show_weather, s=s)
    else:
        raise ValueError("style tidak dikenal: %r" % style)
    # Pertahankan EXIF asli (GPS + tanggal tetap milik foto asli).
    try:
        exif[274] = 1
    except Exception:
        pass
    fmt = (img.format or "JPEG").upper()
    if fmt == "JPG":
        fmt = "JPEG"
    save_kw = {"exif": exif} if exif else {}
    if fmt == "JPEG":
        save_kw["quality"] = int(quality)
        if out.mode in ("RGBA", "LA", "PA"):
            bg = Image.new("RGB", out.size, (255, 255, 255))
            bg.paste(out, mask=out.split()[-1])
            out = bg
        elif out.mode != "RGB":
            out = out.convert("RGB")
    out.save(dst_path, fmt, **save_kw)
    return dst_path


def watermark_output_path(src_path, style):
    folder = os.path.dirname(src_path)
    stem = os.path.splitext(os.path.basename(src_path))[0]
    ext = os.path.splitext(src_path)[1] or ".jpg"
    return os.path.join(folder, "%s_%s%s" % (stem, style, ext))
