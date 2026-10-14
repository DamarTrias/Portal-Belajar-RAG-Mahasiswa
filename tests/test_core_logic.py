"""Uji unit offline untuk logika yang tidak membutuhkan layanan eksternal."""
import hashlib
import secrets
import sys
import types
import unittest

# Mock database dan layanan AI sebelum modul inti diimpor agar uji tidak menghubungi API.
_fake_db = types.SimpleNamespace(db=object())
_fake_ai = types.SimpleNamespace(llm=None, to_text=lambda value: str(value))
sys.modules.setdefault("core.db", _fake_db)
sys.modules.setdefault("core.ai", _fake_ai)

from core.auth import PBKDF2_ITERATIONS, hash_password, verify_password
from core.generator import Kuis, Soal, _validate_quiz, select_spread_rows


class PasswordHashTests(unittest.TestCase):
    def test_new_hash_verifies_and_rejects_wrong_password(self):
        password = "example-password-123"
        stored = hash_password(password)
        self.assertTrue(stored.startswith(f"pbkdf2_sha256${PBKDF2_ITERATIONS}$"))
        self.assertTrue(verify_password(password, stored))
        self.assertFalse(verify_password("wrong-password", stored))

    def test_legacy_hash_remains_verifiable(self):
        password = "example-password-123"
        salt = secrets.token_hex(16)
        digest = hashlib.pbkdf2_hmac(
            "sha256", password.encode("utf-8"), salt.encode("utf-8"), 100_000
        ).hex()
        self.assertTrue(verify_password(password, f"{salt}${digest}"))
        self.assertFalse(verify_password("wrong-password", f"{salt}${digest}"))


class ChunkSamplingTests(unittest.TestCase):
    def test_selects_up_to_15_spread_across_ordered_rows(self):
        rows = [{"id": row_index, "content": str(row_index), "citation": f"page {row_index}"} for row_index in range(100)]
        selected = select_spread_rows(rows, 15)
        selected_ids = [row["id"] for row in selected]
        self.assertEqual(len(selected), 15)
        self.assertEqual(selected_ids[0], 0)
        self.assertEqual(selected_ids[-1], 99)
        self.assertEqual(len(set(selected_ids)), 15)
        self.assertEqual(selected_ids, sorted(selected_ids))

    def test_returns_all_rows_when_under_limit(self):
        rows = [{"id": row_index} for row_index in range(10)]
        self.assertEqual(select_spread_rows(rows, 15), rows)
        self.assertEqual(select_spread_rows(rows, 0), [])


class QuizValidationTests(unittest.TestCase):
    def test_accepts_four_labeled_options_and_normalizes_answer(self):
        question = Soal(
            pertanyaan="Pertanyaan?",
            pilihan=["A. Satu", "B. Dua", "C. Tiga", "D. Empat"],
            jawaban="B. Dua",
            pembahasan="Pembahasan singkat.",
            sumber="materi.pdf (Hal 1)",
        )
        result = _validate_quiz(Kuis(soal=[question]), 1, "Pilihan Ganda")
        self.assertEqual(result[0].jawaban, "B")

    def test_rejects_invalid_answer_key(self):
        question = Soal(
            pertanyaan="Pertanyaan?",
            pilihan=["A. Satu", "B. Dua", "C. Tiga", "D. Empat"],
            jawaban="Z",
            pembahasan="Pembahasan singkat.",
            sumber="materi.pdf (Hal 1)",
        )
        with self.assertRaises(ValueError):
            _validate_quiz(Kuis(soal=[question]), 1, "Pilihan Ganda")


if __name__ == "__main__":
    unittest.main()
