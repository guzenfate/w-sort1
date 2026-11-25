"""Melatih kandidat model jenis bahan dari dataset sampah daur ulang lokal."""
import argparse
import json
import random
from pathlib import Path

import numpy as np
from PIL import Image, ImageOps
from tensorflow import keras


ROOT = Path(__file__).resolve().parents[1]
IMAGE_SIZE = (224, 224)
CLASS_NAMES = ("Karton", "Kaca", "Logam", "Kertas", "Plastik")
CLASS_FOLDERS = {
    "cardboard": "Karton",
    "glass": "Kaca",
    "metal": "Logam",
    "paper": "Kertas",
    "plastic": "Plastik",
}


def collect_dataset(dataset_root):
    """Membagi gambar tiap jenis bahan menjadi data latih dan validasi."""
    source = dataset_root / "Garbage classification"
    train_images = []
    validation_images = []
    rng = random.Random(42)
    for folder, label in CLASS_FOLDERS.items():
        paths = sorted((source / folder).glob("*.jpg"))
        if not paths:
            raise FileNotFoundError(f"Tidak ada gambar .jpg untuk kelas {folder} di {source}")
        rng.shuffle(paths)
        validation_count = max(1, round(len(paths) * 0.2))
        validation_images.extend((path, label) for path in paths[:validation_count])
        train_images.extend((path, label) for path in paths[validation_count:])
    return train_images, validation_images


def image_batches(samples, batch_size):
    """Menghasilkan batch gambar RGB berukuran seragam dan ternormalisasi."""
    for offset in range(0, len(samples), batch_size):
        batch = samples[offset : offset + batch_size]
        images = []
        for path, _ in batch:
            with Image.open(path) as source:
                image = ImageOps.fit(
                    source.convert("RGB"), IMAGE_SIZE, Image.Resampling.LANCZOS
                )
                images.append(np.asarray(image, dtype=np.float32) / 127.5 - 1.0)
        yield np.stack(images)


def extract_features(samples, feature_extractor, batch_size, description):
    """Mengubah gambar menjadi fitur model dasar dan mengembalikan labelnya."""
    features = []
    labels = np.asarray(
        [CLASS_NAMES.index(label) for _, label in samples], dtype=np.int64
    )
    total_batches = (len(samples) + batch_size - 1) // batch_size
    print(f"Mengekstrak fitur {description}: {len(samples)} gambar.")
    for batch_number, images in enumerate(image_batches(samples, batch_size), 1):
        features.append(feature_extractor(images, training=False).numpy())
        if batch_number % 10 == 0 or batch_number == total_batches:
            print(f"  batch {batch_number}/{total_batches}")
    return np.concatenate(features, axis=0), labels


def class_metrics(probabilities, labels):
    """Menghitung akurasi, recall per kelas, dan matriks kebingungan."""
    predictions = np.argmax(probabilities, axis=1)
    matrix = np.zeros((len(CLASS_NAMES), len(CLASS_NAMES)), dtype=np.int64)
    for expected, predicted in zip(labels, predictions):
        matrix[expected, predicted] += 1
    per_class = {}
    for index, name in enumerate(CLASS_NAMES):
        total = int(matrix[index].sum())
        per_class[name] = {
            "correct": int(matrix[index, index]),
            "total": total,
            "recall": float(matrix[index, index] / total) if total else 0.0,
        }
    return {
        "accuracy": float(np.mean(predictions == labels)),
        "per_class": per_class,
        "confusion_matrix": matrix.tolist(),
    }


def main():
    """Melatih kepala klasifikasi bahan dan menyimpan model kandidat beserta metrik."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", type=Path, default=ROOT / "dataset")
    parser.add_argument(
        "--output", type=Path, default=ROOT / "model" / "material_model_candidate.h5"
    )
    parser.add_argument("--epochs", type=int, default=30)
    parser.add_argument("--batch-size", type=int, default=32)
    args = parser.parse_args()
    if args.epochs < 1 or args.batch_size < 1:
        parser.error("--epochs and --batch-size must be positive")

    keras.utils.set_random_seed(42)
    train_samples, validation_samples = collect_dataset(args.dataset)
    print(
        f"Data latih: {len(train_samples)}; validasi: {len(validation_samples)}."
    )

    base_model = keras.models.load_model(
        ROOT / "model" / "keras_model.h5", compile=False
    )
    feature_extractor = base_model.layers[-2]
    feature_extractor.trainable = False
    train_features, train_labels = extract_features(
        train_samples, feature_extractor, args.batch_size, "data latih"
    )
    validation_features, validation_labels = extract_features(
        validation_samples, feature_extractor, args.batch_size, "validasi"
    )

    inputs = keras.Input(shape=(train_features.shape[1],), name="features")
    hidden = keras.layers.Dense(256, activation="relu", name="material_hidden")(inputs)
    dropped = keras.layers.Dropout(0.25, name="material_dropout")(hidden)
    outputs = keras.layers.Dense(
        len(CLASS_NAMES), activation="softmax", name="material_types"
    )(dropped)
    classifier = keras.Model(inputs, outputs, name="pilahpintar_material_classifier")
    classifier.compile(
        optimizer=keras.optimizers.Adam(learning_rate=0.0005),
        loss="sparse_categorical_crossentropy",
        metrics=["accuracy"],
    )
    classifier.fit(
        train_features,
        train_labels,
        validation_data=(validation_features, validation_labels),
        batch_size=64,
        epochs=args.epochs,
        callbacks=[
            keras.callbacks.EarlyStopping(
                monitor="val_accuracy", patience=5, restore_best_weights=True
            )
        ],
        verbose=2,
    )

    probabilities = classifier.predict(
        validation_features, batch_size=128, verbose=0
    )
    report = {
        "class_names": list(CLASS_NAMES),
        "training_images": len(train_samples),
        "validation_images": len(validation_samples),
        "candidate": class_metrics(probabilities, validation_labels),
        "limitations": [
            "Jenis yang tersedia hanya karton, kaca, logam, kertas, dan plastik.",
            "Dataset ini tidak memberi label jenis spesifik untuk sampah organik.",
            "Model tetap harus diuji pada foto kamera nyata; hasil validasi dataset bukan jaminan akurasi lapangan.",
        ],
    }
    inputs = keras.Input(shape=(224, 224, 3), name="image")
    features = feature_extractor(inputs, training=False)
    outputs = classifier(features, training=False)
    full_model = keras.Model(inputs, outputs, name="pilahpintar_material_model")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    full_model.save(args.output)
    loaded_model = keras.models.load_model(args.output, compile=False)
    if loaded_model.input_shape != (None, 224, 224, 3) or loaded_model.output_shape != (
        None,
        len(CLASS_NAMES),
    ):
        raise ValueError(
            f"Bentuk model ekspor tidak sesuai: {loaded_model.input_shape}, "
            f"{loaded_model.output_shape}"
        )
    with args.output.with_suffix(".json").open("w", encoding="utf-8") as file:
        json.dump(report, file, ensure_ascii=False, indent=2)

    print(json.dumps(report, ensure_ascii=False, indent=2))
    print(f"Kandidat model disimpan ke {args.output}")
    print("Kandidat belum menggantikan model aplikasi.")


if __name__ == "__main__":
    main()
