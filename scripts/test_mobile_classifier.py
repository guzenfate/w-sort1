"""Uji cepat model Android offline menggunakan TFLite runtime desktop."""
import sys
from pathlib import Path

from PIL import Image


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "android_app"))

from classifier import LABELS, WasteClassifier


def main():
    """Memastikan model mengklasifikasikan contoh gambar lokal dengan benar."""
    classifier = WasteClassifier(str(ROOT / "android_app" / "waste_classifier.tflite"))
    samples = (
        (
            ROOT / "dataset" / "DATASET" / "DATASET" / "TEST" / "O" / "O_12568.jpg",
            "Organik",
        ),
        (
            ROOT / "dataset" / "DATASET" / "DATASET" / "TEST" / "R" / "R_10000.jpg",
            "Anorganik",
        ),
        (
            ROOT / "dataset" / "Garbage classification" / "metal" / "metal1.jpg",
            "Anorganik",
        ),
    )
    for path, expected in samples:
        with Image.open(path) as image:
            ranked, confident = classifier.predict(image)
        if ranked[0][0] != expected or not confident:
            raise AssertionError(
                f"{path.name}: expected confident {expected}, got {ranked}"
            )
        print(f"{path.name}: {ranked[0][0]} ({ranked[0][1]:.1%})")
    if LABELS != ("Organik", "Anorganik"):
        raise AssertionError(f"Unexpected mobile labels: {LABELS}")
    print("PASS: offline model classifies organic, recyclable and metal samples.")


if __name__ == "__main__":
    main()
