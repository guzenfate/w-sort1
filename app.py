"""W-Sort - mengelompokkan foto sampah ke kategori yang didukung model.

Layar: Masuk/Daftar, Beranda, Panduan, Pindai (lalu Hasil), Misi, Riwayat.
Jalankan di Windows dengan:  .\venv\Scripts\python.exe -m streamlit run app.py
"""
import base64
import importlib.util
import io
import os
import sys
import threading
import time
from datetime import date, datetime, timedelta
from html import escape
from urllib.parse import quote_plus

import numpy as np
import pandas as pd
import streamlit as st
from streamlit.errors import StreamlitSecretNotFoundError
from PIL import Image, ImageOps

import email_service
import ui

_database_spec = importlib.util.spec_from_file_location(
    "pilahpintar_database", os.path.join(os.path.dirname(os.path.abspath(__file__)), "database.py")
)
if _database_spec is None or _database_spec.loader is None:
    raise ImportError("File database.py untuk W-Sort tidak ditemukan.")
db = importlib.util.module_from_spec(_database_spec)
_database_spec.loader.exec_module(db)

AMBANG = 0.65
SELISIH_KEYAKINAN_MINIMAL = 0.12
AMBANG_DETEKSI_OBJEK = 0.35
AMBANG_DETEKSI_MANUSIA = 0.80
# Keluaran detector memakai COCO category_id - 1 (termasuk celah indeks COCO).
# Hanya objek mirip kemasan, sisa makanan, elektronik, buku, dan kebutuhan sekali pakai.
KELAS_OBJEK_SAMPAH = {
    43, 45, 46, 50, 51, 52, 53, 54, 55, 56, 57, 58, 59, 60,
    71, 72, 73, 74, 75, 76, 77, 78, 79, 81, 83, 88, 89,
}
JENIS_ANORGANIK = ["Karton", "Kaca", "Logam", "Kertas", "Plastik"]
OPSI_KOREKSI_JENIS = [*JENIS_ANORGANIK, "Lainnya / belum tahu"]

# ASUMSI CONTOH untuk kartu "Dampak Lingkungan". Ini bukan hasil pengukuran:
# aplikasi hanya tahu jenis sampah, bukan beratnya. Ganti dengan angka dari
# sumber resmi sebelum dilaporkan sebagai data nyata.
BERAT_KG_PER_FOTO = {"organik": 0.30, "anorganik": 0.10, "b3": 0.05}
CO2_KG_PER_KG = {"organik": 0.5, "anorganik": 1.5, "b3": 1.0}
CO2_KG_PER_POHON = 21  # perkiraan serapan CO2 satu pohon per tahun

HADIAH = [("Stiker W-Sort", 300), ("Tote bag daur ulang", 800), ("Bibit tanaman", 1200)]  # contoh

st.set_page_config(page_title="W-Sort", page_icon="♻️", layout="centered")
db.buat_tabel_auth()

st.markdown(f"<style>{ui.css()}</style>", unsafe_allow_html=True)

if "layar" not in st.session_state:
    st.session_state.layar = "mulai"
if "kunci" not in st.session_state:
    st.session_state.kunci = 0  # dinaikkan untuk mengosongkan kolom unggah foto


def h(html):
    """Menampilkan HTML yang dibuat aplikasi ke halaman Streamlit."""
    st.markdown(html, unsafe_allow_html=True)


def layar_autentikasi():
    """Menampilkan formulir masuk dan pendaftaran akun."""
    with st.container(key="auth_page"):
        h(
            '<div class="auth-brand"><span class="auth-brand-mark">♻</span>'
            '<span><strong>W-Sort</strong><small>Pilah lebih bijak, mulai dari sini</small></span></div>'
        )
        h(ui.html_tiga_tong())
        st.title("Selamat datang")
        st.caption("Masuk atau buat akun untuk mulai memilah sampah.")

        with st.container(key="auth_card"):
            tab_masuk, tab_daftar, tab_lupa = st.tabs(
                ["Masuk", "Buat akun", "Lupa kata sandi"]
            )
            with tab_masuk:
                st.markdown(
                    '<div class="auth-section-title">Senang bertemu lagi</div>'
                    '<div class="auth-section-copy">Masuk untuk melanjutkan perjalanan pilah sampahmu.</div>',
                    unsafe_allow_html=True,
                )
                with st.form("form_masuk"):
                    email = st.text_input("Email", key="login_email")
                    kata_sandi = st.text_input(
                        "Kata sandi", type="password", key="login_kata_sandi"
                    )
                    masuk = st.form_submit_button(
                        "Masuk ke akun", type="primary", use_container_width=True
                    )
                if masuk:
                    pengguna = db.masuk_pengguna(email, kata_sandi)
                    if pengguna:
                        st.session_state.pengguna = pengguna
                        st.session_state.layar = "mulai"
                        st.rerun()
                    st.error("Email atau kata sandi salah.")

            with tab_daftar:
                st.markdown(
                    '<div class="auth-section-title">Mulai pilah dengan lebih mudah</div>'
                    '<div class="auth-section-copy">Buat akun untuk menyimpan aktivitas dan progresmu.</div>',
                    unsafe_allow_html=True,
                )
                with st.form("form_daftar"):
                    nama = st.text_input("Nama", key="daftar_nama")
                    email = st.text_input("Email", key="daftar_email")
                    kata_sandi = st.text_input(
                        "Kata sandi (minimal 8 karakter)",
                        type="password",
                        key="daftar_kata_sandi",
                    )
                    daftar = st.form_submit_button(
                        "Buat akun", type="primary", use_container_width=True
                    )
                if daftar:
                    try:
                        pengguna = db.daftar_pengguna(nama, email, kata_sandi)
                    except ValueError as e:
                        st.error(str(e))
                    else:
                        st.session_state.kode_pemulihan_baru = pengguna.pop(
                            "kode_pemulihan"
                        )
                        st.session_state.pengguna = pengguna
                        st.session_state.layar = "mulai"
                        st.rerun()

            with tab_lupa:
                st.markdown(
                    '<div class="auth-section-title">Pulihkan akses akun</div>'
                    '<div class="auth-section-copy">Pilih cara yang paling nyaman untuk membuat kata sandi baru.</div>',
                    unsafe_allow_html=True,
                )
                tab_email, tab_kode = st.tabs(["Kirim kode ke email", "Pakai kode pemulihan"])
                with tab_email:
                    with st.container(key="auth_recovery_email"):
                        st.markdown(
                            '<div class="auth-step"><span>1</span><div><strong>Minta kode reset</strong>'
                            '<small>Kode berlaku 15 menit dan hanya dapat digunakan sekali.</small></div></div>',
                            unsafe_allow_html=True,
                        )
                        with st.form("form_minta_kode_email"):
                            email_minta_reset = st.text_input(
                                "Email akun", key="reset_email"
                            )
                            minta_kode = st.form_submit_button(
                                "Kirim kode reset", use_container_width=True
                            )
                        if minta_kode:
                            konfigurasi_smtp = muat_konfigurasi_smtp()
                            if konfigurasi_smtp is None:
                                st.error(
                                    "Layanan email belum dikonfigurasi. Atur bagian [smtp] "
                                    "di .streamlit/secrets.toml terlebih dahulu."
                                )
                            else:
                                token = None
                                try:
                                    token = db.buat_token_reset(email_minta_reset)
                                    if token:
                                        email_service.kirim_kode_reset(
                                            email_minta_reset,
                                            token,
                                            konfigurasi_smtp,
                                        )
                                except email_service.EmailDeliveryError as e:
                                    if token:
                                        db.batalkan_token_reset(email_minta_reset, token)
                                    st.error(str(e))
                                else:
                                    st.success(
                                        "Jika email terdaftar dan tidak sedang dibatasi, "
                                        "kode reset akan dikirim. Periksa juga folder spam."
                                    )

                        st.markdown(
                            '<div class="auth-step"><span>2</span><div><strong>Buat kata sandi baru</strong>'
                            '<small>Masukkan kode yang dikirim ke email akunmu.</small></div></div>',
                            unsafe_allow_html=True,
                        )
                        with st.form("form_reset_dengan_email"):
                            email_reset = st.text_input(
                                "Email akun", key="reset_email_verifikasi"
                            )
                            token_reset = st.text_input(
                                "Kode dari email", key="reset_token_email"
                            )
                            kata_sandi_baru = st.text_input(
                                "Kata sandi baru",
                                type="password",
                                key="reset_kata_sandi_email",
                            )
                            konfirmasi_kata_sandi = st.text_input(
                                "Ulangi kata sandi baru",
                                type="password",
                                key="reset_konfirmasi_email",
                            )
                            reset_email = st.form_submit_button(
                                "Atur ulang kata sandi",
                                type="primary",
                                use_container_width=True,
                            )
                        if reset_email:
                            if kata_sandi_baru != konfirmasi_kata_sandi:
                                st.error("Kata sandi baru dan konfirmasi tidak sama.")
                            else:
                                try:
                                    kode_baru = db.reset_kata_sandi_dengan_token(
                                        email_reset,
                                        token_reset,
                                        kata_sandi_baru,
                                    )
                                except ValueError as e:
                                    st.error(str(e))
                                else:
                                    if kode_baru:
                                        st.session_state.kode_pemulihan_baru = kode_baru
                                        st.success(
                                            "Kata sandi berhasil diubah. Simpan kode pemulihan baru."
                                        )
                                    else:
                                        st.error(
                                            "Kode email tidak valid atau sudah kedaluwarsa."
                                        )

                with tab_kode:
                    with st.container(key="auth_recovery_code"):
                        st.markdown(
                            '<div class="auth-section-copy auth-recovery-note">'
                            'Tidak dapat mengakses email? Gunakan kode pemulihan yang '
                            'disimpan saat mendaftar atau setelah reset kata sandi.</div>',
                            unsafe_allow_html=True,
                        )
                        with st.form("form_reset_kata_sandi"):
                            email_reset_kode = st.text_input(
                                "Email akun", key="reset_email_kode_pemulihan"
                            )
                            kode_pemulihan = st.text_input(
                                "Kode pemulihan",
                                key="reset_kode_pemulihan",
                                help="Kode pemulihan ditampilkan saat daftar atau setelah reset.",
                            )
                            kata_sandi_baru_kode = st.text_input(
                                "Kata sandi baru",
                                type="password",
                                key="reset_kata_sandi_kode",
                            )
                            konfirmasi_kata_sandi_kode = st.text_input(
                                "Ulangi kata sandi baru",
                                type="password",
                                key="reset_konfirmasi_kode",
                            )
                            reset_kode = st.form_submit_button(
                                "Atur ulang kata sandi",
                                type="primary",
                                use_container_width=True,
                            )
                        if reset_kode:
                            if kata_sandi_baru_kode != konfirmasi_kata_sandi_kode:
                                st.error("Kata sandi baru dan konfirmasi tidak sama.")
                            else:
                                try:
                                    kode_baru = db.reset_kata_sandi(
                                        email_reset_kode,
                                        kode_pemulihan,
                                        kata_sandi_baru_kode,
                                    )
                                except ValueError as e:
                                    st.error(str(e))
                                else:
                                    if kode_baru:
                                        st.session_state.kode_pemulihan_baru = kode_baru
                                        st.success(
                                            "Kata sandi berhasil diubah. Simpan kode pemulihan baru."
                                        )
                                    else:
                                        st.error(
                                            "Email atau kode pemulihan tidak cocok."
                                        )

        st.caption(
            "Akun dan data disimpan lokal di server aplikasi. "
            "Pada hosting gratis, data dapat hilang saat server dimulai ulang."
        )
        tampilkan_kode_pemulihan()


def muat_konfigurasi_smtp():
    """Mengambil konfigurasi SMTP dari secrets Streamlit atau None jika kosong."""
    try:
        return st.secrets["smtp"]
    except (KeyError, StreamlitSecretNotFoundError):
        return None


def lupakan_kode_pemulihan():
    """Menghapus kode pemulihan sementara setelah pengguna menyimpannya."""
    st.session_state.pop("kode_pemulihan_baru", None)


def tampilkan_kode_pemulihan():
    """Menampilkan kode pemulihan baru sekali sampai pengguna mengaku menyimpannya."""
    kode = st.session_state.get("kode_pemulihan_baru")
    if not kode:
        return
    st.warning(
        "Simpan kode ini sekarang. Kode tidak disimpan dalam bentuk yang bisa "
        "dibaca dan tidak dapat ditampilkan lagi setelah ditutup."
    )
    st.code(kode)
    st.button(
        "Saya sudah menyimpan kode",
        key="simpan_kode_pemulihan",
        on_click=lupakan_kode_pemulihan,
    )


def keluar():
    """Menghapus data sesi pengguna lalu kembali ke layar awal."""
    for kunci in (
        "pengguna",
        "hasil",
        "konfirmasi_hapus",
        "kode_pemulihan_baru",
        "kode_pemulihan_diperiksa",
    ):
        st.session_state.pop(kunci, None)
    st.session_state.layar = "mulai"


def pindah(layar):
    """Mengubah layar aplikasi yang sedang aktif."""
    st.session_state.layar = layar


def pilih_kategori_awal(kategori):
    """Menyimpan kategori yang dipilih pada layar pembuka."""
    st.session_state.kategori_awal = kategori


def ganti_gambar():
    """Mengganti kunci widget foto agar pengguna bisa memilih gambar lain."""
    st.session_state.kunci += 1


def pindai_lagi():
    """Mengosongkan widget foto dan membuka kembali layar pemindaian."""
    st.session_state.kunci += 1
    st.session_state.layar = "pindai"


def angka(x, desimal=1):
    """Memformat angka untuk tampilan Indonesia dengan koma desimal."""
    return f"{x:.{desimal}f}".replace(".", ",")


@st.cache_resource
def muat_model():
    """Memuat model kategori dan memeriksa bentuk input serta jumlah kelasnya."""
    from tensorflow import keras
    folder_model = os.path.join(os.path.dirname(os.path.abspath(__file__)), "model")
    model = keras.models.load_model(os.path.join(folder_model, "keras_model.h5"), compile=False)
    labels = baca_label_model(folder_model)
    if model.input_shape != (None, 224, 224, 3) or model.output_shape != (
        None,
        len(labels),
    ):
        raise ValueError(
            "Model kategori harus menerima gambar 224x224 RGB dan menghasilkan "
            f"{len(labels)} kelas sesuai labels.txt."
        )
    return model, labels


def baca_label_model(folder_model=None):
    """Membaca dan memvalidasi nama kelas dari file labels.txt."""
    folder_model = folder_model or os.path.join(
        os.path.dirname(os.path.abspath(__file__)), "model"
    )
    lokasi_label = os.path.join(folder_model, "labels.txt")
    labels_bernomor = []
    with open(lokasi_label, encoding="utf-8") as f:
        for baris in f:
            if not baris.strip():
                continue
            bagian = baris.strip().split(maxsplit=1)
            if len(bagian) != 2:
                raise ValueError(f"Format label tidak valid di {lokasi_label}: {baris.strip()}")
            try:
                nomor = int(bagian[0])
            except ValueError as e:
                raise ValueError(
                    f"Nomor kelas tidak valid di {lokasi_label}: {bagian[0]}"
                ) from e
            labels_bernomor.append((nomor, bagian[1]))
    if [nomor for nomor, _ in labels_bernomor] != list(range(len(labels_bernomor))):
        raise ValueError(f"Nomor kelas di {lokasi_label} harus berurutan mulai dari 0.")
    labels = [label for _, label in labels_bernomor]
    if not labels or len(set(labels)) != len(labels):
        raise ValueError(f"Daftar label di {lokasi_label} kosong atau memiliki duplikat.")
    return labels


@st.cache_resource
def muat_model_material():
    """Memuat model jenis bahan anorganik dan memeriksa bentuk keluarannya."""
    from tensorflow import keras
    folder_model = os.path.join(os.path.dirname(os.path.abspath(__file__)), "model")
    lokasi = os.path.join(folder_model, "material_classifier.h5")
    if not os.path.isfile(lokasi):
        raise FileNotFoundError(
            "Model jenis bahan tidak ditemukan: model/material_classifier.h5. "
            "Pastikan model terlatih tersedia di folder model/."
        )
    model = keras.models.load_model(lokasi, compile=False)
    if model.input_shape != (None, 224, 224, 3) or model.output_shape != (
        None,
        len(JENIS_ANORGANIK),
    ):
        raise ValueError(
            "Model jenis bahan harus menerima gambar 224x224 RGB dan menghasilkan "
            f"{len(JENIS_ANORGANIK)} kelas."
        )
    return model


def prediksi(gambar, model, labels):
    """Mengembalikan daftar (label, skor) dari yang paling yakin."""
    gambar = ImageOps.fit(gambar.convert("RGB"), (224, 224), Image.Resampling.LANCZOS)
    data = np.asarray(gambar, dtype=np.float32) / 127.5 - 1  # sama seperti Teachable Machine
    skor = model.predict(data[np.newaxis, ...], verbose=0)[0]
    urut = np.argsort(skor)[::-1]
    return [(labels[i], float(skor[i])) for i in urut]


@st.cache_resource
def muat_detektor_objek():
    """Memuat detector COCO lokal: kelas 0 adalah person, kelas lain mengikuti COCO 80."""
    import tensorflow as tf

    lokasi = os.path.join(
        os.path.dirname(os.path.abspath(__file__)), "model", "efficientdet_lite0.tflite"
    )
    if not os.path.isfile(lokasi):
        raise FileNotFoundError(
            "Model deteksi objek tidak ditemukan: model/efficientdet_lite0.tflite. "
            "Jalankan kembali Jalankan PilahPintar.bat untuk mengunduh model."
        )
    interpreter = tf.lite.Interpreter(model_path=lokasi, num_threads=2)
    interpreter.allocate_tensors()
    return {
        "interpreter": interpreter,
        "lock": threading.Lock(),
        "input": interpreter.get_input_details()[0],
        "outputs": interpreter.get_output_details(),
    }


def deteksi_objek(gambar, detektor):
    """Mendeteksi manusia dan objek COCO yang mungkin merupakan sampah di seluruh gambar."""
    gambar = gambar.convert("RGB")
    lebar, tinggi = gambar.size
    masukan = detektor["input"]
    ukuran = int(masukan["shape"][1])
    skala = min(ukuran / lebar, ukuran / tinggi)
    lebar_baru = max(1, round(lebar * skala))
    tinggi_baru = max(1, round(tinggi * skala))
    kiri = (ukuran - lebar_baru) // 2
    atas = (ukuran - tinggi_baru) // 2
    kanvas = Image.new("RGB", (ukuran, ukuran), (114, 114, 114))
    kanvas.paste(gambar.resize((lebar_baru, tinggi_baru), Image.Resampling.BILINEAR), (kiri, atas))
    tensor = np.asarray(kanvas, dtype=masukan["dtype"])[np.newaxis, ...]

    with detektor["lock"]:
        detektor["interpreter"].set_tensor(masukan["index"], tensor)
        detektor["interpreter"].invoke()
        keluaran = {
            detail["name"].rsplit(":", 1)[-1]: detektor["interpreter"].get_tensor(detail["index"])
            for detail in detektor["outputs"]
        }

    kotak = keluaran["3"][0]
    kelas = keluaran["2"][0]
    skor = keluaran["1"][0]
    jumlah = min(int(keluaran["0"].reshape(-1)[0]), len(skor))
    objek = []
    for i in range(jumlah):
        kelas_id = int(round(float(kelas[i])))
        keyakinan = float(skor[i])
        manusia = kelas_id == 0 and keyakinan >= AMBANG_DETEKSI_MANUSIA
        if not manusia and (kelas_id not in KELAS_OBJEK_SAMPAH or keyakinan < AMBANG_DETEKSI_OBJEK):
            continue
        y1, x1, y2, x2 = (float(v) for v in kotak[i])
        x1 = max(0, min(lebar, round((x1 * ukuran - kiri) / (lebar_baru / lebar))))
        x2 = max(0, min(lebar, round((x2 * ukuran - kiri) / (lebar_baru / lebar))))
        y1 = max(0, min(tinggi, round((y1 * ukuran - atas) / (tinggi_baru / tinggi))))
        y2 = max(0, min(tinggi, round((y2 * ukuran - atas) / (tinggi_baru / tinggi))))
        batas_ukuran = 2 if manusia else 8
        if x2 - x1 < batas_ukuran or y2 - y1 < batas_ukuran:
            continue
        objek.append({
            "kelas_id": kelas_id,
            "manusia": manusia,
            "keyakinan_deteksi": keyakinan,
            "kotak": (x1, y1, x2, y2),
        })
    return objek


def klasifikasi_multi(
    gambar, model, labels, detektor, model_material, fallback_tanpa_deteksi=True,
    jumlah_maksimal_objek=10, abaikan_deteksi_manusia=False,
):
    """Mendeteksi manusia terlebih dahulu, lalu mengklasifikasikan sampah satu per satu."""
    objek = deteksi_objek(gambar, detektor)
    manusia = [] if abaikan_deteksi_manusia else [obj for obj in objek if obj["manusia"]]
    kandidat = [obj for obj in objek if not obj["manusia"]]
    if manusia and not kandidat:
        return {"manusia": manusia, "item": []}

    item = []
    for obj in sorted(kandidat, key=lambda nilai: nilai["kotak"][0])[:jumlah_maksimal_objek]:
        kiri, atas, kanan, bawah = obj["kotak"]
        lebar, tinggi = kanan - kiri, bawah - atas
        pad_x, pad_y = round(lebar * 0.06), round(tinggi * 0.06)
        potongan = gambar.convert("RGB").crop((
            max(0, kiri - pad_x), max(0, atas - pad_y),
            min(gambar.width, kanan + pad_x), min(gambar.height, bawah + pad_y),
        ))
        hasil = prediksi(potongan, model, labels)
        label, skor = hasil[0]
        jenis = jenis_spesifik(potongan, hasil, model_material)
        item.append({
            "label": label,
            "skor": skor,
            "jenis": jenis[0] if jenis else None,
            "skor_jenis": jenis[1] if jenis else None,
            "dikenali": prediksi_cukup_yakin(hasil),
            "semua": hasil,
            "gambar": jpeg(potongan, 640),
            "thumbnail": jpeg(potongan, 160),
            "keyakinan_deteksi": obj["keyakinan_deteksi"],
            "kotak": obj["kotak"],
        })
    if not item and not fallback_tanpa_deteksi:
        return {"manusia": [], "item": []}
    if not item:
        hasil = prediksi(gambar, model, labels)
        label, skor = hasil[0]
        jenis = jenis_spesifik(gambar, hasil, model_material)
        item.append({
            "label": label,
            "skor": skor,
            "jenis": jenis[0] if jenis else None,
            "skor_jenis": jenis[1] if jenis else None,
            "dikenali": prediksi_cukup_yakin(hasil),
            "semua": hasil,
            "gambar": jpeg(gambar, 640),
            "thumbnail": jpeg(gambar, 160),
            "keyakinan_deteksi": None,
            "kotak": None,
        })
    return {"manusia": [], "item": item}


def jenis_spesifik(gambar, hasil_kategori, model_material):
    """Menampilkan jenis bahan hanya jika kategori dan prediksi bahan cukup yakin."""
    if hasil_kategori[0][0] != "Anorganik" or not prediksi_cukup_yakin(hasil_kategori):
        return None
    hasil = prediksi(gambar, model_material, JENIS_ANORGANIK)
    if not prediksi_cukup_yakin(hasil):
        return None
    return hasil[0]


def simpan_hasil_multi(gambar, klasifikasi, nama_file):
    """Menyimpan hasil objek terdeteksi ke database dan sesi Streamlit."""
    foto = jpeg(gambar, 960)
    if klasifikasi["manusia"]:
        manusia = max(klasifikasi["manusia"], key=lambda obj: obj["keyakinan_deteksi"])
        id_riwayat = db.simpan_riwayat(
            nama_file, "Manusia (scan dibatalkan)", manusia["keyakinan_deteksi"], False, jpeg(gambar, 160)
        )
        st.session_state.hasil = {
            "batch": True, "manusia": True, "gambar": foto,
            "keyakinan_manusia": manusia["keyakinan_deteksi"], "id": id_riwayat,
        }
        return

    items = []
    for nomor, item in enumerate(klasifikasi["item"], 1):
        id_riwayat = db.simpan_riwayat(
            f"{nama_file} · benda {nomor}", item["label"], item["skor"],
            item["dikenali"], item["thumbnail"],
        )
        items.append(dict(
            item, id=id_riwayat, koreksi=None, koreksi_jenis=None,
            penanganan="Belum ditangani", berat_gram=None
        ))
    st.session_state.hasil = {
        "batch": True, "manusia": False, "kosong": not items, "gambar": foto, "items": items,
    }


def prediksi_cukup_yakin(hasil):
    """Menerima klasifikasi jika skornya tinggi dan cukup berbeda dari pilihan kedua."""
    if not hasil or hasil[0][1] < AMBANG:
        return False
    skor_kedua = hasil[1][1] if len(hasil) > 1 else 0.0
    return hasil[0][1] - skor_kedua >= SELISIH_KEYAKINAN_MINIMAL


def jpeg(gambar, sisi=None):
    """Mengubah gambar menjadi JPEG bytes, opsional diperkecil ke ukuran sisi."""
    g = gambar.convert("RGB")
    if sisi:
        g.thumbnail((sisi, sisi))
    buf = io.BytesIO()
    g.save(buf, format="JPEG", quality=85)
    return buf.getvalue()


def dampak_bulan_ini(awalan=None):
    """Estimasi dari asumsi di atas: (kg sampah, kg CO2 dicegah, ekuivalen pohon)."""
    awalan = datetime.now().strftime("%Y-%m") if awalan is None else awalan
    kg = co2 = 0.0
    for r in db.statistik(awalan):
        k = r["label"].lower()
        berat = BERAT_KG_PER_FOTO.get(k, 0.1) * r["jumlah"]
        kg += berat
        co2 += berat * CO2_KG_PER_KG.get(k, 1.0)
    return kg, co2, co2 / CO2_KG_PER_POHON


def kartu_kategori(k, panduan=True):
    """Menampilkan kartu informasi kategori dan tips penanganannya."""
    html = (f'<div class="kat" style="border-left: 8px solid {k["warna"]}">'
            f'<b style="color:{ui.teks_aksen(k["warna"])}; font-size:1.1rem">{escape(k["nama"])}</b>'
            f'<div>{escape(k["deskripsi"])}</div>'
            f'<div class="kecil" style="margin-top:6px"><b>Contoh:</b> {escape(k["contoh"])}</div>')
    if panduan:
        html += "<div style='margin-top:8px'><b>Cara menangani</b></div><ul>"
        html += "".join(f"<li>{escape(t)}</li>" for t in k["tips"]) + "</ul>"
    h(html + "</div>")


def kartu_misi(m):
    """Menampilkan progres satu misi beserta tombol klaim jika sudah selesai."""
    persen = min(m["progres"] / m["target"], 1) * 100
    with st.container(key=f"kartu_misi_{m['kode']}"):
        h(f'<span class="chip mint">{escape(m["jenis"])}</span> <span class="chip peach">+{m["poin"]} poin</span>'
          f'<div style="font-size:1.15rem; font-weight:800; margin-top:6px">{escape(m["nama"])}</div>'
          f'<div class="kecil">{escape(m["deskripsi"])}</div><div class="bar"><i style="width:{persen:.0f}%"></i></div>'
          f'<div class="kecil" style="display:flex; justify-content:space-between"><span>Progress</span>'
          f'<b>{min(m["progres"], m["target"])} / {m["target"]}</b></div>')
        if m["diklaim"]:
            st.success("Poin sudah diklaim.")
        elif m["selesai"]:
            st.button(f"Klaim +{m['poin']} poin", key=f"klaim_{m['kode']}", on_click=db.klaim_misi, args=(m["kode"],))


def navigasi():
    """Menampilkan navigasi bawah dan menandai layar yang sedang aktif."""
    if st.session_state.layar == "mulai":
        return
    aktif = "pindai" if st.session_state.layar == "hasil" else st.session_state.layar
    menu = [("beranda", "Beranda"), ("panduan", "Panduan"), ("pindai", "Pindai"), ("misi", "Misi"),
            ("riwayat", "Riwayat")]
    with st.container(key="nav"):
        for kol, (kode, label) in zip(st.columns(5), menu):
            with kol:
                st.button(label, key=f"nav_{kode}", type="primary" if kode == aktif else "secondary",
                          on_click=pindah, args=(kode,))


# ---------- Layar awal ----------
def layar_mulai():
    """Menampilkan pengenalan kategori dan pintasan ke pindai atau panduan."""
    h(ui.html_tiga_tong())
    h('<div class="tampil" style="font-size:2.1rem; line-height:1.1; margin:22px 0 8px">Sampah ini masuk tong yang mana?</div>'
      '<div class="kecil" style="font-size:1rem; margin-bottom:18px">Foto satu benda. Aplikasi menunjukkan tongnya '
      'dan cara menanganinya, tanpa internet.</div>')
    kategori_awal = st.session_state.get("kategori_awal", "Organik")
    pilihan_kategori = {
        "Organik": "Sisa makanan dan daun biasanya dapat diolah menjadi kompos.",
        "Anorganik": "Kertas, kaca, logam, dan plastik sebaiknya dipilah sesuai jenis bahannya.",
        "B3": "Baterai dan bahan berbahaya perlu dipisahkan. Ikuti petunjuk label atau pengelola setempat.",
    }
    kolom_kategori = st.columns(3)
    for kolom, kategori in zip(kolom_kategori, pilihan_kategori):
        with kolom:
            st.button(
                kategori,
                key=f"pilih_kategori_awal_{kategori.lower()}",
                type="primary" if kategori == kategori_awal else "secondary",
                on_click=pilih_kategori_awal,
                args=(kategori,),
                use_container_width=True,
            )
    with st.container(key="info_kategori_awal"):
        h(f'<div class="lav"><b>{escape(kategori_awal)}</b><div>{escape(pilihan_kategori[kategori_awal])}</div></div>')
    if kategori_awal == "B3":
        st.caption("AI hanya memberi perkiraan kategori, bukan penilaian tingkat bahaya.")
    tombol_pindai, tombol_panduan = st.columns([2, 1])
    with tombol_pindai:
        st.button(
            "Mulai pindai",
            key="mulai_pindai_awal",
            type="primary",
            on_click=pindah,
            args=("pindai",),
            use_container_width=True,
        )
    with tombol_panduan:
        st.button(
            "Lihat panduan",
            key="panduan_dari_awal",
            on_click=pindah,
            args=("panduan",),
            use_container_width=True,
        )


# ---------- Beranda ----------
def layar_beranda():
    """Menampilkan ringkasan akun, poin, dampak, misi, dan aktivitas terbaru."""
    saldo = db.poin()["saldo"]
    h(f'<div style="display:flex; justify-content:space-between; align-items:center">'
      f'<div><b style="font-size:1.3rem">W-Sort</b><div class="kecil">Berjalan lokal, tanpa internet</div></div>'
      f'<span class="chip mint">{ui.ikon("daun", 16)} {saldo:,} poin</span></div>'.replace(",", "."))
    h(f'<div class="judul" style="margin-bottom:0">Halo, {escape(st.session_state.pengguna["nama"])}!</div>'
      '<div class="kecil" style="margin-bottom:12px">Pilah hari ini untuk bumi esok yang lebih asri.</div>')

    with st.container(key="banner"):
        h(f'<div style="display:flex; gap:12px; align-items:center; margin-bottom:14px"><div style="flex:1">'
          f'<div class="tampil" style="font-size:1.5rem; line-height:1.15">Sampah apa di tanganmu?</div>'
          f'<div style="opacity:0.9; margin-top:4px">Pindai benda untuk perkiraan kategori dan jenis bahannya.</div>'
          f'</div>{ui.html_lensa(76)}</div>')
        st.button("Pindai sampah", on_click=pindah, args=("pindai",))

    h('<div class="judul" style="margin-top:12px">Misi hari ini</div>')
    kartu_misi(db.daftar_misi()[0])

    kg, co2, pohon = dampak_bulan_ini()
    with st.container(key="kartu_dampak"):
        h('<div style="display:flex; justify-content:space-between"><b style="font-size:1.1rem">Dampak lingkunganmu</b>'
          '<span class="chip abu">Bulan ini</span></div>')
        with st.container(key="dampak_isi"):
            h(f'<div class="lav"><div class="kecil">Sampah terpilah bulan ini (estimasi)</div>'
              f'<div class="angka">{angka(kg)} <span style="font-size:1.1rem">kg</span></div></div>')
            a, b = st.columns(2)
            a.markdown(f'<div class="lav"><div class="kecil">Emisi Dicegah</div><div class="angka" style="font-size:1.4rem">'
                       f'{angka(co2)} kg</div><div class="kecil">CO₂ (estimasi)</div></div>', unsafe_allow_html=True)
            b.markdown(f'<div class="lav"><div class="kecil">Ekuivalen Pohon</div><div class="angka" style="font-size:1.4rem">'
                       f'{angka(pohon)}</div><div class="kecil">per tahun (estimasi)</div></div>', unsafe_allow_html=True)
            kiri, kanan = st.columns([3, 2])
            kiri.markdown(f'<div style="background:#FDE6CC; border-radius:18px; padding:12px 14px">'
                          f'<div class="kecil" style="color:#7A4A0B">Poin Keberlanjutan</div>'
                          f'<div class="angka" style="font-size:1.5rem; color:#7A4A0B">{saldo:,}</div></div>'.replace(",", "."),
                          unsafe_allow_html=True)
            with kanan:
                st.button("Tukar Hadiah", on_click=pindah, args=("misi",))
        h('<div class="kecil" style="margin-top:6px">Angka kg, CO₂, dan pohon adalah estimasi contoh dari asumsi sederhana, '
          'bukan hasil pengukuran.</div>')

    kategori = db.semua_kategori()
    kiri, kanan = st.columns([3, 1])
    kiri.markdown('<div class="judul">Panduan Kategori</div>', unsafe_allow_html=True)
    with kanan:
        st.button("Lihat semua", on_click=pindah, args=("panduan",))
    h("".join(f'<span class="chip" style="background:{k["warna"]}33; color:{ui.teks_aksen(k["warna"])}; margin-right:8px">'
              f'{escape(k["nama"])}</span>' for k in kategori))

    with st.container(key="kartu_aktivitas"):
        h('<b style="font-size:1.1rem">Aktivitas Terakhir</b>')
        terakhir = db.riwayat_terakhir(3)
        if not terakhir:
            h('<div class="kecil">Belum ada aktivitas. Pindai satu sampah dulu.</div>')
        for r in terakhir:
            thumb = (f'<img src="data:image/jpeg;base64,{base64.b64encode(r["gambar"]).decode()}">'
                     if r["gambar"] else '<div class="thumb"></div>')
            hari = "" if r["waktu"][:10] == datetime.now().strftime("%Y-%m-%d") else r["waktu"][5:10] + " "
            chip = (f'<span class="chip mint">+{db.POIN_PER_FOTO} poin</span>' if r["dikenali"]
                    else '<span class="chip peach">Bukan sampah · manusia</span>'
                    if r["label"].startswith("Manusia") else '<span class="chip peach">Belum yakin</span>')
            h(f'<div class="baris">{thumb}<div style="flex:1"><b>{escape(r["label"])}</b>'
              f'<div class="kecil">{hari}{r["waktu"][11:16]} WIB, yakin {r["keyakinan"]:.0%}</div></div>{chip}</div>')


# ---------- Pindai ----------
def layar_pindai():
    """Memilih sumber foto, menjalankan model, lalu menyimpan hasil klasifikasi."""
    try:
        labels_model = baca_label_model()
    except (OSError, ValueError) as e:
        st.error(f"Daftar kategori model tidak bisa dibaca: {e}")
        return
    h('<div class="judul">Klasifikasi Sampah</div>'
      '<div style="margin-bottom:10px"><span class="chip mint">● Model siap</span> '
      f'<span class="chip abu">{len(labels_model)} kategori model · 5 jenis bahan</span></div>')
    kategori_tersedia = {k["nama"]: k for k in db.semua_kategori()}
    ikon_kategori = {"Organik": "daun", "Anorganik": "botol", "B3": "bahaya"}
    kolom_kategori = st.columns(len(labels_model))
    for kolom, label in zip(kolom_kategori, labels_model):
        with kolom:
            kategori = kategori_tersedia.get(label)
            warna = kategori["warna"] if kategori else ui.BRAND
            ikon = ikon_kategori.get(label)
            with st.container(key=f"scan_category_{label.lower()}"):
                if ikon:
                    h(ui.ikon(ikon, 20, warna))
                h(f'<b>{escape(label)}</b><div class="kecil">Kategori sampah</div>')
    if "B3" in labels_model:
        st.warning(
            "Model memperkirakan kategori B3, bukan jenis atau tingkat bahayanya. "
            "Periksa label produk dan ikuti arahan pengelola setempat; jangan mengandalkan AI saja."
        )
    else:
        st.warning(
            "Jenis yang tersedia saat ini: karton, kaca, logam, kertas, dan plastik. "
            "Jenis sampah organik seperti daun belum dikenali secara spesifik; kategori B3 "
            "belum didukung model aktif."
        )
    with st.expander("Tips agar hasil lebih baik"):
        st.markdown("- Foto satu benda dari dekat dengan latar yang sederhana.\n"
                    "- Pastikan benda terlihat jelas, tidak tertutup, dan pencahayaan cukup.\n"
                    "- Jika kamera langsung tidak tersedia, pilih unggah foto.")
    k = st.session_state.kunci
    sumber = st.radio("Sumber foto", ["Foto / kamera HP", "Kamera otomatis", "Unggah foto"],
                      horizontal=True, label_visibility="collapsed")
    if sumber == "Kamera otomatis":
        st.caption("Kamera diproses oleh aplikasi. Akses hanya tersedia melalui localhost atau HTTPS.")
        layar_kamera_otomatis()
        return
    if sumber == "Unggah foto":
        file = st.file_uploader("Pilih foto", type=["jpg", "jpeg", "png"], key=f"unggah{k}")
    else:
        file = st.camera_input("Ambil foto", key=f"kamera{k}")
    if file is None:
        return

    gambar = ImageOps.exif_transpose(Image.open(file))  # luruskan foto ponsel yang miring
    st.image(gambar)
    if st.button("Klasifikasi sekarang", type="primary"):
        try:
            with st.spinner("Memuat model klasifikasi dan deteksi objek..."):
                model, labels = muat_model()
                model_material = muat_model_material()
                detektor = muat_detektor_objek()
        except Exception as e:
            st.error("Model klasifikasi atau deteksi tidak bisa dimuat. Pastikan model kategori, jenis bahan, "
                     "dan deteksi tersedia di folder model/.")
            st.exception(e)
            return
        with st.spinner("Mendeteksi manusia dan mengklasifikasikan semua objek..."):
            t0 = time.perf_counter()
            klasifikasi = klasifikasi_multi(
                gambar, model, labels, detektor, model_material
            )
            st.session_state.scan_ms = int((time.perf_counter() - t0) * 1000)
        simpan_hasil_multi(gambar, klasifikasi, file.name)
        st.session_state.layar = "hasil"
        st.rerun()
    st.button("Ganti gambar", on_click=ganti_gambar)


def layar_kamera_otomatis():
    """Menjalankan kamera WebRTC dan menampilkan hasil deteksi yang stabil."""
    try:
        import threading
        folder_paket_proyek = os.path.join(
            os.path.dirname(os.path.abspath(__file__)), "venv", "Lib", "site-packages"
        )
        if os.path.isdir(folder_paket_proyek) and folder_paket_proyek not in sys.path:
            sys.path.insert(0, folder_paket_proyek)
        from streamlit_webrtc import VideoProcessorBase, WebRtcMode, webrtc_streamer
    except ImportError:
        st.error("Paket kamera otomatis belum tersedia di Python yang sedang menjalankan aplikasi.")
        st.info(f"Python aktif: `{sys.executable}`. Tutup server lama, lalu jalankan "
                "**Jalankan PilahPintar.bat** dari folder proyek untuk memasang paket kamera.")
        return

    try:
        with st.spinner("Memuat model AI..."):
            model, labels = muat_model()
            model_material = muat_model_material()
            detektor = muat_detektor_objek()
    except Exception as e:
        st.error("Model klasifikasi atau deteksi tidak bisa dimuat. Pastikan model kategori, jenis bahan, "
                 "dan deteksi tersedia di folder model/.")
        st.exception(e)
        return

    durasi_tangkap = st.slider(
        "Tunggu sebelum hasil otomatis diambil (detik)",
        min_value=5,
        max_value=20,
        value=10,
        help="Kamera menunggu benda terlihat stabil selama durasi ini sebelum membuka hasil.",
        key="durasi_scan_otomatis",
    )

    class PemrosesKamera(VideoProcessorBase):
        """Mengelola analisis frame, deteksi manusia, dan kestabilan objek."""

        JEDA_PREDIKSI = 1.5
        JUMLAH_STABIL = max(5, int(durasi_tangkap / JEDA_PREDIKSI) + 1)
        DURASI_STABIL = float(durasi_tangkap)
        DURASI_MANUSIA_STABIL = 2.0

        def __init__(self):
            """Menyiapkan status dan kunci sinkronisasi untuk pemrosesan video."""
            self.kunci = threading.Lock()
            self.pemindaian_aktif = False
            self.abaikan_deteksi_manusia = False
            self.hasil_terbaru = None
            self.hasil_stabil = None
            self.ringkasan_sebelumnya = None
            self.jumlah_stabil = 0
            self.mulai_stabil = None
            self.mulai_deteksi_manusia = None
            self.waktu_prediksi = 0.0
            self.analisis_berjalan = False
            self.error = None

        def mulai_scan(self, durasi):
            """Memulai pemindaian dan mengatur durasi stabilisasi objek."""
            with self.kunci:
                self.DURASI_STABIL = float(durasi)
                self.JUMLAH_STABIL = max(
                    5, int(self.DURASI_STABIL / self.JEDA_PREDIKSI) + 1
                )
                self.pemindaian_aktif = True
                self.abaikan_deteksi_manusia = False
                self.hasil_terbaru = None
                self.hasil_stabil = None
                self.ringkasan_sebelumnya = None
                self.jumlah_stabil = 0
                self.mulai_stabil = None
                self.mulai_deteksi_manusia = None
                self.waktu_prediksi = 0.0
                self.error = None

        def lanjutkan_scan_barang(self):
            """Melanjutkan klasifikasi barang saat pengguna ikut terlihat kamera."""
            with self.kunci:
                self.abaikan_deteksi_manusia = True
                self.hasil_terbaru = None
                self.hasil_stabil = None
                self.ringkasan_sebelumnya = None
                self.jumlah_stabil = 0
                self.mulai_stabil = None
                self.mulai_deteksi_manusia = None
                self.waktu_prediksi = 0.0
                self.error = None

        def recv(self, frame):
            """Menerima frame kamera dan menjadwalkan analisis berkala."""
            sekarang = time.monotonic()
            with self.kunci:
                if (not self.pemindaian_aktif or self.analisis_berjalan
                        or sekarang - self.waktu_prediksi < self.JEDA_PREDIKSI):
                    return frame
                self.analisis_berjalan = True
                self.waktu_prediksi = sekarang

            try:
                gambar = Image.fromarray(frame.to_ndarray(format="rgb24"))
                gambar_analisis = gambar.copy()
                gambar_analisis.thumbnail((640, 480), Image.Resampling.BILINEAR)
                threading.Thread(
                    target=self._analisis, args=(gambar_analisis, gambar), daemon=True
                ).start()
            except Exception as e:
                with self.kunci:
                    self.error = str(e)
                    self.hasil_stabil = None
                    self.analisis_berjalan = False
            return frame

        def _analisis(self, gambar, foto_asli):
            """Menganalisis satu frame dan menyimpan kandidat yang sudah stabil."""
            try:
                with self.kunci:
                    abaikan_deteksi_manusia = self.abaikan_deteksi_manusia
                klasifikasi = klasifikasi_multi(
                    gambar, model, labels, detektor, model_material,
                    fallback_tanpa_deteksi=abaikan_deteksi_manusia,
                    jumlah_maksimal_objek=3,
                    abaikan_deteksi_manusia=abaikan_deteksi_manusia,
                )
                sekarang = time.monotonic()
                with self.kunci:
                    self.error = None
                    if klasifikasi["manusia"]:
                        manusia = max(
                            klasifikasi["manusia"], key=lambda obj: obj["keyakinan_deteksi"]
                        )
                        if self.mulai_deteksi_manusia is None:
                            self.mulai_deteksi_manusia = sekarang
                        durasi_manusia = sekarang - self.mulai_deteksi_manusia
                        self.hasil_terbaru = {
                            "manusia": True,
                            "skor": manusia["keyakinan_deteksi"],
                            "durasi": durasi_manusia,
                        }
                        self.hasil_stabil = None
                        return

                    self.mulai_deteksi_manusia = None
                    ringkasan = tuple(item["label"] for item in klasifikasi["item"])
                    if ringkasan and ringkasan == self.ringkasan_sebelumnya:
                        self.jumlah_stabil += 1
                    elif ringkasan:
                        self.ringkasan_sebelumnya = ringkasan
                        self.jumlah_stabil = 1
                        self.mulai_stabil = sekarang
                        self.hasil_stabil = None
                    else:
                        self.ringkasan_sebelumnya = None
                        self.jumlah_stabil = 0
                        self.mulai_stabil = None
                        self.hasil_stabil = None
                    durasi = sekarang - self.mulai_stabil if self.mulai_stabil else 0
                    self.hasil_terbaru = {
                        "manusia": False,
                        "item": klasifikasi["item"],
                        "jumlah_stabil": self.jumlah_stabil,
                        "durasi": durasi,
                    }
                    if (self.jumlah_stabil >= self.JUMLAH_STABIL
                            and durasi >= self.DURASI_STABIL and self.hasil_stabil is None):
                        self.hasil_stabil = {
                            "manusia": False,
                            "gambar": jpeg(foto_asli, 1280),
                            "klasifikasi": klasifikasi,
                        }
            except Exception as e:
                with self.kunci:
                    self.error = str(e)
                    self.hasil_stabil = None
            finally:
                with self.kunci:
                    self.analisis_berjalan = False

    sesi = webrtc_streamer(
        key="kamera_sampah_otomatis",
        mode=WebRtcMode.SENDRECV,
        video_processor_factory=PemrosesKamera,
        media_stream_constraints={
            "video": {
                "facingMode": "environment",
                "width": {"ideal": 1280},
                "height": {"ideal": 720},
                "frameRate": {"ideal": 20, "max": 20},
            },
            "audio": False,
        },
        desired_playing_state=True,
        media_toggle_controls=False,
        async_processing=True,
        video_receiver_size=1,
        video_html_attrs={
            "autoPlay": True,
            "playsInline": True,
            "style": {
                "width": "100%",
                "height": "auto",
                "objectFit": "contain",
                "borderRadius": "16px",
            },
        },
    )
    st.markdown(
        '<div style="background:#EAF3EE;border:1px solid #D5E5D9;border-radius:16px;'
        'padding:12px 16px;margin:8px 0 12px">'
        '<b>Scan banyak benda sekaligus</b><div class="kecil">Video kamera ditampilkan langsung; '
        'AI mulai menganalisis setelah tombol ditekan. Hasil diambil setelah daftar benda stabil '
        f'selama {durasi_tangkap} detik. Persentase adalah keyakinan model, bukan jaminan akurasi.</div></div>',
        unsafe_allow_html=True,
    )
    if not sesi.state.playing or sesi.video_processor is None:
        st.info("Kamera sedang dimulai otomatis. Izinkan akses kamera di browser jika diminta. "
                "Jika kamera tidak aktif, pastikan izinnya diaktifkan lalu muat ulang halaman.")
        return

    @st.fragment(run_every="1.5s")
    def perbarui_hasil_kamera():
        """Memperbarui progres kamera serta membuka hasil ketika objek stabil."""
        pemroses = sesi.video_processor
        with pemroses.kunci:
            kesalahan = pemroses.error
            hasil_terbaru = pemroses.hasil_terbaru
            hasil_stabil = pemroses.hasil_stabil
            pemindaian_aktif = pemroses.pemindaian_aktif

        if kesalahan:
            st.error(f"Kamera gagal menganalisis gambar: {kesalahan}")
            return
        if not pemindaian_aktif:
            st.info("Arahkan kamera ke sampah, pastikan benda terlihat jelas, lalu mulai deteksi saat siap.")
            st.button(
                "Mulai deteksi",
                type="primary",
                key="mulai_deteksi_kamera",
                on_click=pemroses.mulai_scan,
                args=(durasi_tangkap,),
            )
            return
        if hasil_terbaru and hasil_terbaru["manusia"]:
            st.warning(
                f"Manusia terdeteksi ({hasil_terbaru['skor']:.0%}, ambang "
                f"{AMBANG_DETEKSI_MANUSIA:.0%}). Jika Anda sedang menunjukkan barang, "
                "dekatkan barang ke kamera lalu lanjutkan klasifikasi."
            )
            st.caption(
                f"Konfirmasi deteksi: "
                f"{min(hasil_terbaru['durasi'] / pemroses.DURASI_MANUSIA_STABIL, 1.0):.0%}. "
                "Ini status konfirmasi, bukan skor AI."
            )
            st.progress(min(
                hasil_terbaru["durasi"] / pemroses.DURASI_MANUSIA_STABIL, 1.0
            ))
            st.button(
                "Saya sedang menunjukkan barang — lanjutkan",
                key="lanjutkan_scan_barang",
                on_click=pemroses.lanjutkan_scan_barang,
                help="Akan mencoba mengklasifikasikan objek di foto meski manusia terlihat.",
            )
            st.caption(
                "Jika detektor tidak menemukan barang terpisah, AI memakai seluruh foto; "
                "wajah dan latar dapat memengaruhi hasil."
            )
        elif hasil_terbaru and hasil_terbaru["item"]:
            st.info(f"Objek kandidat sampah terdeteksi: **{len(hasil_terbaru['item'])}**.")
            st.caption(
                f"Menunggu benda stabil: {hasil_terbaru['durasi']:.0f} dari "
                f"{durasi_tangkap} detik"
            )
            st.progress(min(hasil_terbaru["durasi"] / durasi_tangkap, 1.0))
            baris_grafik = []
            for nomor, item in enumerate(hasil_terbaru["item"], 1):
                baris = {
                    "Benda": f"Benda {nomor}: {item['label']}",
                    "Keyakinan kategori AI (%)": item["skor"] * 100,
                }
                if item["keyakinan_deteksi"] is not None:
                    baris["Keyakinan deteksi objek (%)"] = item["keyakinan_deteksi"] * 100
                baris_grafik.append(baris)
            st.caption("Grafik persentase keyakinan untuk setiap benda yang terdeteksi:")
            st.bar_chart(pd.DataFrame(baris_grafik).set_index("Benda"))
        elif hasil_terbaru:
            st.warning("Belum ada objek sampah yang dikenali. Arahkan kamera ke barang bekas atau kemasan.")
        else:
            st.info("Deteksi aktif · arahkan kamera ke beberapa benda sampah.")

        if hasil_stabil:
            simpan_hasil_multi(
                Image.open(io.BytesIO(hasil_stabil["gambar"])),
                hasil_stabil["klasifikasi"],
                "kamera_langsung.jpg",
            )
            st.session_state.layar = "hasil"
            st.rerun()

    perbarui_hasil_kamera()


# ---------- Hasil + koreksi ----------
def tandai(nilai):
    """Menyimpan koreksi kategori untuk hasil tunggal yang sedang dibuka."""
    hs = st.session_state.hasil
    db.set_koreksi(hs["id"], nilai)
    hs["koreksi"] = nilai


def tandai_batch(id_riwayat, nilai):
    """Menyimpan koreksi kategori untuk satu objek dalam hasil banyak benda."""
    hs = st.session_state.hasil
    db.set_koreksi(id_riwayat, nilai)
    for item in hs["items"]:
        if item["id"] == id_riwayat:
            item["koreksi"] = nilai
            break


def tandai_jenis(id_riwayat, nilai):
    """Menyimpan koreksi jenis bahan dan memperbarui data sesi yang tampil."""
    db.set_koreksi_jenis(id_riwayat, nilai)
    hs = st.session_state.hasil
    if hs.get("batch"):
        for item in hs["items"]:
            if item["id"] == id_riwayat:
                item["koreksi_jenis"] = nilai
                break
    elif hs.get("id") == id_riwayat:
        hs["koreksi_jenis"] = nilai


def opsi_penanganan(label):
    """Memilih status penanganan yang sesuai dengan kategori sampah."""
    umum = ["Belum ditangani", "Sudah dipilah"]
    if label.lower() == "organik":
        return umum + ["Sudah dikomposkan"]
    if label.lower() == "b3":
        return umum + ["Disimpan terpisah dengan aman", "Sudah diserahkan ke pengelola"]
    return umum + ["Sudah disetor"]


def simpan_penanganan(id_riwayat, nilai, berat_gram):
    """Menyimpan status dan berat opsional untuk satu hasil scan."""
    berat_gram = berat_gram or None
    db.set_penanganan(id_riwayat, nilai, berat_gram)
    for item in st.session_state.hasil.get("items", []):
        if item["id"] == id_riwayat:
            item["penanganan"] = nilai
            item["berat_gram"] = berat_gram
            break
    st.toast("Status penanganan disimpan.")


def layar_hasil_multi(hs):
    """Menampilkan hasil scan banyak benda, koreksi, dan catatan penanganan."""
    st.image(hs["gambar"], use_container_width=True)
    labels_model = baca_label_model()
    peringatan_b3 = (
        "Kategori B3 hanya perkiraan AI, bukan identifikasi jenis atau tingkat bahaya. "
        "Ikuti label produk dan panduan pengelola setempat."
        if "B3" in labels_model else
        "B3 belum didukung oleh model aktif; jangan mengandalkan hasil AI untuk mengenali limbah berbahaya."
    )
    st.warning(
        "Pengenalan jenis anorganik tersedia untuk karton, kaca, logam, kertas, dan plastik. "
        f"Jenis organik belum tersedia. {peringatan_b3}"
    )
    if hs["manusia"]:
        if st.session_state.get("notif_manusia_id") != hs["id"]:
            st.toast(
                f"Manusia terdeteksi dengan keyakinan {hs['keyakinan_manusia']:.0%}. "
                "Scan sampah dibatalkan.",
                icon="⚠️",
            )
            st.session_state.notif_manusia_id = hs["id"]
        st.error(
            f"Deteksi manusia terkonfirmasi. Keyakinan model "
            f"{hs['keyakinan_manusia']:.0%} memenuhi ambang minimal "
            f"{AMBANG_DETEKSI_MANUSIA:.0%}; scan dibatalkan."
        )
        st.metric("Konfirmasi ambang deteksi", "100%")
        st.caption(
            f"Deteksi mencapai ambang minimal {AMBANG_DETEKSI_MANUSIA:.0%}. "
            f"Skor keyakinan asli model: {hs['keyakinan_manusia']:.0%}; "
            "100% di atas menunjukkan proses konfirmasi selesai, bukan skor AI. "
            "Foto ini tidak dihitung sebagai sampah dan tidak mendapat poin."
        )
    elif hs["kosong"]:
        st.warning("Tidak ada objek sampah yang didukung berhasil dideteksi pada gambar.")
        st.caption("Detektor saat ini mendukung objek seperti botol, gelas, makanan, kemasan, buku, dan elektronik. "
                   "Objek lain mungkin belum terdeteksi.")
    else:
        jumlah_yakin = sum(item["dikenali"] for item in hs["items"])
        st.success(
            f"Terdeteksi {len(hs['items'])} benda · {jumlah_yakin} klasifikasi cukup yakin · "
            f"+{jumlah_yakin * db.POIN_PER_FOTO} poin"
        )
        for nomor, item in enumerate(hs["items"], 1):
            jenis_terkonfirmasi = item.get("koreksi_jenis")
            nama_hasil = (
                f'{item["label"]} · {jenis_terkonfirmasi}' if jenis_terkonfirmasi
                else item["label"]
            )
            with st.container(key=f"hasil_objek_{item['id']}"):
                kiri, kanan = st.columns([1, 2])
                with kiri:
                    st.image(item["gambar"], use_container_width=True)
                with kanan:
                    st.subheader(f"Benda {nomor}: {nama_hasil}")
                    if item["dikenali"]:
                        if item["keyakinan_deteksi"] is None:
                            st.success(f"Keyakinan AI {item['skor']:.0%} · klasifikasi seluruh foto")
                        else:
                            st.success(
                                f"Keyakinan AI {item['skor']:.0%} · "
                                f"deteksi objek {item['keyakinan_deteksi']:.0%}"
                            )
                        if item.get("jenis"):
                            st.caption(
                                f"Perkiraan jenis dari AI: {item['jenis']} · keyakinan "
                                f"{item['skor_jenis']:.0%}"
                            )
                        if jenis_terkonfirmasi:
                            st.success(
                                f"Jenis dikoreksi pengguna: {jenis_terkonfirmasi}."
                            )
                    else:
                        st.warning("Belum yakin kategori sampahnya. Benda ini tidak menambah poin.")
                    kategori = db.ambil_kategori(item["label"])
                    if kategori:
                        tindakan = {
                            "organik": "Pisahkan dari kemasan; olah menjadi kompos jika memungkinkan.",
                            "anorganik": "Kosongkan, bilas, keringkan, lalu pilah berdasarkan jenis bahan.",
                            "b3": "Jangan buang ke tong biasa. Simpan tertutup dan serahkan ke titik pengumpulan B3.",
                        }.get(
                            kategori["nama"].lower(),
                            kategori["tips"][0] if kategori["tips"] else kategori["deskripsi"],
                        )
                        st.markdown(f"**Langkah berikutnya:** {tindakan}")
                        if kategori["nama"].lower() == "b3":
                            st.error("Sampah B3 tidak boleh dibuang ke tempat sampah biasa.")
                    if item["koreksi"]:
                        st.caption(f"Koreksi tersimpan: {item['koreksi']}.")
                    else:
                        with st.expander("Koreksi hasil ini"):
                            pilihan = st.selectbox(
                                "Kategori yang benar",
                                [x["nama"] for x in db.semua_kategori()],
                                key=f"pilih_koreksi_batch_{item['id']}",
                            )
                            st.button(
                                "Simpan koreksi",
                                key=f"simpan_koreksi_batch_{item['id']}",
                                on_click=tandai_batch,
                                args=(item["id"], pilihan),
                            )
                    if item["label"].lower() == "anorganik":
                        with st.expander("Konfirmasi atau koreksi jenis bahan"):
                            st.caption(
                                "Jenis AI hanya perkiraan. Pilihan Anda disimpan terpisah "
                                "dan tidak mengubah prediksi model."
                            )
                            pilihan_koreksi_jenis = [None, *OPSI_KOREKSI_JENIS]
                            pilihan_jenis = st.selectbox(
                                "Jenis bahan yang benar",
                                pilihan_koreksi_jenis,
                                format_func=lambda nilai: nilai or "Pilih jenis bahan",
                                index=(
                                    pilihan_koreksi_jenis.index(jenis_terkonfirmasi)
                                    if jenis_terkonfirmasi in OPSI_KOREKSI_JENIS
                                    else 0
                                ),
                                key=f"pilih_koreksi_jenis_{item['id']}",
                            )
                            st.button(
                                "Simpan koreksi jenis",
                                key=f"simpan_koreksi_jenis_{item['id']}",
                                on_click=tandai_jenis,
                                args=(item["id"], pilihan_jenis),
                                disabled=pilihan_jenis is None,
                            )
                    with st.expander("Catat penanganan sampah"):
                        st.caption("Catatan ini tidak menambah poin dan tidak mengubah hasil AI.")
                        label_penanganan = (
                            item["koreksi"]
                            if item["koreksi"] and item["koreksi"] != "benar"
                            else item["label"]
                        )
                        pilihan_status = opsi_penanganan(label_penanganan)
                        status_aktif = (
                            item["penanganan"] if item["penanganan"] in pilihan_status
                            else "Belum ditangani"
                        )
                        pilihan_penanganan = st.selectbox(
                            "Status penanganan",
                            pilihan_status,
                            index=pilihan_status.index(status_aktif),
                            key=f"pilih_penanganan_{item['id']}",
                        )
                        berat_gram = st.number_input(
                            "Berat (gram, opsional; isi 0 jika tidak dicatat)",
                            min_value=0.0,
                            value=float(item["berat_gram"] or 0),
                            step=10.0,
                            format="%.0f",
                            key=f"berat_penanganan_{item['id']}",
                        )
                        if st.button(
                            "Simpan catatan",
                            key=f"simpan_penanganan_{item['id']}",
                        ):
                            simpan_penanganan(
                                item["id"], pilihan_penanganan, berat_gram
                            )
    st.button("Scan lagi", type="primary", on_click=pindai_lagi)


def tingkat(skor):
    """Mengubah skor model menjadi label tingkat keyakinan untuk tampilan."""
    return "Sangat Tinggi" if skor >= 0.9 else "Tinggi" if skor >= 0.75 else "Cukup"


def layar_hasil():
    """Menampilkan hasil scan tunggal atau banyak benda beserta panduannya."""
    hs = st.session_state.get("hasil")
    if not hs:
        st.session_state.layar = "beranda"
        st.rerun()
    if hs.get("batch"):
        h('<div class="judul">Hasil scan multi-benda</div>')
        layar_hasil_multi(hs)
        return
    h('<div class="judul">Hasil analisis</div>')
    k = db.ambil_kategori(hs["label"]) if hs["dikenali"] else None
    st.image(hs["gambar"])
    warna = k["warna"] if k else ui.BRAND
    status_hasil = ("hasil-status" if hs["dikenali"] else "hasil-status hasil-status-ragu")
    judul_hasil = "Klasifikasi berhasil!" if hs["dikenali"] else "Perlu foto yang lebih jelas"
    nama_hasil = (
        f'{hs["label"]} · {hs["koreksi_jenis"]}' if hs.get("koreksi_jenis")
        else hs["label"]
    )
    deskripsi_hasil = (
        f'Sampah terdeteksi sebagai {escape(nama_hasil)}.' if hs["dikenali"]
        else f'Perkiraan kategori: {escape(hs["label"])}. Keyakinan model belum cukup.'
    )
    jenis_catatan = (
        "Keyakinan kategori belum cukup untuk menampilkan jenis."
        if not hs["dikenali"] else
        "Jenis bahan tersedia untuk karton, kaca, logam, kertas, dan plastik."
        if hs["label"] == "Anorganik" else
        "Kategori B3 hanya perkiraan AI; periksa label produk dan panduan pengelola setempat."
        if hs["label"] == "B3" else
        "Jenis organik seperti daun belum didukung model."
    )
    jenis_html = (
        f'<div class="hasil-score-content">{ui.html_cincin(hs["skor_jenis"], warna)}'
        f'<div><b>{escape(hs["jenis"])}</b><div class="kecil">Jenis bahan</div></div></div>'
        if hs.get("jenis") else
        '<div class="hasil-type-unknown">Belum dikenali</div>'
        f'<div class="hasil-type-note">{jenis_catatan}</div>'
    )
    h(f'<div class="{status_hasil}"><div class="hasil-check">{"✓" if hs["dikenali"] else "!"}</div>'
      f'<div><b>{judul_hasil}</b><div class="kecil">{deskripsi_hasil}</div></div></div>')
    h('<div class="judul" style="margin-top:14px">Tingkat keyakinan</div>'
      '<div class="hasil-grid">'
      '<div class="hasil-score"><div class="hasil-score-head">Kategori</div>'
      f'<div class="hasil-score-content">{ui.html_cincin(hs["skor"], warna)}'
      f'<div><b>{escape(hs["label"])}</b><div class="kecil">Keyakinan AI</div></div></div></div>'
      '<div class="hasil-score"><div class="hasil-score-head">Perkiraan jenis AI</div>'
      f'{jenis_html}</div></div>')
    if hs["dikenali"]:
        h(f'<div style="margin-bottom:8px"><span class="chip peach">+{db.POIN_PER_FOTO} poin</span> '
          f'<span class="chip abu">Keyakinan {tingkat(hs["skor"]).lower()}</span></div>')
        if k:
            h(f'<div>{escape(k["deskripsi"])}</div><div class="kecil" style="margin-top:4px">Contoh: {escape(k["contoh"])}</div>')
            if k["nama"].lower() == "b3":
                st.error("Sampah B3 tidak boleh dibuang ke tempat sampah biasa.")
        else:
            st.info(f'Belum ada panduan untuk "{hs["label"]}" di database.')
    else:
        selisih = hs["semua"][0][1] - hs["semua"][1][1] if len(hs["semua"]) > 1 else hs["skor"]
        alasan = ("Skor AI masih rendah." if hs["skor"] < AMBANG else
                  "Skor dua kategori teratas terlalu berdekatan.")
        st.warning(f"Belum yakin: {alasan} Skor tertinggi {hs['skor']:.0%}, selisih "
                   f"dari kategori berikutnya {selisih:.0%}. Ulangi dengan satu benda, latar polos, "
                   "pencahayaan cukup, dan benda memenuhi sebagian besar gambar.")

    if hs["label"].lower() == "anorganik":
        if hs.get("jenis"):
            st.caption(
                f"Perkiraan jenis dari AI: {hs['jenis']} · keyakinan "
                f"{hs['skor_jenis']:.0%}. Tetap periksa benda aslinya."
            )
        if hs.get("koreksi_jenis"):
            st.success(f"Jenis dikoreksi pengguna: {hs['koreksi_jenis']}.")
        with st.expander("Konfirmasi atau koreksi jenis bahan"):
            st.caption(
                "Jenis AI hanya perkiraan. Pilihan Anda disimpan terpisah dan "
                "tidak mengubah prediksi model."
            )
            pilihan_koreksi_jenis = [None, *OPSI_KOREKSI_JENIS]
            pilihan_jenis = st.selectbox(
                "Jenis bahan yang benar",
                pilihan_koreksi_jenis,
                format_func=lambda nilai: nilai or "Pilih jenis bahan",
                index=(
                    pilihan_koreksi_jenis.index(hs["koreksi_jenis"])
                    if hs.get("koreksi_jenis") in OPSI_KOREKSI_JENIS
                    else 0
                ),
                key=f"pilih_koreksi_jenis_{hs.get('id', 'tunggal')}",
            )
            if hs.get("id") is not None:
                st.button(
                    "Simpan koreksi jenis",
                    key=f"simpan_koreksi_jenis_{hs['id']}",
                    on_click=tandai_jenis,
                    args=(hs["id"], pilihan_jenis),
                    disabled=pilihan_jenis is None,
                )
            else:
                st.info("Koreksi tersedia pada hasil scan yang tersimpan di riwayat.")

    with st.container(key="kartu_koreksi"):
        h('<b>Hasil deteksi kurang tepat?</b><div class="kecil">Koreksi disimpan sebagai bahan evaluasi '
          'akurasi dan dihitung untuk misi verifikasi. Model belum belajar ulang otomatis.</div>')
        if hs["koreksi"]:
            st.success("Jawaban Anda tersimpan." if hs["koreksi"] == "benar"
                       else f'Koreksi tersimpan: seharusnya {hs["koreksi"]}.')
        else:
            st.button("Hasil sudah benar", on_click=tandai, args=("benar",))
            with st.expander("Koreksi kategori"):
                pilihan = st.selectbox("Seharusnya apa?", [x["nama"] for x in db.semua_kategori()], key="pilih_koreksi")
                st.button("Simpan koreksi", on_click=tandai, args=(pilihan,))

    if k:
        h('<div class="judul" style="margin-bottom:0">Panduan Pengolahan</div>'
          '<div class="kecil">Langkah tepat agar sampah ditangani dengan benar.</div>')
        for no, teks in enumerate(k["tips"], 1):
            h(f'<div class="langkah"><div class="no">{no}</div><div>{escape(teks)}</div></div>')
    with st.expander("Skor tiap kategori"):
        for label, skor in hs["semua"]:
            st.progress(skor, text=f"{label}: {skor:.0%}")
    st.button(f"Selesai, dapat +{db.POIN_PER_FOTO} poin" if hs["dikenali"] else "Selesai",
              type="primary", on_click=pindah, args=("beranda",))
    st.button("Pindai lagi", on_click=pindai_lagi)


# ---------- Tantangan: poin, misi, hadiah ----------
GELAR = ["Pemula Hijau", "Pemilah Muda", "Pemilah Handal", "Pahlawan Hijau", "Legenda Hijau"]
POIN_PER_LEVEL = 500
KLASEMEN_CONTOH = [("Peserta A", "RW 03", 34.8), ("Peserta B", "RW 01", 29.2), ("Peserta C", "RW 05", 25.6)]


def level_info(didapat):
    """Menghitung level, gelar, progres, dan poin menuju level berikutnya."""
    lv = 1 + didapat // POIN_PER_LEVEL
    return lv, GELAR[min(lv - 1, len(GELAR) - 1)], (didapat % POIN_PER_LEVEL) / POIN_PER_LEVEL, POIN_PER_LEVEL - didapat % POIN_PER_LEVEL


def tukar(nama, harga):
    """Mencatat penukaran hadiah jika saldo poin mencukupi."""
    if db.poin()["saldo"] >= harga:
        db.tambah_penukaran(nama, harga)


def klaim_tantangan_mingguan():
    """Memproses klaim bonus mingguan dan menampilkan hasilnya."""
    if db.klaim_tantangan_mingguan():
        st.toast(f"Bonus tantangan mingguan +{db.POIN_TANTANGAN_MINGGUAN} poin berhasil diklaim!")
    else:
        st.warning("Bonus belum bisa diklaim. Pastikan target sudah tercapai dan belum diklaim minggu ini.")


def layar_misi():
    """Menampilkan misi harian, tantangan mingguan, level, dan katalog hadiah."""
    p = db.poin()
    lv, gelar, frac, sisa = level_info(p["didapat"])
    h(f'<div class="hero"><span class="chip" style="background:#FFFFFF33">Level {lv}</span>'
      f'<div style="margin-top:10px; font-size:0.8rem; opacity:0.85">Saldo terkumpul</div>'
      f'<div class="tampil" style="font-size:2.6rem; line-height:1.1">{p["saldo"]:,} <span style="font-size:1.1rem">Ecopoin</span></div>'
      f'<span class="chip" style="background:#FDE6CC; color:#7A4A0B">{gelar}</span>'
      f'<div class="bar" style="background:#FFFFFF44"><i style="width:{frac * 100:.0f}%; background:#FFFFFF"></i></div>'
      f'<div style="display:flex; justify-content:space-between; font-size:0.85rem">'
      f'<span>Level {lv}</span><span>{sisa} poin menuju Level {lv + 1}</span></div></div>'.replace(",", "."))
    tab_misi, tab_hadiah = st.tabs(["Misi dan tantangan", "Katalog hadiah"])

    with tab_misi:
        besok = datetime.combine(date.today() + timedelta(days=1), datetime.min.time())
        d = int((besok - datetime.now()).total_seconds())
        h(f'<div style="display:flex; justify-content:space-between; align-items:center; margin:8px 0">'
          f'<b style="font-size:1.3rem">Misi aktif</b>'
          f'<span class="chip" style="background:#EEF1FB">Reset dlm {d // 3600:02d}:{d % 3600 // 60:02d}:{d % 60:02d}</span></div>')
        for m in db.daftar_misi():
            kartu_misi(m)
        h(f'<div class="kecil">Aturan poin: +{db.POIN_PER_FOTO} untuk setiap foto yang berhasil dikenali. '
          'Poin misi masuk setelah diklaim.</div>')
        mingguan = db.tantangan_mingguan()
        mulai_minggu = date.fromisoformat(mingguan["mulai"])
        akhir_minggu = date.fromisoformat(mingguan["selesai"])
        with st.container(key="tantangan_mingguan"):
            st.subheader("Tantangan Mingguan")
            st.caption(
                f"{mulai_minggu.strftime('%d %b')}–{akhir_minggu.strftime('%d %b %Y')} · "
                f"Pindai 10 sampah yang dikenali untuk bonus +{mingguan['poin']} poin"
            )
            st.progress(
                min(mingguan["progres"] / mingguan["target"], 1.0),
                text=f"{min(mingguan['progres'], mingguan['target'])} dari {mingguan['target']} sampah dikenali",
            )
            if mingguan["kategori"]:
                st.write("Ringkasan minggu ini")
                kolom = st.columns(len(mingguan["kategori"]))
                for kolom_kategori, baris in zip(kolom, mingguan["kategori"]):
                    kolom_kategori.metric(baris["label"], baris["jumlah"])
            else:
                st.caption("Hasil scan yang belum yakin tidak dihitung dalam progres.")
            if mingguan["diklaim"]:
                st.success("Bonus tantangan minggu ini sudah diklaim.")
            elif mingguan["progres"] >= mingguan["target"]:
                st.button(
                    f"Klaim bonus +{mingguan['poin']} poin",
                    type="primary",
                    key="klaim_tantangan_mingguan",
                    on_click=klaim_tantangan_mingguan,
                )
            else:
                st.caption(f"Masih perlu {mingguan['target'] - mingguan['progres']} scan yang dikenali.")
        h('<div class="judul" style="margin-top:16px">Klasemen Komunitas</div>'
          '<div class="kecil">Peserta lain adalah data contoh. Angka Anda adalah estimasi kg bulan ini.</div>')
        baris = sorted(KLASEMEN_CONTOH + [("Kamu", "Perangkat ini", round(dampak_bulan_ini()[0], 1))], key=lambda x: -x[2])
        for no, (nama, wilayah, kg) in enumerate(baris, 1):
            h(f'<div class="baris" style="background:{"#D9F5E8" if nama == "Kamu" else "#EEF1FB"}"><b style="width:28px">#{no}</b>'
              f'<div style="flex:1"><b>{nama}</b><div class="kecil">{wilayah}</div></div><b>{angka(kg)} kg</b></div>')

    with tab_hadiah:
        st.caption("Daftar hadiah di bawah hanya contoh.")
        for nama, harga in HADIAH:
            a1, b1 = st.columns([3, 1])
            a1.markdown(f"**{nama}**  \n{harga} poin")
            b1.button("Tukar", key=f"tukar_{nama}", disabled=p["saldo"] < harga, on_click=tukar, args=(nama, harga))
        penukaran = db.riwayat_penukaran()
        if penukaran:
            st.subheader("Riwayat penukaran")
            st.dataframe(pd.DataFrame(penukaran), hide_index=True)


# ---------- Riwayat ----------
BULAN = ["Januari", "Februari", "Maret", "April", "Mei", "Juni", "Juli", "Agustus", "September", "Oktober",
         "November", "Desember"]


def label_tanggal(waktu):
    """Mengubah tanggal waktu riwayat menjadi label Hari ini/Kemarin/tanggal."""
    d = datetime.strptime(waktu[:10], "%Y-%m-%d").date()
    if d == date.today():
        return "Hari ini"
    if d == date.today() - timedelta(days=1):
        return "Kemarin"
    return f"{d.day} {BULAN[d.month - 1]} {d.year}"


def hapus_satu(id_riwayat):
    """Menghapus satu catatan riwayat dan menampilkan notifikasi."""
    db.hapus_riwayat(id_riwayat)
    st.toast("Riwayat dihapus.")


def minta_hapus_semua():
    """Meminta konfirmasi sebelum menghapus seluruh riwayat."""
    st.session_state.konfirmasi_hapus = True


def batal_hapus_semua():
    """Membatalkan konfirmasi penghapusan seluruh riwayat."""
    st.session_state.konfirmasi_hapus = False


def hapus_semua():
    """Menghapus seluruh riwayat dan membersihkan hasil dari sesi."""
    db.hapus_semua_riwayat()
    st.session_state.konfirmasi_hapus = False
    st.session_state.pop("hasil", None)
    st.toast("Semua riwayat dihapus.")


def baris_riwayat(r, warna_map):
    """Menyusun HTML untuk satu baris riwayat pemilahan."""
    thumb = (f'<img src="data:image/jpeg;base64,{base64.b64encode(r["gambar"]).decode()}">'
             if r["gambar"] else '<div class="thumb"></div>')
    w = warna_map.get(r["label"].lower(), "#0B6B4E")
    if r["label"].startswith("Manusia"):
        chip, poin = '<span class="chip peach">Bukan sampah · manusia</span>', ""
    elif r["dikenali"]:
        chip = f'<span class="chip" style="background:{w}33; color:{ui.teks_aksen(w)}">{escape(r["label"])}</span>'
        poin = f'<span class="chip peach">+{db.POIN_PER_FOTO} poin</span>'
    else:
        chip, poin = '<span class="chip peach">Belum yakin</span>', ""
    tag = ""
    if r["koreksi"] == "benar":
        tag = '<div class="kecil">Diverifikasi pengguna</div>'
    elif r["koreksi"]:
        tag = f'<div class="kecil">Dikoreksi pengguna: {escape(r["koreksi"])}</div>'
    koreksi_jenis = (
        f'<div class="kecil">Jenis dikoreksi pengguna: {escape(r["koreksi_jenis"])}</div>'
        if r.get("koreksi_jenis") else ""
    )
    berat = (
        f'<div class="kecil">Berat dicatat: {r["berat_gram"]:g} gram</div>'
        if r["berat_gram"] is not None else ""
    )
    return (f'<div class="baris">{thumb}<div style="flex:1; min-width:0"><b>{escape(r["label"])}</b> {poin}'
            f'<div>{chip} <span class="kecil">{r["waktu"][11:16]} WIB, yakin {r["keyakinan"]:.0%}</span></div>'
            f'<div class="kecil">Penanganan: {escape(r["penanganan"])}</div>'
            f'{berat}{tag}{koreksi_jenis}</div></div>')


def layar_riwayat():
    """Menampilkan statistik, filter, unduhan CSV, dan daftar riwayat."""
    h('<div class="judul">Riwayat & Log Pemilahan</div>')
    semua = db.ambil_riwayat(500)
    if not semua:
        st.write("Belum ada riwayat. Pindai satu sampah dulu.")
        return
    kategori = db.semua_kategori()
    warna_map = {k["nama"].lower(): k["warna"] for k in kategori}
    stat = db.statistik()
    total = sum(r["jumlah"] for r in stat)
    with st.container(key="dampak_isi"):
        c1, c2, c3 = st.columns(3)
        c1.markdown(f'<div class="lav"><div class="kecil">Total Pilah</div><div class="angka">{total}</div>'
                    f'<div class="kecil">foto dikenali</div></div>', unsafe_allow_html=True)
        c2.markdown(f'<div class="lav"><div class="kecil">Terkumpul</div><div class="angka">{angka(dampak_bulan_ini("")[0])}'
                    f'<span style="font-size:0.9rem"> kg</span></div><div class="kecil">estimasi</div></div>', unsafe_allow_html=True)
        dominan = f'{stat[0]["label"]}</div><div class="kecil">{stat[0]["jumlah"] / total:.0%} dari total' if stat else "-"
        c3.markdown(f'<div class="lav"><div class="kecil">Dominan</div><div class="angka" style="font-size:1.3rem">'
                    f'{dominan}</div></div>', unsafe_allow_html=True)
    benar, salah = db.akurasi_koreksi()
    if benar + salah:
        st.caption(f"Akurasi menurut koreksi pengguna: {benar / (benar + salah):.0%} ({benar} benar, {salah} salah)")
    ringkasan = db.ringkasan_penanganan()
    if ringkasan["total"]:
        st.caption(
            f"Sudah ditangani: {ringkasan['sudah_ditangani']} dari {ringkasan['total']} hasil · "
            f"berat tercatat: {angka(ringkasan['berat_gram'], 0)} gram "
            "(berdasarkan input pengguna, bukan estimasi AI)"
        )

    cari = st.text_input("Cari", placeholder="Cari kategori atau nama file...", label_visibility="collapsed")
    pilih_kat = st.radio("Kategori", ["Semua"] + [k["nama"] for k in kategori], horizontal=True,
                         label_visibility="collapsed", key="f_kategori")
    status_koreksi = st.radio("Status hasil", ["Semua log", "Dikoreksi", "Belum yakin"], horizontal=True,
                              label_visibility="collapsed", key="f_status")
    status_penanganan = st.radio(
        "Penanganan", ["Semua", "Belum ditangani", "Sudah ditangani"],
        horizontal=True, label_visibility="collapsed", key="f_penanganan",
    )
    data = [r for r in semua
            if (not cari or cari.lower() in
                f'{r["label"]} {r["nama_file"] or ""} {r.get("koreksi_jenis") or ""}'.lower())
            and (pilih_kat == "Semua" or r["label"] == pilih_kat)
            and (status_koreksi == "Semua log"
                 or (status_koreksi == "Belum yakin" and not r["dikenali"])
                 or (status_koreksi == "Dikoreksi" and r["koreksi"] and r["koreksi"] != "benar"))
            and (status_penanganan == "Semua"
                 or (status_penanganan == "Belum ditangani"
                     and r["penanganan"] == "Belum ditangani")
                 or (status_penanganan == "Sudah ditangani"
                     and r["penanganan"] != "Belum ditangani"))]
    if not data:
        st.info("Tidak ada riwayat yang cocok dengan filter.")

    with st.container(key="daftar_riwayat"):
        sebelumnya = None
        for r in data:
            tgl = label_tanggal(r["waktu"])
            if tgl != sebelumnya:
                n = sum(1 for x in data if label_tanggal(x["waktu"]) == tgl)
                h(f'<div class="kecil" style="display:flex; justify-content:space-between; margin-top:12px">'
                  f'<b>{tgl}</b><span>{n} aksi terdata</span></div>')
                sebelumnya = tgl
            kiri, kanan = st.columns([6, 1])
            kiri.markdown(baris_riwayat(r, warna_map), unsafe_allow_html=True)
            kanan.button("✕", key=f"hapus_{r['id']}", on_click=hapus_satu, args=(r["id"],), help="Hapus riwayat ini")

    with st.expander("Kelola riwayat"):
        df = pd.DataFrame(semua).drop(columns=["gambar"])
        df["keyakinan"] = (df["keyakinan"] * 100).round().astype(int).astype(str) + "%"
        df["dikenali"] = df["dikenali"].map({1: "Ya", 0: "Belum yakin"})
        st.download_button("Unduh riwayat (CSV)", df.to_csv(index=False).encode("utf-8"), "riwayat.csv", "text/csv")
        if st.session_state.get("konfirmasi_hapus"):
            st.warning("Semua riwayat dan fotonya akan dihapus. Poin dari foto-foto itu ikut berkurang. Lanjutkan?")
            ya, batal = st.columns(2)
            ya.button("Ya, hapus semua", type="primary", on_click=hapus_semua)
            batal.button("Batal", on_click=batal_hapus_semua)
        else:
            st.button("Hapus semua riwayat", on_click=minta_hapus_semua)


# ---------- Panduan ----------
def layar_panduan():
    """Menampilkan panduan kategori dan pencarian lokasi setor."""
    h('<div class="judul">Panduan Kategori</div>')
    semua = db.semua_kategori()
    for k in semua:
        kartu_kategori(k)

    st.subheader("Cari tempat setor")
    st.caption(
        "Cari bank sampah atau titik pengumpulan di Google Maps berdasarkan kota/kecamatan. "
        "Perlu internet. Lokasi yang diketik dikirim ke Google Maps saat tombol ditekan; "
        "aplikasi tidak memakai GPS atau menyimpan lokasi ke riwayat."
    )
    kolom_lokasi, kolom_jenis = st.columns([2, 1])
    lokasi = kolom_lokasi.text_input(
        "Kota atau kecamatan",
        placeholder="Contoh: Bandung, Coblong",
        key="lokasi_titik_setor",
    ).strip()
    jenis_setor = kolom_jenis.selectbox(
        "Yang ingin disetor",
        [
            "Bank sampah umum",
            "Kertas, plastik, dan kardus",
            "Elektronik dan baterai",
            "Limbah B3 rumah tangga",
            "Sampah organik / kompos",
        ],
        key="jenis_titik_setor",
    )
    if jenis_setor == "Limbah B3 rumah tangga":
        st.warning(
            "Hubungi pengelola atau dinas lingkungan hidup terlebih dahulu untuk memastikan "
            "lokasi menerima jenis B3 tersebut. Jangan mencampur B3 dengan sampah biasa."
        )
    if lokasi:
        kata_kunci = {
            "Bank sampah umum": "bank sampah",
            "Kertas, plastik, dan kardus": "daur ulang kertas plastik kardus bank sampah",
            "Elektronik dan baterai": "titik pengumpulan limbah elektronik baterai",
            "Limbah B3 rumah tangga": "titik pengumpulan limbah B3 rumah tangga",
            "Sampah organik / kompos": "pengolahan sampah organik kompos",
        }[jenis_setor]
        url_peta = (
            "https://www.google.com/maps/search/?api=1&query="
            + quote_plus(f"{kata_kunci} {lokasi}")
        )
        st.link_button("Buka hasil di Google Maps", url_peta, use_container_width=True)
        st.caption("Hasil peta perlu diperiksa kembali; pastikan jam buka dan jenis sampah yang diterima.")
    else:
        st.info("Masukkan kota atau kecamatan untuk mencari lokasi setor.")

    st.subheader("Tambah panduan")
    with st.form("tambah", clear_on_submit=True):
        nama = st.selectbox("Kategori", [k["nama"] for k in semua])
        teks_baru = st.text_input("Isi panduan")
        if st.form_submit_button("Simpan") and teks_baru.strip():
            db.tambah_panduan(nama, teks_baru.strip())
            st.success("Panduan disimpan. Pindah layar lalu kembali untuk melihatnya.")


if not st.session_state.get("pengguna"):
    layar_autentikasi()
    st.stop()

db.pakai_database_pengguna(st.session_state.pengguna["id"])
db.buat_tabel()
if not st.session_state.get("kode_pemulihan_diperiksa"):
    kode_pemulihan = db.buat_kode_pemulihan_jika_belum_ada(
        st.session_state.pengguna["id"]
    )
    st.session_state.kode_pemulihan_diperiksa = True
    if kode_pemulihan:
        st.session_state.kode_pemulihan_baru = kode_pemulihan
with st.container(key="akun"):
    kolom_pengguna, kolom_keluar = st.columns([4, 1])
    kolom_pengguna.caption(f"Masuk sebagai {st.session_state.pengguna['email']}")
    if kolom_keluar.button("Keluar", key="keluar"):
        keluar()
        st.rerun()
with st.expander("Keamanan akun"):
    st.caption("Membuat kode baru akan langsung membatalkan kode pemulihan sebelumnya.")
    if st.button("Buat kode pemulihan baru", key="buat_kode_pemulihan"):
        st.session_state.kode_pemulihan_baru = db.ganti_kode_pemulihan(
            st.session_state.pengguna["id"]
        )
tampilkan_kode_pemulihan()

{
    "mulai": layar_mulai, "beranda": layar_beranda, "panduan": layar_panduan, "pindai": layar_pindai,
    "hasil": layar_hasil, "misi": layar_misi, "riwayat": layar_riwayat,
}[st.session_state.layar]()
navigasi()