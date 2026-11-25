"""Melatih kandidat klasifikasi Organik/Anorganik dari dataset lokal."""
import argparse
import json
import random
from pathlib import Path

import numpy as np
from PIL import Image, ImageOps
from tensorflow import keras


ROOT = Path(__file__).resolve().parents[1]
IMAGE_SIZE = (224, 224)
CLASS_NAMES = ("Organik", "Anorganik")
GARBAGE_CLASS_MAP = {
    "cardboard": 1,
    "glass": 1,
    "metal": 1,
    "paper": 1,
    "plastic": 1,
}


def collect_dataset(dataset_root):
    """Mengumpulkan data latih dan validasi lalu memetakan kelas daur ulang."""
    source = dataset_root / "DATASET" / "DATASET"
    train_images = []
    validation_images = []
    for folder_name, label in (("O", 0), ("R", 1)):
        for split, target in (("TRAIN", train_images), ("TEST", validation_images)):
            folder = source / split / folder_name
            paths = sorted(folder.glob("*.jpg"))
            if not paths:
                raise FileNotFoundError(f"Tidak ada gambar .jpg di {folder}")
            target.extend((path, label) for path in paths)

    garbage_root = dataset_root / "Garbage classification"
    rng = random.Random(42)
    for class_name, label in GARBAGE_CLASS_MAP.items():
        paths = sorted((garbage_root / class_name).glob("*.jpg"))
        if not paths:
            raise FileNotFoundError(
                f"Tidak ada gambar .jpg untuk kelas {class_name} di {garbage_root}"
            )
        rng.shuffle(paths)
        jumlah_validasi = max(1, round(len(paths) * 0.2))
        validation_images.extend((path, label) for path in paths[:jumlah_validasi])
        train_images.extend((path, label) for path in paths[jumlah_validasi:])

    if not (dataset_root / "Garbage classification" / "trash").is_dir():
        print("Peringatan: folder trash tidak ditemukan; kelas trash tetap tidak digunakan.")
    else:
        jumlah_trash = sum(
            1 for path in (dataset_root / "Garbage classification" / "trash").glob("*.jpg")
        )
        print(f"Mengabaikan {jumlah_trash} gambar trash sesuai pemetaan dataset.")
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
    labels = np.asarray([label for _, label in samples], dtype=np.int64)
    total_batches = (len(samples) + batch_size - 1) // batch_size
    print(f"Mengekstrak fitur {description}: {len(samples)} gambar.")
    for batch_number, images in enumerate(image_batches(samples, batch_size), 1):
        features.append(feature_extractor(images, training=False).numpy())
        if batch_number % 25 == 0 or batch_number == total_batches:
            print(f"  batch {batch_number}/{total_batches}")
    return np.concatenate(features, axis=0), labels


def class_metrics(probabilities, labels):
    """Menghitung akurasi, recall per kelas, dan matriks kebingungan."""
    predictions = np.argmax(probabilities, axis=1)
    matrix = np.zeros((2, 3), dtype=np.int64)
    for expected, predicted in zip(labels, predictions):
        matrix[expected, predicted] += 1
    accuracy = float(np.mean(predictions == labels))
    per_class = {}
    for index, name in enumerate(CLASS_NAMES):
        total = int(matrix[index].sum())
        per_class[name] = {
            "correct": int(matrix[index, index]),
            "total": total,
            "recall": float(matrix[index, index] / total) if total else 0.0,
        }
    return {
        "accuracy": accuracy,
        "per_class": per_class,
        "confusion_matrix": matrix.tolist(),
    }


def main():
    """Melatih kandidat model, membandingkannya dengan baseline, dan menyimpan metrik."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", type=Path, default=ROOT / "dataset")
    parser.add_argument(
        "--output", type=Path, default=ROOT / "model" / "keras_model_candidate.h5"
    )
    parser.add_argument("--epochs", type=int, default=20)
    parser.add_argument("--batch-size", type=int, default=32)
    args = parser.parse_args()
    if args.epochs < 1 or args.batch_size < 1:
        parser.error("--epochs and --batch-size must be positive")

    keras.utils.set_random_seed(42)
    train_samples, validation_samples = collect_dataset(args.dataset)
    print(
        f"Data latih: {len(train_samples)} "
        f"(Organik {sum(label == 0 for _, label in train_samples)}, "
        f"Anorganik {sum(label == 1 for _, label in train_samples)}); "
        f"validasi: {len(validation_samples)} "
        f"(Organik {sum(label == 0 for _, label in validation_samples)}, "
        f"Anorganik {sum(label == 1 for _, label in validation_samples)})."
    )

    previous_model = keras.models.load_model(
        ROOT / "model" / "keras_model.h5", compile=False
    )
    feature_extractor = previous_model.layers[0]
    feature_extractor.trainable = False
    train_features, train_labels = extract_features(
        train_samples, feature_extractor, args.batch_size, "data latih"
    )
    validation_features, validation_labels = extract_features(
        validation_samples, feature_extractor, args.batch_size, "validasi"
    )

    old_head = previous_model.layers[1]
    head_input = keras.Input(shape=(train_features.shape[1],), name="features")
    hidden = keras.layers.Dense(100, activation="relu", name="waste_hidden")
    hidden_output = hidden(head_input)
    dropped = keras.layers.Dropout(0.15, name="waste_dropout")(hidden_output)
    output = keras.layers.Dense(
        len(CLASS_NAMES), activation="softmax", name="waste_categories"
    )(dropped)
    classifier = keras.Model(head_input, output, name="pilahpintar_classifier")
    hidden.set_weights(old_head.layers[0].get_weights())
    classifier.compile(
        optimizer=keras.optimizers.Adam(learning_rate=0.0005),
        loss="sparse_categorical_crossentropy",
        metrics=["accuracy"],
    )
    callbacks = [
        keras.callbacks.EarlyStopping(
            monitor="val_accuracy", patience=4, restore_best_weights=True
        )
    ]
    classifier.fit(
        train_features,
        train_labels,
        validation_data=(validation_features, validation_labels),
        batch_size=128,
        epochs=args.epochs,
        callbacks=callbacks,
        verbose=2,
    )

    old_probabilities = old_head.predict(validation_features, batch_size=256, verbose=0)
    new_probabilities = classifier.predict(
        validation_features, batch_size=256, verbose=0
    )
    report = {
        "class_names": list(CLASS_NAMES),
        "training_images": len(train_samples),
        "validation_images": len(validation_samples),
        "baseline": class_metrics(old_probabilities, validation_labels),
        "candidate": class_metrics(new_probabilities, validation_labels),
        "limitations": [
            "Model hanya dilatih untuk Organik dan Anorganik.",
            "B3 tidak memiliki contoh berlabel pada dataset dan tidak dapat dikenali model ini.",
            "Kelas metal dipetakan ke Anorganik sesuai arahan pengguna.",
            "Kelas trash tidak digunakan.",
        ],
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    model_input = keras.Input(shape=(224, 224, 3), name="image")
    model_features = feature_extractor(model_input, training=False)
    model_output = classifier(model_features, training=False)
    full_model = keras.Model(model_input, model_output, name="pilahpintar_model")
    full_model.save(args.output)
    loaded_model = keras.models.load_model(args.output, compile=False)
    if loaded_model.input_shape != (None, 224, 224, 3) or loaded_model.output_shape != (
        None,
        len(CLASS_NAMES),
    ):
        raise ValueError(f"Bentuk model ekspor tidak sesuai: {loaded_model.input_shape}, {loaded_model.output_shape}")
    with args.output.with_suffix(".json").open("w", encoding="utf-8") as file:
        json.dump(report, file, ensure_ascii=False, indent=2)

    print("Metrik validasi:")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    print(f"Kandidat model disimpan ke {args.output}")
    print("Kandidat belum menggantikan model aplikasi.")


if __name__ == "__main__":
    main()
