"""Mengekspor model klasifikasi aktif ke format TFLite untuk aplikasi Android."""
import argparse
from pathlib import Path

import numpy as np
import tensorflow as tf
from tensorflow import keras


ROOT = Path(__file__).resolve().parents[1]


def main():
    """Memvalidasi model sumber, mengekspornya, lalu memeriksa model TFLite."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--source", type=Path, default=ROOT / "model" / "keras_model.h5"
    )
    parser.add_argument(
        "--output", type=Path, default=ROOT / "android_app" / "waste_classifier.tflite"
    )
    args = parser.parse_args()

    model = keras.models.load_model(args.source, compile=False)
    if model.input_shape != (None, 224, 224, 3) or model.output_shape != (None, 2):
        raise ValueError(
            "Model Android harus menerima gambar 224x224 RGB dan menghasilkan "
            "dua skor Organik/Anorganik."
        )
    converter = tf.lite.TFLiteConverter.from_keras_model(model)
    converter.optimizations = [tf.lite.Optimize.DEFAULT]
    content = converter.convert()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(content)

    interpreter = tf.lite.Interpreter(model_path=str(args.output), num_threads=2)
    interpreter.allocate_tensors()
    input_info = interpreter.get_input_details()[0]
    output_info = interpreter.get_output_details()[0]
    if tuple(input_info["shape"]) != (1, 224, 224, 3):
        raise ValueError(f"Bentuk masukan TFLite tidak sesuai: {input_info['shape']}")
    if input_info["dtype"] != np.float32 or tuple(output_info["shape"]) != (1, 2):
        raise ValueError("Model TFLite harus memakai input float32 dan output 2 kelas.")
    print(f"Model mobile berhasil dibuat: {args.output}")
    print(f"Ukuran: {args.output.stat().st_size:,} bytes")


if __name__ == "__main__":
    main()
