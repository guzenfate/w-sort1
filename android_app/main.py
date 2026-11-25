"""Aplikasi Kivy offline untuk memindai sampah di Android."""
import json
import os
import threading
from datetime import datetime

from PIL import Image, ImageOps
from kivy.app import App
from kivy.clock import Clock
from kivy.core.window import Window
from kivy.graphics import Color, RoundedRectangle
from kivy.resources import resource_find
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.button import Button
from kivy.uix.camera import Camera
from kivy.uix.label import Label
from kivy.uix.screenmanager import Screen, ScreenManager
from kivy.uix.scrollview import ScrollView
from kivy.utils import platform

from classifier import WasteClassifier

BACKGROUND = (0.95, 0.97, 0.94, 1)
GREEN = (0.12, 0.38, 0.25, 1)


class Card(BoxLayout):
    """Kartu putih dengan sudut membulat untuk layar riwayat."""

    def __init__(self, **kwargs):
        """Membuat kartu dan menjaga latar tetap mengikuti ukuran widget."""
        super().__init__(**kwargs)
        with self.canvas.before:
            Color(1, 1, 1, 1)
            self.background = RoundedRectangle(
                pos=self.pos, size=self.size, radius=[18]
            )
        self.bind(pos=self._update_background, size=self._update_background)

    def _update_background(self, *_):
        """Memperbarui posisi dan ukuran latar kartu."""
        self.background.pos = self.pos
        self.background.size = self.size


def make_label(text, font_size=16, color=(0.12, 0.16, 0.13, 1), **kwargs):
    """Membuat label rata kiri yang membungkus teks sesuai ukuran widget."""
    label = Label(
        text=text,
        font_size=font_size,
        color=color,
        halign="left",
        valign="middle",
        **kwargs,
    )
    label.bind(size=lambda widget, size: setattr(widget, "text_size", size))
    return label


def make_button(text, callback, color=GREEN):
    """Membuat tombol berwarna dan menghubungkan fungsi saat tombol ditekan."""
    button = Button(
        text=text,
        size_hint_y=None,
        height=54,
        background_normal="",
        background_color=color,
        color=(1, 1, 1, 1),
        font_size=16,
    )
    button.bind(on_release=callback)
    return button


class ScannerScreen(Screen):
    """Layar kamera untuk mengambil gambar dan menampilkan prediksi."""

    def __init__(self, app, **kwargs):
        """Menyusun tampilan kamera, status model, dan tombol pemindaian."""
        super().__init__(name="scanner", **kwargs)
        self.owner = app
        self.layout = BoxLayout(
            orientation="vertical", padding=18, spacing=12
        )
        self.add_widget(self.layout)
        self.layout.add_widget(
            make_label("W-Sort", 28, GREEN, size_hint_y=None, height=42)
        )
        self.layout.add_widget(
            make_label(
                "Arahkan kamera ke satu benda untuk memperkirakan kategorinya.",
                14,
                size_hint_y=None,
                height=44,
            )
        )
        self.camera = Camera(
            play=False,
            resolution=(1280, 720),
            index=0,
            size_hint=(1, 0.55),
        )
        with self.camera.canvas.before:
            Color(0.08, 0.1, 0.08, 1)
            self.camera_background = RoundedRectangle(
                pos=self.camera.pos, size=self.camera.size, radius=[18]
            )
        self.camera.bind(
            pos=lambda widget, pos: setattr(self.camera_background, "pos", pos),
            size=lambda widget, size: setattr(self.camera_background, "size", size),
        )
        self.layout.add_widget(self.camera)
        self.status = make_label(
            "Memuat model offline...", 15, size_hint_y=None, height=56
        )
        self.layout.add_widget(self.status)
        self.scan_button = make_button("Pindai sampah", self.scan)
        self.scan_button.disabled = True
        self.layout.add_widget(self.scan_button)
        self.layout.add_widget(
            make_button(
                "Riwayat scan",
                lambda *_: self.owner.show_history(),
                color=(0.35, 0.45, 0.38, 1),
            )
        )
        self.layout.add_widget(
            make_label(
                "Model hanya mengenali Organik dan Anorganik. B3 tidak didukung; "
                "periksa label dan panduan secara manual.",
                13,
                (0.48, 0.34, 0.08, 1),
                size_hint_y=None,
                height=52,
            )
        )

    def scan(self, *_):
        """Mengambil frame kamera dan memulai klasifikasi di thread terpisah."""
        texture = self.camera.texture
        if texture is None:
            self.status.text = "Kamera belum siap. Periksa izin kamera lalu coba lagi."
            return
        self.scan_button.disabled = True
        self.status.text = "Menganalisis gambar di perangkat..."
        try:
            width, height = texture.size
            mode = texture.colorfmt.upper()
            if mode not in ("RGB", "RGBA"):
                raise ValueError(f"Format kamera tidak didukung: {texture.colorfmt}")
            image = Image.frombytes(mode, (width, height), texture.pixels)
            image = ImageOps.flip(image).convert("RGB")
        except Exception as error:
            self.scan_button.disabled = False
            self.status.text = f"Gambar kamera gagal dibaca: {error}"
            return
        threading.Thread(
            target=self._classify, args=(image,), daemon=True
        ).start()

    def _classify(self, image):
        """Mengklasifikasikan gambar, menyimpan hasil, lalu memperbarui tampilan."""
        try:
            ranked, confident = self.owner.classifier.predict(image)
            record = {
                "waktu": datetime.now().astimezone().isoformat(timespec="seconds"),
                "label": ranked[0][0],
                "keyakinan": ranked[0][1],
                "yakin": confident,
            }
            self.owner.save_record(record)
            Clock.schedule_once(lambda _dt: self._show_result(record), 0)
        except Exception as error:
            Clock.schedule_once(
                lambda _dt, message=str(error): self._show_error(message), 0
            )

    def _show_result(self, record):
        """Menampilkan label hasil dan apakah prediksi cukup meyakinkan."""
        score = record["keyakinan"]
        if record["yakin"]:
            self.status.text = (
                f"Perkiraan: {record['label']} ({score:.0%})\n"
                "Pastikan kembali jenis bahan sebelum memilah."
            )
        else:
            self.status.text = (
                f"Belum yakin — perkiraan {record['label']} ({score:.0%}).\n"
                "Coba dekatkan satu benda dan gunakan pencahayaan yang baik."
            )
        self.scan_button.disabled = False

    def _show_error(self, message):
        """Menampilkan kesalahan klasifikasi dan mengaktifkan tombol pindai lagi."""
        self.status.text = f"Gagal menganalisis foto: {message}"
        self.scan_button.disabled = False


class HistoryScreen(Screen):
    """Layar yang menampilkan riwayat pemindaian lokal."""

    def __init__(self, app, **kwargs):
        """Menyusun daftar riwayat yang dapat digulir."""
        super().__init__(name="history", **kwargs)
        self.owner = app
        self.layout = BoxLayout(orientation="vertical", padding=18, spacing=12)
        self.add_widget(self.layout)
        self.layout.add_widget(
            make_label("Riwayat scan", 26, GREEN, size_hint_y=None, height=48)
        )
        self.scroll = ScrollView()
        self.rows = BoxLayout(orientation="vertical", spacing=8, size_hint_y=None)
        self.rows.bind(minimum_height=self.rows.setter("height"))
        self.scroll.add_widget(self.rows)
        self.layout.add_widget(self.scroll)
        self.layout.add_widget(
            make_button("Kembali ke kamera", lambda *_: app.show_scanner())
        )

    def refresh(self):
        """Memuat ulang dan menampilkan paling banyak 50 hasil terbaru."""
        self.rows.clear_widgets()
        records = self.owner.load_records()
        if not records:
            self.rows.add_widget(
                make_label("Belum ada hasil scan.", size_hint_y=None, height=54)
            )
            return
        for record in reversed(records[-50:]):
            waktu = record["waktu"].replace("T", " ")
            label = f"{waktu}  ·  {record['label']}  ·  {record['keyakinan']:.0%}"
            row = Card(size_hint_y=None, height=58, padding=12)
            row.add_widget(make_label(label, 14))
            self.rows.add_widget(row)


class PilahPintarApp(App):
    """Mengelola layar, model, kamera, dan penyimpanan lokal aplikasi."""

    def build(self):
        """Membuat layar aplikasi dan menjadwalkan pemuatan model."""
        self.title = "W-Sort"
        Window.clearcolor = BACKGROUND
        self.manager = ScreenManager()
        self.scanner = ScannerScreen(self)
        self.history = HistoryScreen(self)
        self.camera_granted = False
        self.manager.add_widget(self.scanner)
        self.manager.add_widget(self.history)
        Clock.schedule_once(self.load_classifier, 0)
        return self.manager

    def load_classifier(self, *_):
        """Memuat model TFLite lokal lalu meminta izin kamera."""
        try:
            model_path = os.path.join(
                os.path.dirname(os.path.abspath(__file__)), "waste_classifier.tflite"
            )
            if not os.path.isfile(model_path):
                model_path = resource_find("waste_classifier.tflite")
            if not model_path:
                raise FileNotFoundError("File waste_classifier.tflite tidak ditemukan.")
            self.classifier = WasteClassifier(model_path)
            self.scanner.scan_button.disabled = False
            self.scanner.status.text = "Model siap. Izinkan kamera, lalu pindai satu benda."
            self.request_camera_permission()
        except Exception as error:
            self.scanner.status.text = f"Model offline gagal dimuat: {error}"

    def request_camera_permission(self):
        """Meminta izin kamera di Android atau mengaktifkannya di desktop."""
        if platform != "android":
            self.camera_granted = True
            self.scanner.camera.play = True
            return
        try:
            from android.permissions import Permission, request_permissions

            request_permissions(
                [Permission.CAMERA],
                callback=self._camera_permission_result,
            )
        except Exception as error:
            self.scanner.status.text = f"Izin kamera gagal diminta: {error}"

    def _camera_permission_result(self, _permissions, grant_results):
        """Menjadwalkan penerapan hasil permintaan izin pada thread UI."""
        granted = bool(grant_results) and all(grant_results)
        Clock.schedule_once(lambda _dt: self._set_camera_permission(granted), 0)

    def _set_camera_permission(self, granted):
        """Mengaktifkan kamera sesuai izin dan memberi pesan bila ditolak."""
        self.camera_granted = granted
        self.scanner.camera.play = granted
        if not granted:
            self.scanner.status.text = (
                "Izin kamera diperlukan. Aktifkan izin W-Sort di pengaturan Android."
            )

    def show_history(self):
        """Menghentikan kamera dan membuka layar riwayat."""
        self.scanner.camera.play = False
        self.history.refresh()
        self.manager.current = "history"

    def show_scanner(self):
        """Membuka layar pemindai dan melanjutkan kamera jika diizinkan."""
        self.manager.current = "scanner"
        self.scanner.camera.play = self.camera_granted

    def load_records(self):
        """Membaca riwayat JSON lokal atau mengembalikan daftar kosong."""
        path = os.path.join(self.user_data_dir, "riwayat.json")
        if not os.path.isfile(path):
            return []
        try:
            with open(path, encoding="utf-8") as file:
                records = json.load(file)
        except (OSError, json.JSONDecodeError) as error:
            Clock.schedule_once(
                lambda _dt, message=str(error): setattr(
                    self.scanner.status, "text", f"Riwayat tidak dapat dibaca: {message}"
                ),
                0,
            )
            return []
        if not isinstance(records, list):
            self.scanner.status.text = "Format riwayat tidak valid."
            return []
        return records

    def save_record(self, record):
        """Menambahkan hasil ke riwayat dan membatasi penyimpanan ke 500 baris."""
        path = os.path.join(self.user_data_dir, "riwayat.json")
        os.makedirs(self.user_data_dir, exist_ok=True)
        records = self.load_records()
        records.append(record)
        temporary_path = path + ".tmp"
        with open(temporary_path, "w", encoding="utf-8") as file:
            json.dump(records[-500:], file, ensure_ascii=False, indent=2)
        os.replace(temporary_path, path)

    def on_pause(self):
        """Menghentikan kamera saat aplikasi masuk ke latar belakang."""
        self.scanner.camera.play = False
        return True

    def on_resume(self):
        """Memeriksa kembali izin kamera saat aplikasi dibuka lagi."""
        self.request_camera_permission()


if __name__ == "__main__":
    PilahPintarApp().run()
