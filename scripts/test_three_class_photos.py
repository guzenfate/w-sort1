"""Mengevaluasi kandidat tiga kelas pada foto yang dikelompokkan per kategori."""
import argparse
import csv
from pathlib import Path

import numpy as np
from PIL import Image, ImageOps
from tensorflow import keras


ROOT = Path(__file__).resolve().parents[1]
CLASS_NAMES = ("Organik", "Anorganik", "B3")
IMAGE_SIZE = (224, 224)
IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp"}
CONFIDENCE_THRESHOLD = 0.65
MARGIN_THRESHOLD = 0.12


def load_labels(path):
    """Membaca file label dan memastikan urutan kelas sesuai konfigurasi."""
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        parts = line.strip().split(maxsplit=1)
        if len(parts) != 2:
            raise ValueError(f"Format label tidak valid: {line}")
        try:
            index = int(parts[0])
        except ValueError as error:
            raise ValueError(f"Nomor label tidak valid: {parts[0]}") from error
        rows.append((index, parts[1]))
    if [index for index, _ in rows] != list(range(len(rows))):
        raise ValueError("Nomor label harus berurutan mulai dari 0.")
    labels = [label for _, label in rows]
    if tuple(labels) != CLASS_NAMES:
        raise ValueError(f"Label harus berurutan {CLASS_NAMES}, tetapi ditemukan {labels}.")
    return labels


def image_tensor(path):
    """Memuat foto, mengubah ukurannya, dan menormalkan nilainya untuk model."""
    with Image.open(path) as source:
        image = ImageOps.fit(
            source.convert("RGB"), IMAGE_SIZE, Image.Resampling.LANCZOS
        )
        return np.asarray(image, dtype=np.float32) / 127.5 - 1.0


def collect_photos(photo_root):
    """Mengumpulkan foto uji dari subfolder yang namanya sesuai kategori."""
    samples = []
    folders = {
        path.name.casefold(): path for path in photo_root.iterdir() if path.is_dir()
    }
    for label in CLASS_NAMES:
        folder = folders.get(label.casefold())
        if folder is None:
            raise FileNotFoundError(
                f"Folder kelas tidak ditemukan: {label}. "
                f"Buat folder {', '.join(CLASS_NAMES)} di dalam {photo_root}."
            )
        paths = sorted(
            path
            for path in folder.rglob("*")
            if path.is_file() and path.suffix.lower() in IMAGE_EXTENSIONS
        )
        if not paths:
            raise ValueError(f"Belum ada foto uji di folder {folder}.")
        samples.extend((path, label) for path in paths)
    return samples


def main():
    """Mengukur prediksi model, mencetak metrik, dan menyimpan rincian ke CSV."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--photos", type=Path, default=ROOT / "uji_foto")
    parser.add_argument(
        "--model",
        type=Path,
        default=ROOT / "model" / "keras_model_3class_candidate_v2.h5",
    )
    parser.add_argument(
        "--labels",
        type=Path,
        default=ROOT / "model" / "labels_3class_candidate_v2.txt",
    )
    parser.add_argument(
        "--csv",
        type=Path,
        default=ROOT / "uji_foto" / "hasil_uji_model_3kelas.csv",
    )
    args = parser.parse_args()
    labels = load_labels(args.labels)
    samples = collect_photos(args.photos)
    model = keras.models.load_model(args.model, compile=False)
    if model.input_shape != (None, 224, 224, 3) or model.output_shape != (
        None,
        len(labels),
    ):
        raise ValueError(
            f"Bentuk model tidak sesuai dengan label: "
            f"{model.input_shape}, {model.output_shape}"
        )

    confusion = np.zeros((len(labels), len(labels)), dtype=np.int64)
    totals = np.zeros(len(labels), dtype=np.int64)
    correct_by_class = np.zeros(len(labels), dtype=np.int64)
    prediction_totals = np.zeros(len(labels), dtype=np.int64)
    accepted_total = 0
    accepted_correct = 0
    results = []

    for path, true_label in samples:
        scores = model.predict(image_tensor(path)[np.newaxis, ...], verbose=0)[0]
        ranking = np.argsort(scores)[::-1]
        predicted_index = int(ranking[0])
        true_index = labels.index(true_label)
        confidence = float(scores[predicted_index])
        margin = confidence - float(scores[ranking[1]])
        accepted = confidence >= CONFIDENCE_THRESHOLD and margin >= MARGIN_THRESHOLD
        correct = predicted_index == true_index
        totals[true_index] += 1
        confusion[true_index, predicted_index] += 1
        correct_by_class[true_index] += int(correct)
        prediction_totals[predicted_index] += 1
        accepted_total += int(accepted)
        accepted_correct += int(accepted and correct)
        results.append(
            (
                path.relative_to(args.photos).as_posix(),
                true_label,
                labels[predicted_index],
                confidence,
                margin,
                accepted,
                correct,
            )
        )

    args.csv.parent.mkdir(parents=True, exist_ok=True)
    with args.csv.open("w", newline="", encoding="utf-8-sig") as file:
        writer = csv.writer(file)
        writer.writerow(
            (
                "file",
                "label_sebenarnya",
                "prediksi",
                "keyakinan",
                "selisih_dengan_kedua",
                "diterima_ambang_aplikasi",
                "benar",
            )
        )
        writer.writerows(results)

    print(f"Jumlah foto: {len(samples)}")
    print(f"Akurasi top-1: {correct_by_class.sum() / totals.sum():.1%}")
    print(
        f"Hasil diterima ambang aplikasi: {accepted_total}/{len(samples)} "
        f"({accepted_total / len(samples):.1%})"
    )
    if accepted_total:
        print(f"Akurasi pada hasil yang diterima: {accepted_correct / accepted_total:.1%}")
    print("Matriks kebingungan (baris=label sebenarnya, kolom=prediksi):")
    print("                  " + "  ".join(f"{label:>10}" for label in labels))
    for index, label in enumerate(labels):
        print(f"{label:>18}  " + "  ".join(f"{value:10d}" for value in confusion[index]))
    print("Per kelas:")
    for index, label in enumerate(labels):
        precision = (
            correct_by_class[index] / prediction_totals[index]
            if prediction_totals[index]
            else 0.0
        )
        recall = correct_by_class[index] / totals[index]
        print(
            f"  {label}: benar {correct_by_class[index]}/{totals[index]}, "
            f"precision {precision:.1%}, recall {recall:.1%}"
        )
    print(f"Rincian disimpan ke {args.csv}")
    print("Evaluasi foto nyata bukan jaminan aman untuk menentukan penanganan B3.")


if __name__ == "__main__":
    main()
