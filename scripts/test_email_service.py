"""Uji pengiriman kode reset tanpa menghubungi server SMTP sungguhan."""
import sys
import smtplib
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import email_service


class EmailServiceTests(unittest.TestCase):
    """Memeriksa konfigurasi dan pesan yang diserahkan ke SMTP."""

    @patch("email_service.smtplib.SMTP")
    def test_sends_reset_token_over_starttls(self, smtp_factory):
        """Pesan berisi token dikirim setelah koneksi STARTTLS dibuat."""
        smtp = Mock()
        smtp.__enter__ = Mock(return_value=smtp)
        smtp.__exit__ = Mock(return_value=False)
        smtp.send_message.return_value = {}
        smtp_factory.return_value = smtp
        configuration = {
            "host": "smtp.example.com",
            "port": 587,
            "username": "sender@example.com",
            "password": "test-secret",
            "sender": "sender@example.com",
        }

        email_service.kirim_kode_reset(
            "student@example.com", "reset-token", configuration
        )

        smtp.starttls.assert_called_once()
        message = smtp.send_message.call_args.args[0]
        self.assertEqual(message["To"], "student@example.com")
        self.assertIn("reset-token", message.get_content())

    def test_missing_smtp_configuration_is_reported(self):
        """Konfigurasi yang tidak lengkap ditolak sebelum membuat koneksi."""
        with self.assertRaises(email_service.EmailDeliveryError):
            email_service.kirim_kode_reset(
                "student@example.com", "reset-token", {}
            )

    @patch("email_service.smtplib.SMTP")
    def test_authentication_error_is_explained_without_exposing_credentials(
        self, smtp_factory
    ):
        """Kegagalan login SMTP memberi petunjuk tanpa mencetak kata sandi."""
        smtp = Mock()
        smtp.__enter__ = Mock(return_value=smtp)
        smtp.__exit__ = Mock(return_value=False)
        smtp.login.side_effect = smtplib.SMTPAuthenticationError(
            535, b"authentication failed"
        )
        smtp_factory.return_value = smtp
        configuration = {
            "host": "smtp.example.com",
            "port": 587,
            "username": "sender@example.com",
            "password": "do-not-display-this",
            "sender": "sender@example.com",
        }

        with self.assertRaises(email_service.EmailDeliveryError) as error:
            email_service.kirim_kode_reset(
                "student@example.com", "reset-token", configuration
            )

        self.assertIn("Login SMTP ditolak", str(error.exception))
        self.assertNotIn("do-not-display-this", str(error.exception))


if __name__ == "__main__":
    unittest.main()
