"""Fungsi untuk menyimpan dan mengambil data aplikasi dari SQLite.

Alur sederhananya:
1. Data akun disimpan di smartwaste.db.
2. Setelah masuk, data aplikasi memakai database akun yang aktif.
3. Akun pertama memakai database lama agar riwayat yang ada tetap terjaga;
   akun lainnya memiliki file sendiri di user_data/.

SQLite sudah termasuk di Python, jadi tidak perlu memasang server database.
"""
import contextvars
import hashlib
import hmac
import math
import os
import re
import secrets
import sqlite3
from datetime import datetime, timedelta, timezone

DB_PATH = "smartwaste.db"
ITERASI_HASH_KATA_SANDI = 310_000
MASA_BERLAKU_TOKEN_RESET = timedelta(minutes=15)
JEDA_PERMINTAAN_TOKEN_RESET = timedelta(seconds=60)
_database_pengguna = contextvars.ContextVar("database_pengguna", default=None)


# KONEKSI DATABASE
def _koneksi(lokasi=None):
    """Membuka koneksi SQLite ke lokasi yang diberikan atau database aktif."""
    lokasi = lokasi or _database_pengguna.get() or DB_PATH
    os.makedirs(os.path.dirname(os.path.abspath(lokasi)), exist_ok=True)
    return sqlite3.connect(lokasi)


# AKUN DAN LOGIN
def buat_tabel_auth():
    """Membuat tabel akun di database utama jika tabel tersebut belum ada."""
    conn = _koneksi(DB_PATH)
    try:
        conn.execute("""CREATE TABLE IF NOT EXISTS pengguna (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nama TEXT NOT NULL,
            email TEXT NOT NULL COLLATE NOCASE UNIQUE,
            hash_kata_sandi TEXT NOT NULL,
            salt_kata_sandi TEXT NOT NULL,
            iterasi_hash INTEGER NOT NULL,
            dibuat TEXT NOT NULL,
            hash_kode_pemulihan TEXT)""")
        kolom = {
            baris[1]
            for baris in conn.execute("PRAGMA table_info(pengguna)").fetchall()
        }
        if "hash_kode_pemulihan" not in kolom:
            conn.execute(
                "ALTER TABLE pengguna ADD COLUMN hash_kode_pemulihan TEXT"
            )
        conn.execute(
            """CREATE TABLE IF NOT EXISTS token_reset_kata_sandi (
                pengguna_id INTEGER PRIMARY KEY,
                hash_token TEXT NOT NULL,
                dibuat TEXT NOT NULL,
                kedaluwarsa TEXT NOT NULL
            )"""
        )
        conn.commit()
    finally:
        conn.close()


def daftar_pengguna(nama, email, kata_sandi):
    """Menyimpan akun dan mengembalikan profil beserta kode pemulihan sekali pakai."""
    nama = nama.strip()
    email = email.strip().lower()
    if not nama or len(nama) > 80:
        raise ValueError("Nama wajib diisi dan maksimal 80 karakter.")
    if len(email) > 254 or not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", email):
        raise ValueError("Masukkan alamat email yang valid.")
    _validasi_kata_sandi(kata_sandi)

    kode_pemulihan = _kode_pemulihan_baru()
    salt = secrets.token_bytes(16)
    hash_kata_sandi = hashlib.pbkdf2_hmac(
        "sha256", kata_sandi.encode("utf-8"), salt, ITERASI_HASH_KATA_SANDI
    )
    conn = _koneksi(DB_PATH)
    try:
        cur = conn.execute(
            "INSERT INTO pengguna (nama, email, hash_kata_sandi, salt_kata_sandi, "
            "iterasi_hash, dibuat, hash_kode_pemulihan) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (nama, email, hash_kata_sandi.hex(), salt.hex(), ITERASI_HASH_KATA_SANDI,
             datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
             _hash_kode_pemulihan(kode_pemulihan)),
        )
        conn.commit()
        return {
            "id": cur.lastrowid,
            "nama": nama,
            "email": email,
            "kode_pemulihan": kode_pemulihan,
        }
    except sqlite3.IntegrityError:
        raise ValueError("Email sudah terdaftar.") from None
    finally:
        conn.close()


def _validasi_kata_sandi(kata_sandi):
    """Memastikan kata sandi baru memenuhi batas panjang aplikasi."""
    if len(kata_sandi) < 8 or len(kata_sandi) > 256:
        raise ValueError("Kata sandi harus terdiri dari 8 sampai 256 karakter.")


def _kode_pemulihan_baru():
    """Membuat kode acak 128-bit dalam kelompok agar mudah disalin."""
    kode = secrets.token_hex(16).upper()
    return "-".join(kode[i:i + 4] for i in range(0, len(kode), 4))


def _hash_kode_pemulihan(kode):
    """Mengubah kode pemulihan menjadi hash SHA-256; None jika formatnya salah."""
    if not isinstance(kode, str):
        return None
    kode_normal = re.sub(r"[\s-]", "", kode).upper()
    if not re.fullmatch(r"[0-9A-F]{32}", kode_normal):
        return None
    return hashlib.sha256(kode_normal.encode("ascii")).hexdigest()


def buat_kode_pemulihan_jika_belum_ada(id_pengguna):
    """Membuat kode pemulihan untuk akun lama yang belum memilikinya."""
    if not isinstance(id_pengguna, int) or id_pengguna < 1:
        raise ValueError("ID pengguna tidak valid.")

    conn = _koneksi(DB_PATH)
    try:
        conn.execute("BEGIN IMMEDIATE")
        pengguna = conn.execute(
            "SELECT hash_kode_pemulihan FROM pengguna WHERE id = ?",
            (id_pengguna,),
        ).fetchone()
        if pengguna is None:
            raise ValueError("Akun tidak ditemukan.")
        if pengguna[0]:
            conn.rollback()
            return None

        kode = _kode_pemulihan_baru()
        conn.execute(
            "UPDATE pengguna SET hash_kode_pemulihan = ? WHERE id = ?",
            (_hash_kode_pemulihan(kode), id_pengguna),
        )
        conn.commit()
        return kode
    finally:
        conn.close()


def ganti_kode_pemulihan(id_pengguna):
    """Mengganti kode pemulihan setelah pengguna berhasil masuk ke akunnya."""
    if not isinstance(id_pengguna, int) or id_pengguna < 1:
        raise ValueError("ID pengguna tidak valid.")

    kode = _kode_pemulihan_baru()
    conn = _koneksi(DB_PATH)
    try:
        cur = conn.execute(
            "UPDATE pengguna SET hash_kode_pemulihan = ? WHERE id = ?",
            (_hash_kode_pemulihan(kode), id_pengguna),
        )
        if cur.rowcount != 1:
            raise ValueError("Akun tidak ditemukan.")
        conn.commit()
        return kode
    finally:
        conn.close()


def reset_kata_sandi(email, kode_pemulihan, kata_sandi_baru):
    """Mereset kata sandi dengan kode yang valid dan mengganti kode tersebut."""
    _validasi_kata_sandi(kata_sandi_baru)
    email = email.strip().lower()
    hash_kode = _hash_kode_pemulihan(kode_pemulihan)
    if hash_kode is None:
        return None

    salt = secrets.token_bytes(16)
    hash_kata_sandi = hashlib.pbkdf2_hmac(
        "sha256",
        kata_sandi_baru.encode("utf-8"),
        salt,
        ITERASI_HASH_KATA_SANDI,
    )
    conn = _koneksi(DB_PATH)
    try:
        conn.execute("BEGIN IMMEDIATE")
        pengguna = conn.execute(
            "SELECT id, hash_kode_pemulihan FROM pengguna WHERE email = ?",
            (email,),
        ).fetchone()
        if (
            pengguna is None
            or pengguna[1] is None
            or not hmac.compare_digest(hash_kode, pengguna[1])
        ):
            conn.rollback()
            return None

        kode_baru = _kode_pemulihan_baru()
        conn.execute(
            "UPDATE pengguna SET hash_kata_sandi = ?, salt_kata_sandi = ?, "
            "iterasi_hash = ?, hash_kode_pemulihan = ? WHERE id = ?",
            (
                hash_kata_sandi.hex(),
                salt.hex(),
                ITERASI_HASH_KATA_SANDI,
                _hash_kode_pemulihan(kode_baru),
                pengguna[0],
            ),
        )
        conn.commit()
        return kode_baru
    finally:
        conn.close()


def _hash_token_reset(token):
    """Menghasilkan hash token reset email agar token asli tidak disimpan."""
    if not isinstance(token, str) or not token:
        return None
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def buat_token_reset(email):
    """Membuat token reset 15 menit; mengembalikan None jika email tidak dikenal/terbatas."""
    email = email.strip().lower()
    sekarang = datetime.now(timezone.utc)
    conn = _koneksi(DB_PATH)
    try:
        conn.execute("BEGIN IMMEDIATE")
        pengguna = conn.execute(
            "SELECT id FROM pengguna WHERE email = ?",
            (email,),
        ).fetchone()
        if pengguna is None:
            conn.rollback()
            return None

        permintaan_lama = conn.execute(
            "SELECT dibuat FROM token_reset_kata_sandi WHERE pengguna_id = ?",
            (pengguna[0],),
        ).fetchone()
        if permintaan_lama:
            waktu_permintaan = datetime.fromisoformat(permintaan_lama[0])
            if sekarang - waktu_permintaan < JEDA_PERMINTAAN_TOKEN_RESET:
                conn.rollback()
                return None

        token = secrets.token_urlsafe(32)
        kedaluwarsa = sekarang + MASA_BERLAKU_TOKEN_RESET
        conn.execute(
            "INSERT OR REPLACE INTO token_reset_kata_sandi "
            "(pengguna_id, hash_token, dibuat, kedaluwarsa) VALUES (?, ?, ?, ?)",
            (
                pengguna[0],
                _hash_token_reset(token),
                sekarang.isoformat(timespec="seconds"),
                kedaluwarsa.isoformat(timespec="seconds"),
            ),
        )
        conn.commit()
        return token
    finally:
        conn.close()


def batalkan_token_reset(email, token):
    """Membatalkan token yang gagal dikirim melalui email."""
    email = email.strip().lower()
    hash_token = _hash_token_reset(token)
    if hash_token is None:
        return
    conn = _koneksi(DB_PATH)
    try:
        conn.execute(
            "DELETE FROM token_reset_kata_sandi "
            "WHERE pengguna_id = (SELECT id FROM pengguna WHERE email = ?) "
            "AND hash_token = ?",
            (email, hash_token),
        )
        conn.commit()
    finally:
        conn.close()


def reset_kata_sandi_dengan_token(email, token, kata_sandi_baru):
    """Mereset kata sandi dengan token email yang valid dan belum kedaluwarsa."""
    _validasi_kata_sandi(kata_sandi_baru)
    email = email.strip().lower()
    hash_token = _hash_token_reset(token)
    if hash_token is None:
        return None

    salt = secrets.token_bytes(16)
    hash_kata_sandi = hashlib.pbkdf2_hmac(
        "sha256",
        kata_sandi_baru.encode("utf-8"),
        salt,
        ITERASI_HASH_KATA_SANDI,
    )
    sekarang = datetime.now(timezone.utc)
    conn = _koneksi(DB_PATH)
    try:
        conn.execute("BEGIN IMMEDIATE")
        data_token = conn.execute(
            "SELECT pengguna.id, token_reset_kata_sandi.hash_token, "
            "token_reset_kata_sandi.kedaluwarsa "
            "FROM pengguna JOIN token_reset_kata_sandi "
            "ON token_reset_kata_sandi.pengguna_id = pengguna.id "
            "WHERE pengguna.email = ?",
            (email,),
        ).fetchone()
        if (
            data_token is None
            or not hmac.compare_digest(hash_token, data_token[1])
        ):
            conn.rollback()
            return None
        if sekarang >= datetime.fromisoformat(data_token[2]):
            conn.execute(
                "DELETE FROM token_reset_kata_sandi WHERE pengguna_id = ?",
                (data_token[0],),
            )
            conn.commit()
            return None

        kode_pemulihan_baru = _kode_pemulihan_baru()
        conn.execute(
            "UPDATE pengguna SET hash_kata_sandi = ?, salt_kata_sandi = ?, "
            "iterasi_hash = ?, hash_kode_pemulihan = ? WHERE id = ?",
            (
                hash_kata_sandi.hex(),
                salt.hex(),
                ITERASI_HASH_KATA_SANDI,
                _hash_kode_pemulihan(kode_pemulihan_baru),
                data_token[0],
            ),
        )
        conn.execute(
            "DELETE FROM token_reset_kata_sandi WHERE pengguna_id = ?",
            (data_token[0],),
        )
        conn.commit()
        return kode_pemulihan_baru
    finally:
        conn.close()


def masuk_pengguna(email, kata_sandi):
    """Memeriksa email dan kata sandi; mengembalikan profil atau None jika gagal."""
    email = email.strip().lower()
    conn = _koneksi(DB_PATH)
    try:
        pengguna = conn.execute(
            "SELECT id, nama, email, hash_kata_sandi, salt_kata_sandi, iterasi_hash "
            "FROM pengguna WHERE email = ?",
            (email,),
        ).fetchone()
    finally:
        conn.close()
    if not pengguna:
        return None

    hash_kata_sandi = hashlib.pbkdf2_hmac(
        "sha256", kata_sandi.encode("utf-8"), bytes.fromhex(pengguna[4]), pengguna[5]
    )
    if not hmac.compare_digest(hash_kata_sandi.hex(), pengguna[3]):
        return None
    return {"id": pengguna[0], "nama": pengguna[1], "email": pengguna[2]}


def pakai_database_pengguna(id_pengguna):
    """Memilih database untuk sesi pengguna yang sedang masuk."""
    if not isinstance(id_pengguna, int) or id_pengguna < 1:
        raise ValueError("ID pengguna tidak valid.")
    if id_pengguna == 1:
        _database_pengguna.set(DB_PATH)
        return
    folder = os.path.join(os.path.dirname(os.path.abspath(DB_PATH)), "user_data")
    os.makedirs(folder, exist_ok=True)
    _database_pengguna.set(os.path.join(folder, f"pengguna_{id_pengguna}.db"))


def jalankan(sql, params=(), ambil=False):
    """Menjalankan SQL dengan parameter; jika ambil=True, kembalikan baris sebagai list of dict."""
    conn = _koneksi()
    conn.row_factory = sqlite3.Row
    try:
        cur = conn.execute(sql, params)
        conn.commit()
        return [dict(r) for r in cur.fetchall()] if ambil else None
    finally:
        conn.close()


# KATEGORI DAN PANDUAN
DATA_AWAL = {
    "Organik": {
        "deskripsi": "Sampah dari sisa makhluk hidup yang mudah membusuk dan terurai secara alami.",
        "contoh": "Sisa makanan, kulit buah dan sayur, daun, ranting",
        "warna": "#2E7D32",
        "tips": [
            "Pisahkan dari plastik dan kemasan.",
            "Olah menjadi kompos atau masukkan ke lubang biopori.",
            "Simpan dalam wadah tertutup agar tidak bau dan tidak dikerubungi lalat.",
            "Sisa makanan berminyak, daging, dan tulang sebaiknya tidak masuk kompos rumahan yang sederhana.",
        ],
    },
    "Anorganik": {
        "deskripsi": "Sampah yang sulit terurai. Banyak di antaranya bisa didaur ulang bila dipilah dengan benar.",
        "contoh": "Botol dan gelas plastik, kardus, kaleng, botol kaca",
        "warna": "#F2B01E",
        "tips": [
            "Bersihkan sisa isi dan keringkan sebelum dibuang.",
            "Pisahkan menurut bahan: plastik, kertas dan kardus, kaca, logam.",
            "Pipihkan botol, kaleng, dan kardus agar hemat tempat.",
            "Kertas basah atau berminyak dan plastik sachet sulit didaur ulang. Bila tidak ada pengumpul, masukkan ke sampah residu.",
            "Bungkus pecahan kaca dengan kertas tebal dan beri tanda agar petugas tidak terluka.",
        ],
    },
    "B3": {
        "deskripsi": "Bahan berbahaya dan beracun. Bisa mencemari tanah dan air serta membahayakan kesehatan.",
        "contoh": "Baterai, lampu neon, obat kedaluwarsa, pestisida, oli bekas, barang elektronik",
        "warna": "#C62828",
        "tips": [
            "Jangan dibuang ke tempat sampah biasa, saluran air, atau dibakar.",
            "Simpan di wadah tertutup, terpisah dari sampah lain, dan jauh dari anak-anak.",
            "Serahkan ke titik pengumpulan sampah B3 atau tanyakan ke dinas lingkungan hidup setempat.",
        ],
    },
}


def buat_tabel():
    """Membuat atau memperbarui tabel kategori, panduan, riwayat, dan poin."""
    # Database versi lama (tanpa kolom warna) dibuat ulang dengan struktur baru
    kolom = [k["name"] for k in jalankan("PRAGMA table_info(kategori)", ambil=True)]
    if kolom and "warna" not in kolom:
        for tabel in ("panduan", "riwayat", "kategori"):
            jalankan(f"DROP TABLE IF EXISTS {tabel}")

    jalankan("""CREATE TABLE IF NOT EXISTS kategori (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        nama TEXT NOT NULL UNIQUE,
        deskripsi TEXT NOT NULL,
        contoh TEXT NOT NULL,
        warna TEXT NOT NULL)""")
    jalankan("""CREATE TABLE IF NOT EXISTS panduan (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        kategori_id INTEGER NOT NULL REFERENCES kategori(id),
        teks TEXT NOT NULL)""")
    jalankan("""CREATE TABLE IF NOT EXISTS riwayat (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        waktu TEXT NOT NULL,
        nama_file TEXT,
        label TEXT NOT NULL,
        keyakinan REAL NOT NULL,
        dikenali INTEGER NOT NULL,
        penanganan TEXT NOT NULL DEFAULT 'Belum ditangani',
        berat_gram REAL)""")
    # Kolom tambahan tetap mempertahankan riwayat yang sudah ada.
    kolom_r = [k["name"] for k in jalankan("PRAGMA table_info(riwayat)", ambil=True)]
    for nama, tipe in (
        ("gambar", "BLOB"),
        ("koreksi", "TEXT"),
        ("koreksi_jenis", "TEXT"),
        ("penanganan", "TEXT NOT NULL DEFAULT 'Belum ditangani'"),
        ("berat_gram", "REAL"),
    ):
        if nama not in kolom_r:
            jalankan(f"ALTER TABLE riwayat ADD COLUMN {nama} {tipe}")
    jalankan("""CREATE TABLE IF NOT EXISTS penukaran (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        waktu TEXT NOT NULL,
        hadiah TEXT NOT NULL,
        poin INTEGER NOT NULL)""")
    jalankan("""CREATE TABLE IF NOT EXISTS klaim (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        tanggal TEXT NOT NULL,
        kode TEXT NOT NULL,
        poin INTEGER NOT NULL,
        UNIQUE (tanggal, kode))""")
    jalankan("UPDATE kategori SET warna = ? WHERE nama = ? AND warna = ?", ("#F2B01E", "Anorganik", "#1565C0"))
    if not jalankan("SELECT id FROM kategori", ambil=True):
        isi_data_awal()


def isi_data_awal():
    """Mengisi kategori dan tips bawaan saat tabel kategori masih kosong."""
    for nama, d in DATA_AWAL.items():
        jalankan("INSERT INTO kategori (nama, deskripsi, contoh, warna) VALUES (?, ?, ?, ?)",
                 (nama, d["deskripsi"], d["contoh"], d["warna"]))
        kid = jalankan("SELECT id FROM kategori WHERE nama = ?", (nama,), ambil=True)[0]["id"]
        for teks in d["tips"]:
            jalankan("INSERT INTO panduan (kategori_id, teks) VALUES (?, ?)", (kid, teks))


def _lengkapi(kategori):
    """Menambahkan daftar tips dari tabel panduan ke data satu kategori."""
    teks = jalankan("SELECT teks FROM panduan WHERE kategori_id = ? ORDER BY id", (kategori["id"],), ambil=True)
    kategori["tips"] = [t["teks"] for t in teks]
    return kategori


def ambil_kategori(label):
    """Mengambil satu kategori beserta tipsnya; None jika label tidak ditemukan."""
    baris = jalankan("SELECT * FROM kategori WHERE LOWER(nama) = LOWER(?)", (label,), ambil=True)
    return _lengkapi(baris[0]) if baris else None


def semua_kategori():
    """Mengambil semua kategori beserta tipsnya, diurutkan berdasarkan ID."""
    return [_lengkapi(k) for k in jalankan("SELECT * FROM kategori ORDER BY id", ambil=True)]


def tambah_panduan(nama_kategori, teks):
    """Menambahkan satu tips ke kategori yang namanya diberikan."""
    kid = jalankan("SELECT id FROM kategori WHERE nama = ?", (nama_kategori,), ambil=True)[0]["id"]
    jalankan("INSERT INTO panduan (kategori_id, teks) VALUES (?, ?)", (kid, teks))


POIN_PER_FOTO = 10   # poin tiap foto yang berhasil dikenali
POIN_MISI = 150      # bonus bila misi harian tercapai
TARGET_MISI = 3      # misi harian: klasifikasi 3 sampah dalam sehari


# RIWAYAT HASIL PEMILAHAN
def _sekarang():
    """Menghasilkan waktu lokal dengan format YYYY-MM-DD HH:MM:SS."""
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def simpan_riwayat(nama_file, label, keyakinan, dikenali, gambar=None):
    """Menyimpan hasil klasifikasi dan mengembalikan ID riwayat yang baru."""
    conn = _koneksi()
    try:
        cur = conn.execute(
            "INSERT INTO riwayat (waktu, nama_file, label, keyakinan, dikenali, gambar) VALUES (?, ?, ?, ?, ?, ?)",
            (_sekarang(), nama_file, label, keyakinan, int(dikenali), gambar))
        conn.commit()
        return cur.lastrowid
    finally:
        conn.close()


def set_koreksi(id_riwayat, nilai):
    """Menyimpan koreksi kategori: 'benar' atau nama kategori yang seharusnya."""
    jalankan("UPDATE riwayat SET koreksi = ? WHERE id = ?", (nilai, id_riwayat))


JENIS_BAHAN_KOREKSI = {
    "Karton",
    "Kaca",
    "Logam",
    "Kertas",
    "Plastik",
    "Lainnya / belum tahu",
}


def set_koreksi_jenis(id_riwayat, nilai):
    """Menyimpan koreksi bahan (misalnya Plastik) terpisah dari kategori AI."""
    if nilai not in JENIS_BAHAN_KOREKSI:
        raise ValueError("Koreksi jenis bahan tidak valid.")
    jalankan(
        "UPDATE riwayat SET koreksi_jenis = ? WHERE id = ?",
        (nilai, id_riwayat),
    )


STATUS_PENANGANAN = {
    "Belum ditangani",
    "Sudah dipilah",
    "Sudah dikomposkan",
    "Sudah disetor",
    "Disimpan terpisah dengan aman",
    "Sudah diserahkan ke pengelola",
}


def set_penanganan(id_riwayat, nilai, berat_gram=None):
    """Menyimpan status penanganan dan berat opsional; berat harus nol atau positif."""
    if nilai not in STATUS_PENANGANAN:
        raise ValueError("Status penanganan tidak valid.")
    if berat_gram is not None:
        if isinstance(berat_gram, bool):
            raise ValueError("Berat harus berupa angka nol atau lebih.")
        try:
            berat_gram = float(berat_gram)
        except (TypeError, ValueError) as e:
            raise ValueError("Berat harus berupa angka nol atau lebih.") from e
        if not math.isfinite(berat_gram) or berat_gram < 0:
            raise ValueError("Berat harus berupa angka nol atau lebih.")
    jalankan(
        "UPDATE riwayat SET penanganan = ?, berat_gram = ? WHERE id = ?",
        (nilai, berat_gram, id_riwayat),
    )


def ambil_riwayat(batas=100):
    """Mengambil riwayat terbaru, paling banyak sebanyak batas yang diminta."""
    return jalankan("SELECT id, waktu, nama_file, label, keyakinan, dikenali, koreksi, koreksi_jenis, penanganan, "
                    "berat_gram, gambar "
                    "FROM riwayat "
                    "ORDER BY id DESC LIMIT ?", (batas,), ambil=True)


def ringkasan_penanganan():
    """Menghitung total, jumlah yang ditangani, dan berat selain hasil deteksi manusia."""
    return jalankan(
        "SELECT COUNT(*) AS total, "
        "SUM(CASE WHEN penanganan != 'Belum ditangani' THEN 1 ELSE 0 END) AS sudah_ditangani, "
        "COALESCE(SUM(berat_gram), 0) AS berat_gram "
        "FROM riwayat WHERE label NOT LIKE 'Manusia%'",
        ambil=True,
    )[0]


def riwayat_terakhir(n=3):
    """Mengambil n hasil terbaru untuk ditampilkan sebagai ringkasan."""
    return jalankan("SELECT waktu, label, keyakinan, dikenali, gambar FROM riwayat ORDER BY id DESC LIMIT ?",
                    (n,), ambil=True)


def statistik(awalan=""):
    """Menghitung hasil dikenali per kategori; awalan tanggal dapat membatasi periode."""
    return jalankan("SELECT label, COUNT(*) AS jumlah FROM riwayat WHERE dikenali = 1 AND waktu LIKE ? "
                    "GROUP BY label ORDER BY jumlah DESC", (awalan + "%",), ambil=True)


def jumlah_hari_ini():
    """Menghitung hasil pemilahan yang dikenali hari ini."""
    return jalankan("SELECT COUNT(*) AS n FROM riwayat WHERE dikenali = 1 AND waktu LIKE ?",
                    (_sekarang()[:10] + "%",), ambil=True)[0]["n"]


TARGET_TANTANGAN_MINGGUAN = 10
POIN_TANTANGAN_MINGGUAN = 50
KODE_TANTANGAN_MINGGUAN = "mingguan10"


# MISI DAN POIN
def tantangan_mingguan(sekarang=None):
    """Mengembalikan progres dan status klaim tantangan untuk minggu berjalan."""
    hari_ini = sekarang.date() if isinstance(sekarang, datetime) else sekarang or datetime.now().date()
    mulai = hari_ini - timedelta(days=hari_ini.weekday())
    selesai = mulai + timedelta(days=6)
    mulai_waktu = mulai.strftime("%Y-%m-%d 00:00:00")
    batas_waktu = (selesai + timedelta(days=1)).strftime("%Y-%m-%d 00:00:00")
    ringkasan = jalankan(
        "SELECT label, COUNT(*) AS jumlah FROM riwayat "
        "WHERE dikenali = 1 AND waktu >= ? AND waktu < ? GROUP BY label ORDER BY jumlah DESC",
        (mulai_waktu, batas_waktu), ambil=True,
    )
    klaim = jalankan(
        "SELECT id FROM klaim WHERE tanggal = ? AND kode = ?",
        (mulai.isoformat(), KODE_TANTANGAN_MINGGUAN), ambil=True,
    )
    return {
        "mulai": mulai.isoformat(),
        "selesai": selesai.isoformat(),
        "progres": sum(baris["jumlah"] for baris in ringkasan),
        "target": TARGET_TANTANGAN_MINGGUAN,
        "poin": POIN_TANTANGAN_MINGGUAN,
        "kategori": ringkasan,
        "diklaim": bool(klaim),
    }


def klaim_tantangan_mingguan(sekarang=None):
    """Memberikan bonus tantangan sekali per minggu jika target pemindaian tercapai."""
    hari_ini = sekarang.date() if isinstance(sekarang, datetime) else sekarang or datetime.now().date()
    mulai = hari_ini - timedelta(days=hari_ini.weekday())
    batas_waktu = (mulai + timedelta(days=7)).strftime("%Y-%m-%d 00:00:00")
    conn = _koneksi()
    try:
        conn.execute("BEGIN IMMEDIATE")
        jumlah = conn.execute(
            "SELECT COUNT(*) FROM riwayat WHERE dikenali = 1 AND waktu >= ? AND waktu < ?",
            (mulai.strftime("%Y-%m-%d 00:00:00"), batas_waktu),
        ).fetchone()[0]
        if jumlah < TARGET_TANTANGAN_MINGGUAN:
            conn.rollback()
            return False
        cur = conn.execute(
            "INSERT OR IGNORE INTO klaim (tanggal, kode, poin) VALUES (?, ?, ?)",
            (mulai.isoformat(), KODE_TANTANGAN_MINGGUAN, POIN_TANTANGAN_MINGGUAN),
        )
        conn.commit()
        return cur.rowcount == 1
    finally:
        conn.close()


MISI = [
    {"kode": "harian3", "jenis": "Harian", "nama": "Pilah 3 Sampah Hari Ini", "target": 3, "poin": 150,
     "deskripsi": "Pindai sampah apa saja dengan kamera PilahPintar."},
    {"kode": "beragam", "jenis": "Harian", "nama": "Pindai 2 Kategori Berbeda", "target": 2, "poin": 100,
     "deskripsi": "Temukan dua kategori sampah yang berbeda hari ini, misalnya Organik dan Anorganik."},
    {"kode": "koreksi2", "jenis": "Komunitas", "nama": "Koreksi & Verifikasi 2 Hasil AI", "target": 2, "poin": 50,
     "deskripsi": "Tandai hasil AI sebagai benar atau salah di halaman hasil."},
]


def _progres(kode):
    """Menghitung progres misi tertentu untuk hari ini."""
    hari = _sekarang()[:10] + "%"
    if kode == "harian3":
        sql = "SELECT COUNT(*) AS n FROM riwayat WHERE dikenali = 1 AND waktu LIKE ?"
    elif kode == "beragam":
        sql = "SELECT COUNT(DISTINCT label) AS n FROM riwayat WHERE dikenali = 1 AND waktu LIKE ?"
    else:
        sql = "SELECT COUNT(*) AS n FROM riwayat WHERE koreksi IS NOT NULL AND waktu LIKE ?"
    return jalankan(sql, (hari,), ambil=True)[0]["n"]


def daftar_misi():
    """Mengembalikan daftar misi hari ini, termasuk progres dan status selesai/klaim."""
    hari = _sekarang()[:10]
    hasil = []
    for m in MISI:
        n = _progres(m["kode"])
        diklaim = bool(jalankan("SELECT id FROM klaim WHERE tanggal = ? AND kode = ?", (hari, m["kode"]), ambil=True))
        hasil.append(dict(m, progres=n, selesai=n >= m["target"], diklaim=diklaim))
    return hasil


def klaim_misi(kode):
    """Menyimpan klaim misi jika target tercapai dan misi belum diklaim."""
    for m in daftar_misi():
        if m["kode"] == kode and m["selesai"] and not m["diklaim"]:
            jalankan("INSERT OR IGNORE INTO klaim (tanggal, kode, poin) VALUES (?, ?, ?)",
                     (_sekarang()[:10], kode, m["poin"]))


def poin():
    """Menghitung total poin didapat, dipakai, dan saldo yang tersisa."""
    dikenali = jalankan("SELECT COUNT(*) AS n FROM riwayat WHERE dikenali = 1", ambil=True)[0]["n"]
    bonus = jalankan("SELECT COALESCE(SUM(poin), 0) AS n FROM klaim", ambil=True)[0]["n"]
    dipakai = jalankan("SELECT COALESCE(SUM(poin), 0) AS n FROM penukaran", ambil=True)[0]["n"]
    didapat = dikenali * POIN_PER_FOTO + bonus
    return {"didapat": didapat, "dipakai": dipakai, "saldo": didapat - dipakai}


def hapus_riwayat(id_riwayat):
    """Menghapus satu hasil riwayat berdasarkan ID-nya."""
    jalankan("DELETE FROM riwayat WHERE id = ?", (id_riwayat,))


def hapus_semua_riwayat():
    """Menghapus semua hasil dari tabel riwayat pengguna aktif."""
    jalankan("DELETE FROM riwayat")


def tambah_penukaran(hadiah, jumlah_poin):
    """Mencatat penukaran poin untuk hadiah tertentu."""
    jalankan("INSERT INTO penukaran (waktu, hadiah, poin) VALUES (?, ?, ?)", (_sekarang(), hadiah, jumlah_poin))


def riwayat_penukaran():
    """Mengambil daftar penukaran terbaru beserta waktu, hadiah, dan poinnya."""
    return jalankan("SELECT waktu, hadiah, poin FROM penukaran ORDER BY id DESC", ambil=True)


def akurasi_koreksi():
    """Mengembalikan jumlah koreksi benar dan jumlah koreksi yang menyatakan salah."""
    b = jalankan("SELECT COUNT(*) AS n FROM riwayat WHERE koreksi = 'benar'", ambil=True)[0]["n"]
    t = jalankan("SELECT COUNT(*) AS n FROM riwayat WHERE koreksi IS NOT NULL AND koreksi != 'benar'",
                 ambil=True)[0]["n"]
    return b, t