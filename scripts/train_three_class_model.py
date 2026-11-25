"""Melatih kandidat model tiga kelas dari dataset tahap ketiga yang diekstrak."""
import argparse
import json
import random
from collections import defaultdict
from pathlib import Path

import numpy as np
from PIL import Image, ImageOps
from tensorflow import keras


ROOT = Path(__file__).resolve().parents[1]
IMAGE_SIZE = (224, 224)
CLASS_NAMES = ("Organik", "Anorganik", "B3")
CLASS_FOLDERS = {
    "A_Foods": "Organik",
    "C_Cardboard": "Anorganik",
    "D_Newspaper": "Anorganik",
    "E_Paper Cups": "Anorganik",
    "F_Papers": "Anorganik",
    "G_Brown Glass": "Anorganik",
    "H_Porcelin": "Anorganik",
    "I_Green Glass": "Anorganik",
    "J_White Glass": "Anorganik",
    "K_Beverage Cans": "Anorganik",
    "L_Construction Scrap": "Anorganik",
    "M_Metal Containers": "Anorganik",
    "N_Plastic Bag": "Anorganik",
    "O_Plastic Bottle": "Anorganik",
    "Q_Plastic Containers": "Anorganik",
    "R_Plastic Cups": "Anorganik",
    "S_Tetra Pak": "Anorganik",
    "Y_Medicine and Medicine Strip": "B3",
    "Z_A_A_Syringe": "B3",
    "Z_G_Battery": "B3",
    "Z_H_Thermometer": "B3",
    "Z_J_Pesticidebottle": "B3",
}
IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png"}
PREFERRED_EXTENSIONS = {".jpg": 0, ".jpeg": 1, ".png": 2}


def collect_dataset(dataset_root, validation_fraction, extra_training_root=None):
    """Memetakan folder dataset ke kelas dan membagi grup foto untuk validasi."""
    train_images = []
    validation_images = []
    excluded = {}
    extra_counts = {name: 0 for name in CLASS_NAMES}
    rng = random.Random(42)

    for folder in sorted(path for path in dataset_root.iterdir() if path.is_dir()):
        label = CLASS_FOLDERS.get(folder.name)
        if label is None:
            count = sum(
                path.is_file() and path.suffix.lower() in IMAGE_EXTENSIONS
                for path in folder.rglob("*")
            )
            excluded[folder.name] = count
            continue

        grouped_paths = defaultdict(list)
        for path in sorted(folder.rglob("*")):
            if path.is_file() and path.suffix.lower() in IMAGE_EXTENSIONS:
                # Files with the same relative stem but different extensions are variants
                # of one image; keep them together and use only one for training.
                key = path.relative_to(folder).with_suffix("").as_posix().casefold()
                grouped_paths[key].append(path)
        groups = [
            min(paths, key=lambda path: PREFERRED_EXTENSIONS[path.suffix.lower()])
            for paths in grouped_paths.values()
        ]
        if not groups:
            raise FileNotFoundError(f"Tidak ada gambar untuk kelas {folder.name} di {folder}")

        rng.shuffle(groups)
        validation_count = max(1, round(len(groups) * validation_fraction))
        validation_groups = groups[:validation_count]
        train_groups = groups[validation_count:]
        if not train_groups:
            raise ValueError(f"Terlalu sedikit grup gambar untuk melatih kelas {folder.name}.")
        class_index = CLASS_NAMES.index(label)
        train_images.extend((path, class_index) for path in train_groups)
        validation_images.extend((path, class_index) for path in validation_groups)

    if extra_training_root and extra_training_root.is_dir():
        extra_folders = {
            folder.name.casefold(): folder
            for folder in extra_training_root.iterdir()
            if folder.is_dir()
        }
        for label_index, label in enumerate(CLASS_NAMES):
            folder = extra_folders.get(label.casefold())
            if folder is None:
                continue
            paths = sorted(
                path
                for path in folder.rglob("*")
                if path.is_file() and path.suffix.lower() in IMAGE_EXTENSIONS
            )
            train_images.extend((path, label_index) for path in paths)
            extra_counts[label] = len(paths)

    represented = {label for _, label in train_images}
    missing = set(range(len(CLASS_NAMES))) - represented
    if missing:
        names = ", ".join(CLASS_NAMES[index] for index in sorted(missing))
        raise ValueError(f"Dataset tidak memiliki gambar latih untuk kelas: {names}.")
    if not validation_images:
        raise ValueError(f"Tidak ada gambar validasi di {dataset_root}.")
    return train_images, validation_images, excluded, extra_counts


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
    """Menghitung akurasi, precision/recall per kelas, dan matriks kebingungan."""
    predictions = np.argmax(probabilities, axis=1)
    matrix = np.zeros((len(CLASS_NAMES), len(CLASS_NAMES)), dtype=np.int64)
    for expected, predicted in zip(labels, predictions):
        matrix[expected, predicted] += 1
    per_class = {}
    for index, name in enumerate(CLASS_NAMES):
        true_positive = int(matrix[index, index])
        predicted_total = int(matrix[:, index].sum())
        actual_total = int(matrix[index].sum())
        per_class[name] = {
            "correct": true_positive,
            "total": actual_total,
            "precision": true_positive / predicted_total if predicted_total else 0.0,
            "recall": true_positive / actual_total if actual_total else 0.0,
        }
    return {
        "accuracy": float(np.mean(predictions == labels)),
        "per_class": per_class,
        "confusion_matrix": matrix.tolist(),
    }


def class_counts(samples):
    """Menghitung jumlah sampel pada setiap kelas."""
    return {
        name: sum(label == index for _, label in samples)
        for index, name in enumerate(CLASS_NAMES)
    }


def main():
    """Melatih model kandidat tiga kelas, mengevaluasinya, lalu menyimpan hasil."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--dataset",
        type=Path,
        default=ROOT / "new dataset" / "archive (1)" / "Dataset_ThirdStage" / "Dataset",
    )
    parser.add_argument(
        "--source-model", type=Path, default=ROOT / "model" / "keras_model.h5"
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=ROOT / "model" / "keras_model_3class_candidate_v2.h5",
    )
    parser.add_argument(
        "--extra-training",
        type=Path,
        default=ROOT / "dataset" / "real_examples",
        help="Optional extra training images in one subfolder per class.",
    )
    parser.add_argument("--epochs", type=int, default=20)
    parser.add_argument("--batch-size", type=int, default=32)
    parser.add_argument("--validation-fraction", type=float, default=0.2)
    parser.add_argument(
        "--inspect-only",
        action="store_true",
        help="Count the mapped images and splits without loading or training a model.",
    )
    args = parser.parse_args()
    if args.epochs < 1 or args.batch_size < 1:
        parser.error("--epochs and --batch-size must be positive")
    if not 0 < args.validation_fraction < 1:
        parser.error("--validation-fraction must be between 0 and 1")
    if not args.dataset.is_dir():
        parser.error(f"Dataset folder not found: {args.dataset}")
    if args.output.resolve() == args.source_model.resolve():
        parser.error("Output kandidat tidak boleh menimpa model sumber.")

    train_samples, validation_samples, excluded, extra_counts = collect_dataset(
        args.dataset, args.validation_fraction, args.extra_training
    )
    print(
        f"Data latih: {len(train_samples)} {class_counts(train_samples)}; "
        f"validasi: {len(validation_samples)} {class_counts(validation_samples)}."
    )
    print(f"Contoh tambahan yang hanya masuk data latih: {extra_counts}")
    print(f"Kelas yang tidak dipakai: {json.dumps(excluded, ensure_ascii=False)}")
    if args.inspect_only:
        return

    keras.utils.set_random_seed(42)
    previous_model = keras.models.load_model(args.source_model, compile=False)
    if previous_model.input_shape != (None, 224, 224, 3):
        raise ValueError(f"Bentuk masukan model sumber tidak sesuai: {previous_model.input_shape}")
    feature_extractor = previous_model.layers[1]
    feature_extractor.trainable = False
    train_features, train_labels = extract_features(
        train_samples, feature_extractor, args.batch_size, "data latih"
    )
    validation_features, validation_labels = extract_features(
        validation_samples, feature_extractor, args.batch_size, "validasi"
    )

    old_head = previous_model.layers[-1]
    old_hidden = old_head.get_layer("waste_hidden")
    head_input = keras.Input(shape=(train_features.shape[1],), name="features")
    hidden = keras.layers.Dense(100, activation="relu", name="waste_hidden")
    hidden_output = hidden(head_input)
    dropped = keras.layers.Dropout(0.15, name="waste_dropout")(hidden_output)
    output = keras.layers.Dense(
        len(CLASS_NAMES), activation="softmax", name="waste_categories"
    )(dropped)
    classifier = keras.Model(head_input, output, name="pilahpintar_3class_classifier")
    hidden.set_weights(old_hidden.get_weights())
    classifier.compile(
        optimizer=keras.optimizers.Adam(learning_rate=0.0005),
        loss="sparse_categorical_crossentropy",
        metrics=["accuracy"],
    )
    train_counts = class_counts(train_samples)
    total_train = len(train_samples)
    class_weights = {
        index: total_train / (len(CLASS_NAMES) * train_counts[name])
        for index, name in enumerate(CLASS_NAMES)
    }
    classifier.fit(
        train_features,
        train_labels,
        validation_data=(validation_features, validation_labels),
        class_weight=class_weights,
        batch_size=128,
        epochs=args.epochs,
        callbacks=[
            keras.callbacks.EarlyStopping(
                monitor="val_accuracy", patience=4, restore_best_weights=True
            )
        ],
        verbose=2,
    )

    probabilities = classifier.predict(
        validation_features, batch_size=256, verbose=0
    )
    report = {
        "class_names": list(CLASS_NAMES),
        "source_dataset": str(args.dataset),
        "training_images": len(train_samples),
        "validation_images": len(validation_samples),
        "training_counts": class_counts(train_samples),
        "validation_counts": class_counts(validation_samples),
        "extra_training_counts": extra_counts,
        "excluded_folder_counts": excluded,
        "mapping": CLASS_FOLDERS,
        "candidate": class_metrics(probabilities, validation_labels),
        "limitations": [
            "Validasi menggunakan pemisahan grup nama file dan belum menggantikan uji foto lapangan.",
            "Label B3 hanya mengikuti folder dataset; produk berbeda dapat memiliki bahaya berbeda.",
            "Hasil AI tidak boleh menjadi satu-satunya dasar penanganan limbah berbahaya.",
            "Model kandidat tidak menggantikan model aplikasi secara otomatis.",
        ],
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    model_input = keras.Input(shape=(224, 224, 3), name="image")
    model_features = feature_extractor(model_input, training=False)
    model_output = classifier(model_features, training=False)
    full_model = keras.Model(
        model_input, model_output, name="pilahpintar_3class_model"
    )
    full_model.save(args.output)
    loaded_model = keras.models.load_model(args.output, compile=False)
    if loaded_model.input_shape != (None, 224, 224, 3) or loaded_model.output_shape != (
        None,
        len(CLASS_NAMES),
    ):
        raise ValueError(f"Bentuk model ekspor tidak sesuai: {loaded_model.input_shape}, {loaded_model.output_shape}")

    report_path = args.output.with_suffix(".json")
    report_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    labels_path = args.output.with_name(
        f"labels_{args.output.stem.removeprefix('keras_model_')}.txt"
    )
    labels_path.write_text(
        "".join(f"{index} {name}\n" for index, name in enumerate(CLASS_NAMES)),
        encoding="utf-8",
    )
    print("Metrik validasi:")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    print(f"Kandidat model disimpan ke {args.output}")
    print(f"Label kandidat disimpan ke {labels_path}")
    print("Kandidat belum menggantikan model aplikasi.")


if __name__ == "__main__":
    main()
