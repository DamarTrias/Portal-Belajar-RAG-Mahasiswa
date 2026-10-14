"""Autentikasi mahasiswa: registrasi dan login dengan hash kata sandi PBKDF2."""
import hashlib
import hmac
import re
import secrets
from typing import Any, Dict, Optional, Tuple

from core.db import db


# Jumlah iterasi PBKDF2 saat ini dan untuk format hash lama (backward-compatible).
PBKDF2_ITERATIONS = 600_000
LEGACY_PBKDF2_ITERATIONS = 100_000


def hash_password(password: str) -> str:
    """
    Menghasilkan hash PBKDF2-HMAC-SHA256 dengan salt acak yang unik.
    Format keluaran: `pbkdf2_sha256$<iterasi>$<salt>$<hash_hex>`
    Format ini menyimpan semua parameter agar verifikasi tidak perlu konfigurasi tambahan.
    """
    salt = secrets.token_hex(16)
    hashed_key = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        salt.encode("utf-8"),
        PBKDF2_ITERATIONS,
    )
    return f"pbkdf2_sha256${PBKDF2_ITERATIONS}${salt}${hashed_key.hex()}"


def verify_password(password: str, stored_hash: str) -> bool:
    """
    Memverifikasi kata sandi terhadap hash yang tersimpan di basis data.
    Mendukung dua format hash:
    - Format baru (4 bagian): `pbkdf2_sha256$<iterasi>$<salt>$<hash_hex>`
    - Format lama (2 bagian): `<salt>$<hash_hex>` dengan 100.000 iterasi
    """
    if not stored_hash:
        return False

    try:
        hash_parts = stored_hash.split("$")

        if len(hash_parts) == 4 and hash_parts[0] == "pbkdf2_sha256":
            # Format baru: baca parameter iterasi langsung dari hash.
            iterations = int(hash_parts[1])
            salt, expected_key = hash_parts[2], hash_parts[3]
            if iterations < 1 or not re.fullmatch(r"[0-9a-f]+", expected_key):
                return False

        elif len(hash_parts) == 2:
            # Format lama: gunakan iterasi default untuk akun lama.
            salt, expected_key = hash_parts
            iterations = LEGACY_PBKDF2_ITERATIONS

        else:
            return False

        computed_key = hashlib.pbkdf2_hmac(
            "sha256",
            password.encode("utf-8"),
            salt.encode("utf-8"),
            iterations,
        )
        # Gunakan compare_digest untuk menghindari timing attack.
        return hmac.compare_digest(computed_key.hex(), expected_key)

    except (TypeError, ValueError):
        return False


def register_user(name: str, nim: str, password: str) -> Tuple[bool, str]:
    """
    Mendaftarkan mahasiswa baru ke tabel `students`.
    Mengembalikan (True, pesan_sukses) atau (False, pesan_error).
    """
    name = name.strip()
    nim = nim.strip()
    password = password.strip()

    # Validasi input sebelum menyentuh basis data.
    if len(name) < 3:
        return False, "Nama lengkap minimal 3 karakter."
    if not nim:
        return False, "NIM wajib diisi."
    if len(password) < 6:
        return False, "Kata sandi minimal 6 karakter."

    try:
        # Cek apakah NIM sudah terdaftar.
        existing = db.table("students").select("id").eq("nim", nim).execute()
        if existing.data:
            return False, f"NIM '{nim}' sudah terdaftar. Silakan gunakan NIM lain atau login."

        # Simpan akun baru dengan kata sandi yang sudah di-hash.
        insert_result = db.table("students").insert({
            "name": name,
            "nim": nim,
            "password_hash": hash_password(password),
        }).execute()

        if insert_result.data:
            return True, "Pendaftaran berhasil! Silakan masuk menggunakan akun baru Anda."
        return False, "Gagal menyimpan akun ke basis data."

    except Exception as error:
        return False, f"Terjadi kesalahan saat pendaftaran: {error}"


def login_user(nim: str, password: str) -> Tuple[bool, Optional[Dict[str, Any]], str]:
    """
    Memeriksa NIM dan kata sandi mahasiswa.
    Mengembalikan tuple (sukses, data_mahasiswa, pesan).
    - Jika berhasil: (True, dict berisi id/name/nim, pesan sukses)
    - Jika gagal   : (False, None, pesan error)

    Secara otomatis memigrasikan hash lama ke format iterasi baru saat login berhasil.
    """
    nim = nim.strip()
    password = password.strip()

    if not nim or not password:
        return False, None, "NIM dan kata sandi wajib diisi."

    try:
        result = db.table("students").select("*").eq("nim", nim).execute()
        if not result.data:
            return False, None, "NIM tidak ditemukan. Pastikan NIM sudah benar atau daftar akun baru."

        student = result.data[0]
        stored_hash = student.get("password_hash")

        if not stored_hash:
            return False, None, "Akun ini belum memiliki kata sandi. Silakan daftarkan ulang akun Anda."

        if not verify_password(password, stored_hash):
            return False, None, "Kata sandi salah. Silakan periksa kembali."

        # Migrasikan hash lama ke format baru saat login berhasil.
        is_old_hash_format = not stored_hash.startswith(f"pbkdf2_sha256${PBKDF2_ITERATIONS}$")
        if is_old_hash_format:
            try:
                db.table("students").update({
                    "password_hash": hash_password(password)
                }).eq("id", student["id"]).execute()
            except Exception:
                # Kegagalan migrasi hash tidak membatalkan login yang valid.
                pass

        # Kembalikan hanya data yang diperlukan UI; hash tidak boleh ada di session.
        safe_student_data = {
            "id": student["id"],
            "name": student.get("name", ""),
            "nim": student.get("nim", ""),
        }
        return True, safe_student_data, "Login berhasil!"

    except Exception as error:
        return False, None, f"Terjadi kesalahan saat verifikasi: {error}"
