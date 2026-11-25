"""Uji alur kode pemulihan kata sandi dan migrasi tabel akun lama."""
import hashlib
import sqlite3
import sys
import tempfile
import unittest
from contextlib import closing
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import database as db


class PasswordRecoveryTests(unittest.TestCase):
    """Memeriksa kode pemulihan tanpa memakai database proyek."""

    def setUp(self):
        """Membuat database sementara dengan struktur akun versi lama."""
        self.temp_dir = tempfile.TemporaryDirectory()
        self.database_asli = db.DB_PATH
        db.DB_PATH = str(Path(self.temp_dir.name) / "smartwaste.db")

        salt = b"legacy-test-salt"
        hash_kata_sandi = hashlib.pbkdf2_hmac(
            "sha256", b"old-password", salt, db.ITERASI_HASH_KATA_SANDI
        ).hex()
        with closing(sqlite3.connect(db.DB_PATH)) as conn:
            conn.execute(
                """CREATE TABLE pengguna (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    nama TEXT NOT NULL,
                    email TEXT NOT NULL COLLATE NOCASE UNIQUE,
                    hash_kata_sandi TEXT NOT NULL,
                    salt_kata_sandi TEXT NOT NULL,
                    iterasi_hash INTEGER NOT NULL,
                    dibuat TEXT NOT NULL
                )"""
            )
            conn.execute(
                "INSERT INTO pengguna "
                "(nama, email, hash_kata_sandi, salt_kata_sandi, iterasi_hash, dibuat) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (
                    "Legacy",
                    "legacy@example.com",
                    hash_kata_sandi,
                    salt.hex(),
                    db.ITERASI_HASH_KATA_SANDI,
                    "2026-01-01 00:00:00",
                ),
            )
            conn.commit()
        db.buat_tabel_auth()

    def tearDown(self):
        """Memulihkan lokasi database dan menghapus data sementara."""
        db.DB_PATH = self.database_asli
        self.temp_dir.cleanup()

    def test_existing_account_can_reset_once_with_recovery_code(self):
        """Migrasi menambah kode pemulihan dan reset memakai kode hanya sekali."""
        code = db.buat_kode_pemulihan_jika_belum_ada(1)
        self.assertIsNotNone(code)
        self.assertIsNone(db.buat_kode_pemulihan_jika_belum_ada(1))

        self.assertIsNone(
            db.reset_kata_sandi(
                "legacy@example.com", "kode-salah", "new-password"
            )
        )
        self.assertIsNotNone(
            db.masuk_pengguna("legacy@example.com", "old-password")
        )

        next_code = db.reset_kata_sandi(
            "legacy@example.com", code, "new-password"
        )
        self.assertIsNotNone(next_code)
        self.assertIsNone(
            db.reset_kata_sandi(
                "legacy@example.com", code, "another-password"
            )
        )
        self.assertIsNone(db.masuk_pengguna("legacy@example.com", "old-password"))
        self.assertIsNotNone(
            db.masuk_pengguna("legacy@example.com", "new-password")
        )

    def test_new_account_stores_only_a_hash_of_recovery_code(self):
        """Akun baru mendapat kode, tetapi database hanya menyimpan hash-nya."""
        account = db.daftar_pengguna(
            "Student", "student@example.com", "student-password"
        )
        with closing(sqlite3.connect(db.DB_PATH)) as conn:
            stored_hash = conn.execute(
                "SELECT hash_kode_pemulihan FROM pengguna WHERE email = ?",
                ("student@example.com",),
            ).fetchone()[0]

        self.assertNotEqual(stored_hash, account["kode_pemulihan"])
        self.assertEqual(len(stored_hash), 64)
        rotated_code = db.ganti_kode_pemulihan(account["id"])
        self.assertIsNone(
            db.reset_kata_sandi(
                "student@example.com",
                account["kode_pemulihan"],
                "changed-password",
            )
        )
        self.assertIsNotNone(
            db.reset_kata_sandi(
                "student@example.com",
                rotated_code,
                "changed-password",
            )
        )
        self.assertIsNotNone(
            db.masuk_pengguna("student@example.com", "changed-password")
        )

    def test_email_token_resets_password_once_and_rotates_recovery_code(self):
        """Token email yang disimpan sebagai hash hanya dapat mereset sekali."""
        token = db.buat_token_reset("legacy@example.com")
        self.assertIsNotNone(token)
        self.assertIsNone(db.buat_token_reset("legacy@example.com"))

        with closing(sqlite3.connect(db.DB_PATH)) as conn:
            stored_hash = conn.execute(
                "SELECT hash_token FROM token_reset_kata_sandi"
            ).fetchone()[0]
        self.assertNotEqual(stored_hash, token)

        new_recovery_code = db.reset_kata_sandi_dengan_token(
            "legacy@example.com", token, "email-password"
        )
        self.assertIsNotNone(new_recovery_code)
        self.assertIsNone(
            db.reset_kata_sandi_dengan_token(
                "legacy@example.com", token, "another-password"
            )
        )
        self.assertIsNone(
            db.masuk_pengguna("legacy@example.com", "old-password")
        )
        self.assertIsNotNone(
            db.masuk_pengguna("legacy@example.com", "email-password")
        )

    def test_expired_email_token_is_rejected(self):
        """Token email yang melewati batas waktu tidak mengubah kata sandi."""
        token = db.buat_token_reset("legacy@example.com")
        waktu_kedaluwarsa = (
            datetime.now(timezone.utc) - timedelta(minutes=1)
        ).isoformat(timespec="seconds")
        with closing(sqlite3.connect(db.DB_PATH)) as conn:
            conn.execute(
                "UPDATE token_reset_kata_sandi SET kedaluwarsa = ?",
                (waktu_kedaluwarsa,),
            )
            conn.commit()

        self.assertIsNone(
            db.reset_kata_sandi_dengan_token(
                "legacy@example.com", token, "new-password"
            )
        )
        self.assertIsNotNone(
            db.masuk_pengguna("legacy@example.com", "old-password")
        )


if __name__ == "__main__":
    unittest.main()
