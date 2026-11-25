"""Kirim pesan pemulihan akun melalui SMTP dengan koneksi TLS."""
from email.message import EmailMessage
import smtplib
import ssl


class EmailDeliveryError(RuntimeError):
    """Kesalahan yang dapat ditampilkan saat email pemulihan gagal dikirim."""


def kirim_kode_reset(penerima, token, konfigurasi):
    """Mengirim token reset dengan STARTTLS memakai konfigurasi SMTP aplikasi."""
    host = str(konfigurasi.get("host", "")).strip()
    username = str(konfigurasi.get("username", "")).strip()
    password = str(konfigurasi.get("password", ""))
    pengirim = str(konfigurasi.get("sender", username)).strip()
    try:
        port = int(konfigurasi.get("port", 587))
    except (TypeError, ValueError) as error:
        raise EmailDeliveryError("Port SMTP harus berupa angka.") from error

    if not all((host, username, password, pengirim)):
        raise EmailDeliveryError(
            "Konfigurasi SMTP belum lengkap. Isi host, username, password, dan sender."
        )
    if not 1 <= port <= 65535:
        raise EmailDeliveryError("Port SMTP harus di antara 1 dan 65535.")
    if any("\n" in nilai or "\r" in nilai for nilai in (host, username, pengirim)):
        raise EmailDeliveryError("Konfigurasi SMTP mengandung nilai yang tidak valid.")

    pesan = EmailMessage()
    pesan["Subject"] = "Kode reset kata sandi W-Sort"
    pesan["From"] = pengirim
    pesan["To"] = penerima
    pesan.set_content(
        "Kami menerima permintaan untuk mengatur ulang kata sandi akun W-Sort.\n\n"
        f"Kode reset Anda:\n{token}\n\n"
        "Kode berlaku selama 15 menit dan hanya dapat digunakan sekali. "
        "Jika Anda tidak meminta reset, abaikan email ini."
    )

    try:
        with smtplib.SMTP(host, port, timeout=15) as server:
            server.ehlo()
            server.starttls(context=ssl.create_default_context())
            server.ehlo()
            server.login(username, password)
            ditolak = server.send_message(pesan)
            if ditolak:
                raise smtplib.SMTPRecipientsRefused(ditolak)
    except smtplib.SMTPAuthenticationError as error:
        raise EmailDeliveryError(
            f"Login SMTP ditolak (kode {error.smtp_code}). "
            "Periksa username dan App Password email."
        ) from error
    except smtplib.SMTPRecipientsRefused as error:
        raise EmailDeliveryError(
            "Server SMTP menolak alamat pengirim atau penerima. "
            "Periksa nilai sender dan alamat email akun."
        ) from error
    except smtplib.SMTPNotSupportedError as error:
        raise EmailDeliveryError(
            "Server SMTP tidak mendukung STARTTLS. Gunakan host dan port "
            "SMTP STARTTLS yang benar, biasanya port 587."
        ) from error
    except ssl.SSLError as error:
        raise EmailDeliveryError(
            "Negosiasi TLS dengan server email gagal. Periksa host dan port SMTP."
        ) from error
    except smtplib.SMTPConnectError as error:
        raise EmailDeliveryError(
            f"Server SMTP menolak koneksi (kode {error.smtp_code}). "
            "Periksa host dan port SMTP."
        ) from error
    except (OSError, smtplib.SMTPException) as error:
        kode_smtp = getattr(error, "smtp_code", None)
        rincian = f"kode SMTP {kode_smtp}" if kode_smtp else type(error).__name__
        raise EmailDeliveryError(
            f"Email reset gagal dikirim ({rincian}). "
            "Periksa koneksi dan konfigurasi SMTP."
        ) from error
