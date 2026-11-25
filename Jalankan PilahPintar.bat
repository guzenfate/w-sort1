@echo off
cd /d "%~dp0"

if not exist "venv\Scripts\python.exe" (
    echo Python virtual environment tidak ditemukan di folder venv.
    pause
    exit /b 1
)

venv\Scripts\python.exe -c "import streamlit_webrtc" >nul 2>nul
if errorlevel 1 (
    echo Memasang paket kamera otomatis ke virtual environment proyek...
    venv\Scripts\python.exe -m pip install -r "%~dp0requirements.txt"
    if errorlevel 1 (
        echo Gagal memasang dependensi. Periksa koneksi internet lalu jalankan file ini lagi.
        pause
        exit /b 1
    )
)

    if not exist "model\efficientdet_lite0.tflite" (
        echo Mengunduh model lokal untuk deteksi banyak objek dan manusia...
        curl.exe -L --fail --show-error --silent --output "model\efficientdet_lite0.tflite" "https://storage.googleapis.com/download.tensorflow.org/models/tflite/task_library/object_detection/android/lite-model_efficientdet_lite0_detection_metadata_1.tflite"
        if errorlevel 1 (
            echo Gagal mengunduh model deteksi. Periksa koneksi internet lalu jalankan file ini lagi.
            del /q "model\efficientdet_lite0.tflite" 2>nul
            pause
            exit /b 1
        )
    )

    set "PYTHONPATH=%~dp0venv\Lib\site-packages;%PYTHONPATH%"

echo Membuka W-Sort di http://localhost:8502
echo Biarkan jendela ini tetap terbuka selama aplikasi digunakan.
"venv\Scripts\python.exe" -m streamlit run "%~dp0app.py" --server.address localhost --server.port 8502
if errorlevel 1 pause
a