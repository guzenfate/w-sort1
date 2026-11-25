# Model PilahPintar

## Klasifikasi sampah

`keras_model.h5` mengelompokkan foto menjadi **Organik** atau **Anorganik**.
Dataset lokal dilatih dengan pemetaan berikut:

- `DATASET/TRAIN/O` dan `DATASET/TEST/O` -> Organik.
- `DATASET/TRAIN/R`, `DATASET/TEST/R`, serta `cardboard`, `glass`, `metal`,
  `paper`, dan `plastic` -> Anorganik.
- `trash` tidak digunakan.

Untuk melatih ulang, letakkan dataset di folder `dataset/`, lalu jalankan:

```powershell
.\venv\Scripts\python.exe scripts\train_model.py
```

Skrip memakai data `TEST/O` dan `TEST/R`, serta menyisihkan 20% gambar dari
setiap kelas Garbage Classification untuk evaluasi. Model kandidat dan laporan
metrik disimpan di `model/keras_model_candidate.h5` dan
`model/keras_model_candidate.json`; skrip tidak mengganti model aplikasi secara
otomatis.

Pada evaluasi dataset ini, model mencapai akurasi 94.2% pada 2.991 gambar
validasi (Organik 96.8%, Anorganik 91.9%). Ini bukan jaminan akurasi pada semua
kondisi kamera atau sampah nyata. Dataset tidak memiliki contoh B3, jadi model
ini **tidak mengenali B3** dan dapat salah mengelompokkan benda berbahaya sebagai
Organik atau Anorganik. Periksa label produk dan panduan B3 secara manual.
Model klasifikasi sebelum pelatihan disimpan sebagai
`keras_model_before_dataset_training.h5`.

## Jenis bahan anorganik

Versi web juga memakai `material_classifier.h5` untuk mengenali lima jenis
bahan: karton, kaca, logam, kertas, dan plastik. Model ini dilatih sebagai
klasifikasi tahap kedua setelah kategori utama adalah Anorganik. Jenis hanya
ditampilkan bila skor kelas tertinggi minimal 65% dan unggul minimal 12 poin
persentase dari pilihan kedua. Jenis sampah organik yang lebih spesifik (misalnya
daun) belum tersedia di dataset, dan B3 tidak didukung.

Untuk melatih ulang kandidat dan laporan evaluasinya, jalankan:

```powershell
.\venv\Scripts\python.exe scripts\train_material_classifier.py
```

Kandidat disimpan sebagai `material_model_candidate.h5`; skrip tidak mengganti
model aktif secara otomatis. Kandidat saat ini mencapai akurasi 87.2% pada 478
gambar validasi terpisah dari lima kelas material. Dengan ambang penerimaan di
atas, 415 dari 478 hasil ditampilkan dan 91.1% dari hasil yang ditampilkan
sesuai label validasi. Angka ini hanya mengukur dataset tersebut, bukan jaminan
akurasi pada foto kamera nyata atau benda di luar lima kelas yang dilatih.

## Kandidat model tiga kelas dari dataset baru

Dataset baru yang diekstrak ke `new dataset/archive (1)/` dapat diperiksa tanpa
memuat model:

```powershell
.\venv\Scripts\python.exe scripts\train_three_class_model.py --inspect-only
```

Pemetaan kandidat dari `Dataset_ThirdStage/Dataset`:

- **Organik:** `A_Foods`.
- **Anorganik:** kardus, koran, gelas kertas, kertas, kaca, porselen, kaleng,
  logam, sisa konstruksi, plastik, dan Tetra Pak.
- **B3:** obat/kemasan obat, jarum suntik, baterai, termometer, dan botol
  pestisida.
- Folder lain tidak digunakan untuk pelatihan kandidat, termasuk elektronik,
  pakaian, masker, dan kaleng semprot.

Latih kandidat dengan:

```powershell
.\venv\Scripts\python.exe scripts\train_three_class_model.py
```

Skrip mengelompokkan file dengan nama dasar yang sama (misalnya `.jpg` dan
`.png`) agar varian gambar tidak tersebar antara latih dan validasi. Keluaran
disimpan terpisah sebagai `keras_model_3class_candidate_v2.h5`,
`keras_model_3class_candidate_v2.json`, dan
`labels_3class_candidate_v2.txt`. Gambar tambahan di
`dataset/real_examples/<kelas>/` hanya masuk ke data latih, tidak ke validasi.
Kandidat tidak mengganti model aktif atau label aktif secara otomatis. Periksa
precision/recall setiap kelas dan lakukan uji foto nyata yang baru sebelum
pengaktifan.

Kategori B3 hanya perkiraan dari gambar dan folder label dataset. B3 bukan satu
jenis bahan yang seragam; jangan mengandalkan model untuk memastikan tingkat
bahaya atau menentukan penanganan. Periksa label produk dan arahan pengelola
limbah setempat.

Untuk menguji kandidat dengan foto nyata yang belum pernah ada di dataset,
buat folder `uji_foto/Organik`, `uji_foto/Anorganik`, dan `uji_foto/B3`.
Masukkan foto ke folder kategori yang benar, lalu jalankan:

```powershell
.\venv\Scripts\python.exe scripts\test_three_class_photos.py
```

Skrip menampilkan akurasi, precision/recall, matriks kebingungan, dan berapa
hasil yang lolos ambang keyakinan aplikasi. Rincian tiap foto ditulis ke
`uji_foto/hasil_uji_model_3kelas.csv`. Gunakan foto barang sendiri, satu benda
per foto, dan jangan menangani atau membuka benda berbahaya hanya untuk tes.

## Deteksi objek dan manusia

`efficientdet_lite0.tflite` adalah model EfficientDet-Lite0 terlatih pada COCO,
diunduh oleh `Jalankan PilahPintar.bat` saat pertama kali dijalankan. Model berjalan
lokal dengan TensorFlow Lite; diperlukan koneksi internet hanya untuk unduhan awal.

Sumber model: [TensorFlow Lite Task Library](https://storage.googleapis.com/download.tensorflow.org/models/tflite/task_library/object_detection/android/lite-model_efficientdet_lite0_detection_metadata_1.tflite).
Model menggunakan kelas COCO; keluaran detector memakai `category_id - 1`
(kelas 0 adalah `person`, dengan celah indeks COCO tetap ada). Hanya kelas objek
tertentu yang diteruskan ke pengklasifikasi sampah yang sudah ada. Karena COCO
bukan dataset sampah, aplikasi mencoba mengklasifikasikan seluruh foto jika tidak
ada benda yang dideteksi. Jika ada manusia sekaligus benda kandidat sampah, benda
tetap diproses; scan hanya dibatalkan saat manusia terdeteksi tanpa kandidat benda
lain.
