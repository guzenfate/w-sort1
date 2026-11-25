"""Klasifikasi lokal yang dipakai bersama oleh aplikasi Kivy dan Android."""
from array import array

import numpy as np
from PIL import Image, ImageOps

try:
    from kivy.utils import platform
except ImportError:
    platform = "desktop"


LABELS = ("Organik", "Anorganik")
CONFIDENCE_THRESHOLD = 0.65
MARGIN_THRESHOLD = 0.12


class WasteClassifier:
    """Memuat model TFLite dan memprediksi kategori Organik atau Anorganik."""

    def __init__(self, model_path):
        """Memuat interpreter TFLite sesuai platform yang sedang digunakan."""
        self.android = platform == "android"
        if self.android:
            from jnius import autoclass

            interpreter_class = autoclass("org.tensorflow.lite.Interpreter")
            file_class = autoclass("java.io.File")
            stream_class = autoclass("java.io.FileInputStream")
            map_mode_class = autoclass("java.nio.channels.FileChannel$MapMode")
            self.byte_buffer = autoclass("java.nio.ByteBuffer")
            self.byte_order = autoclass("java.nio.ByteOrder")
            stream = stream_class(model_path)
            channel = stream.getChannel()
            mapped_model = channel.map(
                map_mode_class.READ_ONLY, 0, file_class(model_path).length()
            )
            self.interpreter = interpreter_class(mapped_model)
            self.input = self.byte_buffer.allocateDirect(1 * 224 * 224 * 3 * 4)
            self.output = self.byte_buffer.allocateDirect(len(LABELS) * 4)
            self.input.order(self.byte_order.nativeOrder())
            self.output.order(self.byte_order.nativeOrder())
            self._stream = stream
        else:
            try:
                from tflite_runtime.interpreter import Interpreter
            except ImportError:
                import tensorflow as tf

                Interpreter = tf.lite.Interpreter

            self.interpreter = Interpreter(model_path=model_path, num_threads=2)
            self.interpreter.allocate_tensors()
            self.input_details = self.interpreter.get_input_details()[0]
            self.output_details = self.interpreter.get_output_details()[0]

    def predict(self, image):
        """Memproses gambar dan mengembalikan skor terurut serta status keyakinan."""
        image = ImageOps.fit(
            image.convert("RGB"), (224, 224), Image.Resampling.LANCZOS
        )
        values = np.asarray(image, dtype=np.float32) / 127.5 - 1.0
        if self.android:
            self.input.rewind()
            self.input.put(array("b", values.tobytes()))
            self.input.rewind()
            self.output.rewind()
            self.interpreter.run(self.input, self.output)
            self.output.rewind()
            scores = [self.output.getFloat() for _ in LABELS]
        else:
            tensor = values[np.newaxis, ...]
            self.interpreter.set_tensor(self.input_details["index"], tensor)
            self.interpreter.invoke()
            scores = self.interpreter.get_tensor(self.output_details["index"])[0]
        ranked = sorted(
            ((LABELS[index], float(score)) for index, score in enumerate(scores)),
            key=lambda result: result[1],
            reverse=True,
        )
        confident = (
            ranked[0][1] >= CONFIDENCE_THRESHOLD
            and ranked[0][1] - ranked[1][1] >= MARGIN_THRESHOLD
        )
        return ranked, confident
