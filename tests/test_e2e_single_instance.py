# tests/test_e2e_single_instance.py — Uji ujung-ke-ujung single-instance
# lewat proses NYATA (mensimulasikan Explorer yang memanggil exe
# sekali per file).
#
# Jalankan di bawah Xvfb (dialog tkinter butuh layar):
#   xvfb-run -a -s "-screen 0 1024x600x24" \
#       .venv-test/bin/python tests/test_e2e_single_instance.py
#
# Proses A: `convtool.py exif foto0.jpg` -> primary, dialog terbuka.
# Proses B (1,5 detik kemudian): `convtool.py exif foto1.jpg foto2.jpg`
# -> harus meneruskan file ke A lalu KELUAR CEPAT (kode 0), bukan
# membuka dialog sendiri. Bukti B tidak membuka dialog: B keluar
# dalam < 5 detik (dialog modal akan memblokir sampai ditutup user).
# Bukti A tetap primary: A masih hidup sesudah B keluar.

import os
import subprocess
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PIL import Image  # noqa: E402

WORK = os.path.join(os.path.dirname(os.path.abspath(__file__)), "work-e2e")
PASSES = [0]
FAILURES = []


def check(name, cond, detail=""):
    if cond:
        PASSES[0] += 1
        print("PASS ", name, detail)
    else:
        FAILURES.append(name)
        print("FAIL ", name, detail)


def main():
    os.makedirs(WORK, exist_ok=True)
    root_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    photos = []
    for i in range(3):
        p = os.path.join(WORK, "foto%d.jpg" % i)
        Image.new("RGB", (400, 300), (40 + i * 60, 120, 200)).save(p)
        photos.append(p)
    env = dict(os.environ)
    env["PYTHONPATH"] = root_dir + os.pathsep + env.get("PYTHONPATH", "")

    print("\n== e2e single-instance: 2 proses, 1 dialog ==")
    state_file = os.path.join(WORK, "state.txt")
    env_a = dict(env)
    env_a["CONVTOOL_STATE_FILE"] = state_file
    proc_a = subprocess.Popen(
        [sys.executable, os.path.join(root_dir, "convtool.py"),
         "exif", photos[0]],
        cwd=root_dir, env=env_a)
    time.sleep(2.0)  # beri waktu A bind port + buka dialog
    check("proses A masih hidup (primary, dialog terbuka)",
          proc_a.poll() is None, "")
    t0 = time.time()
    proc_b = subprocess.run(
        [sys.executable, os.path.join(root_dir, "convtool.py"),
         "exif", photos[1], photos[2]],
        cwd=root_dir, env=env, timeout=15)
    dt = time.time() - t0
    check("proses B keluar cepat (meneruskan, bukan dialog sendiri)",
          dt < 8.0, "%.1f detik" % dt)
    check("proses B kode keluar 0", proc_b.returncode == 0,
          str(proc_b.returncode))
    time.sleep(0.5)
    check("proses A TETAP hidup sesudah B keluar (tetap primary)",
          proc_a.poll() is None, "")
    # Bukti paling penting: daftar file di dialog A BERTAMBAH jadi 3
    # (kiriman B digabung oleh _poll_ipc -> add_files).
    got = []
    end = time.time() + 3.0
    while time.time() < end:
        try:
            got = [l for l in open(state_file,
                                   encoding="utf-8").read().splitlines()
                   if l.strip()]
        except Exception:
            got = []
        if len(got) == 3:
            break
        time.sleep(0.2)
    check("dialog A berisi 3 foto sesudah kiriman B",
          got == photos, str(got))
    proc_a.terminate()
    try:
        proc_a.wait(timeout=5)
    except Exception:
        proc_a.kill()
    check("proses A bisa ditutup", proc_a.poll() is not None, "")

    print("\n==================================")
    print("LOLOS: %d   GAGAL: %d" % (PASSES[0], len(FAILURES)))
    if FAILURES:
        print("Yang gagal:", ", ".join(FAILURES))
        return 1
    print("SEMUA UJI E2E LOLOS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
