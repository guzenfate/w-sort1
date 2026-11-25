# W-Sort

Aplikasi Streamlit untuk membantu memperkirakan kategori sampah Organik atau
Anorganik. Aplikasi dapat dijalankan di Windows atau di-host agar bisa dibuka
dari Chrome Android.

## Jalankan di Windows

Jalankan `Jalankan PilahPintar.bat`. Aplikasi terbuka di
`http://localhost:8502`.

## Host agar bisa dibuka di Android

Panduan ini memakai Streamlit Community Cloud. Hosting memberikan URL HTTPS
`streamlit.app`; pengguna membuka URL itu di Chrome Android dan dapat membuat
pintasan lewat menu Chrome **Tambahkan ke layar utama**. Ini adalah pintasan ke
aplikasi web, bukan APK native.

1. Pastikan dataset, database, file `user_data/`, virtualenv, dan rahasia lokal
   tidak masuk ke Git. Berkas-berkas ini tercantum di `.gitignore`.
2. Buat repository GitHub **private** menggunakan GitHub Desktop, pilih folder
   proyek ini, lalu commit dan push ke GitHub. Jangan push `venv/` atau folder
   `dataset/`; keduanya besar dan tidak dibutuhkan untuk menjalankan aplikasi.
3. Buka [share.streamlit.io](https://share.streamlit.io), masuk dengan GitHub,
   lalu pilih **Create app** dan repository yang baru di-push.
4. Pilih branch `main`, file utama `app.py`, lalu buka **Advanced settings** dan
   pilih **Python 3.11**. Versi ini diperlukan TensorFlow 2.15 yang dipakai
   proyek.
5. Tekan **Deploy** dan tunggu sampai Streamlit menampilkan URL aplikasi.
6. Buka URL tersebut di Chrome pada HP, izinkan akses kamera, lalu pilih
   **Foto / kamera HP**. Untuk membuat pintasan, buka menu Chrome (⋮) lalu
   **Tambahkan ke layar utama**.

Lihat [README model](model/README.md) untuk dukungan kategori dan batasan AI.

Dataset tiga kelas yang diekstrak ke `new dataset/archive (1)/` dapat diperiksa
dengan:

```powershell
.\venv\Scripts\python.exe scripts\train_three_class_model.py --inspect-only
```

Untuk melatih kandidat model Organik/Anorganik/B3, jalankan perintah yang sama
tanpa `--inspect-only`. Proses ini membaca `Dataset_ThirdStage`, dapat memakan
waktu, dan menyimpan model, metrik, serta label kandidat terpisah di `model/`.
Model aktif tidak diganti otomatis; tinjau metrik tiap kelas dan uji dengan foto
nyata sebelum mengaktifkannya. Lihat [README model](model/README.md) untuk
pemetaan kelas dan batasan klasifikasi B3.

Di menu **Panduan Kategori**, fitur **Cari tempat setor** membuka pencarian
Google Maps berdasarkan kota/kecamatan dan jenis sampah yang dipilih. Fitur ini
tidak meminta akses GPS atau menyimpan lokasi. Periksa langsung dengan pengelola
atau dinas setempat apakah lokasi menerima jenis sampah tersebut, terutama B3.

Pada hasil scan, pengguna juga dapat mencatat status penanganan. Pilihannya
disesuaikan dengan kategori: misalnya organik dapat ditandai sudah dikomposkan,
sedangkan B3 dapat ditandai disimpan aman atau diserahkan ke pengelola. Status
dan berat opsional (gram) tersimpan di riwayat dan dapat difilter atau diekspor
ke CSV. Rekap berat hanya menjumlahkan angka yang dimasukkan pengguna; angka itu
bukan estimasi AI. Catatan ini tidak menambah poin dan tidak melatih ulang model.

Untuk hasil Anorganik, jenis bahan dari AI ditampilkan sebagai perkiraan.
Pengguna dapat memilih koreksi jenis (karton, kaca, logam, kertas, plastik,
atau lainnya/belum tahu); koreksi disimpan terpisah dari prediksi AI dan muncul
di riwayat/ekspor CSV. Koreksi ini belum melatih ulang model.

Mode **Kamera otomatis** menunggu pengguna menekan **Mulai deteksi** setelah
benda siap di depan kamera. Durasi stabilisasi dapat dipilih 5–20 detik. Selama
deteksi berlangsung, grafik menampilkan persentase keyakinan AI dan detektor
objek; persentase keyakinan bukan jaminan akurasi.
Pratinjau meminta video hingga 720p pada 20 fps, sedangkan AI menganalisis gambar
yang diperkecil dan maksimal tiga benda per putaran agar kamera lebih responsif.
Jika manusia terdeteksi saat pengguna sedang memegang barang, tersedia tindakan
untuk melanjutkan klasifikasi. Bila barang tidak terdeteksi terpisah, seluruh
foto digunakan dan wajah/latar dapat memengaruhi hasil.

## Penting sebelum membagikan link

- Jangan masukkan `smartwaste.db`, `user_data/`, dataset, atau kredensial ke
  repository.
- SQLite bawaan menyimpan akun dan riwayat pada server aplikasi. Penyimpanan
  lokal Streamlit Community Cloud tidak dijamin persisten; data dapat hilang
  ketika aplikasi tidur, dibangun ulang, atau server diganti. Jangan gunakan
  akun/kata sandi penting atau data pribadi untuk uji publik. Untuk penggunaan
  sungguhan, database perlu dipindahkan ke layanan persisten yang sesuai.
- Jika lupa kata sandi, minta kode reset lewat tab **Lupa kata sandi**. Kode
  dikirim ke email terdaftar, berlaku 15 menit, dan hanya bisa digunakan sekali.
  Atur layanan SMTP melalui `.streamlit/secrets.toml` lokal (berkas ini
  diabaikan Git) atau **Settings > Secrets** di Streamlit Community Cloud:

  ```toml
  [smtp]
  host = "smtp.gmail.com"
  port = 587
  username = "alamat-pengirim@gmail.com"
  password = "app-password-email"
  sender = "alamat-pengirim@gmail.com"
  ```

  Gunakan app password dari penyedia email, bukan kata sandi utama akun email.
  Aplikasi memakai SMTP STARTTLS. Simpan juga kode pemulihan cadangan yang
  ditampilkan setelah mendaftar atau reset; kode ini bisa dipakai jika email
  tidak tersedia. Akun lama mendapat kode pemulihan saat masuk kembali setelah
  pembaruan.
- Model aktif bawaan membedakan Organik dan Anorganik; model tahap kedua dapat
  mengenali karton, kaca, logam, kertas, dan plastik. Skrip kandidat tiga kelas
  belum mengganti model aktif. Aplikasi Android native masih memakai
  klasifikasi dua kategori. Ikuti label produk dan panduan setempat untuk
  barang berbahaya; jangan jadikan hasil AI sebagai satu-satunya dasar
  penanganan B3.
- Kamera browser menggunakan koneksi HTTPS dan izin kamera. **Foto / kamera
  HP** memakai widget kamera browser; **Kamera otomatis** menggunakan WebRTC
  dan dapat bergantung pada konfigurasi jaringan/perangkat, jadi gunakan mode
  Foto jika mode otomatis tidak tersambung.
- Aplikasi versi web tidak benar-benar diubah menjadi APK. Aksesnya memerlukan
  internet selama aplikasi digunakan.

## Dependensi dan model

`requirements.txt` dipakai Streamlit Community Cloud. Model klasifikasi aktif
dan detektor objek di `model/` harus tetap disertakan di repository; database,
dataset, dan model eksperimen tidak perlu diunggah.
