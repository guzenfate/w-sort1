# W-Sort Android (Kivy, offline)

Folder ini berisi aplikasi Android terpisah dari aplikasi Streamlit desktop.
Kamera, klasifikasi Organik/Anorganik, dan riwayat sederhana berjalan di
perangkat; APK tidak memerlukan server atau koneksi internet untuk scan.

## Fitur MVP

- Preview kamera langsung dengan resolusi ideal 1280x720.
- Tombol scan menganalisis satu gambar secara lokal.
- Klasifikasi dua kelas: Organik dan Anorganik.
- Hasil keyakinan rendah ditandai "Belum yakin".
- Riwayat scan disimpan di penyimpanan privat aplikasi.
- B3 tidak didukung karena dataset tidak memiliki gambar B3 berlabel.

UI Android ini belum membawa akun, misi, poin, scan multi-benda, atau deteksi
manusia dari aplikasi Streamlit.

## Build APK di Linux atau WSL2

Buildozer tidak dapat membangun APK langsung dari PowerShell/Windows. Jika WSL
belum ada, buka PowerShell sebagai Administrator lalu jalankan:

```powershell
wsl --install -d Ubuntu-22.04
```

Restart Windows jika diminta, selesaikan setup Ubuntu, lalu buka terminal Ubuntu:

```bash
sudo apt update
sudo apt install -y python3-pip python3-venv git zip unzip openjdk-17-jdk \
  autoconf libtool pkg-config zlib1g-dev libncurses5-dev libncursesw5-dev \
  libtinfo5 cmake libffi-dev libssl-dev
mkdir -p ~/PilahPintarAndroid
cp -r "/mnt/c/smart_waste_app - Salin/android_app/." ~/PilahPintarAndroid/
cd ~/PilahPintarAndroid
python3 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip setuptools wheel
pip install buildozer cython
buildozer android debug
```

Build pertama mengunduh Android SDK/NDK dan dependensi Gradle, jadi perlu
koneksi internet dan ruang disk yang cukup. Setelah selesai, APK debug berada
di folder `bin/`. Salin APK ke ponsel, izinkan instalasi dari sumber tersebut,
lalu pasang. Untuk memakai kamera, izinkan akses kamera ketika diminta.

Jika SDK/NDK yang dipilih Buildozer tidak kompatibel dengan lingkungan build,
gunakan Ubuntu LTS dan ikuti pesan versi yang direkomendasikan Buildozer; file
`buildozer.spec` dapat diperbarui tanpa mengubah kode aplikasi.

## Menjalankan di desktop untuk uji classifier

Kivy belum disertakan dalam virtual environment desktop proyek. Pasang Kivy
sesuai platform desktop, lalu dari folder ini jalankan `python main.py`.
Di desktop, kode menggunakan `tflite-runtime` bila tersedia atau
`tf.lite.Interpreter` dari TensorFlow yang telah dipasang.

## Melatih ulang model

Setelah mengganti model klasifikasi aktif, ekspor kembali aset Android dari
root proyek Windows:

```powershell
.\venv\Scripts\python.exe scripts\export_mobile_model.py
```

Salin ulang folder `android_app` ke WSL dan buat APK baru.
