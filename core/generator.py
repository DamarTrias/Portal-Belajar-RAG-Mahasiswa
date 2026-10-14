"""Pembuatan soal latihan dan flashcard dari sampel potongan materi mahasiswa."""
import json
import re
from typing import Any, Dict, List, Optional, Tuple

from pydantic import BaseModel, Field

from core.ai import llm, to_text
from core.db import db

# Batas maksimal chunk yang diambil sebagai sampel konteks untuk generasi.
CHUNK_SAMPLE_LIMIT = 15
# Ukuran halaman saat mengambil chunk dari database secara bertahap (pagination).
DB_PAGE_SIZE = 500


# ==============================================================================
# Model Data (Pydantic)
# ==============================================================================

class Soal(BaseModel):
    pertanyaan: str = Field(min_length=1, description="Teks butir soal")
    pilihan: List[str] = Field(
        default_factory=list,
        description="Empat opsi pilihan ganda berlabel A-D; kosong untuk esai.",
    )
    jawaban: str = Field(min_length=1, description="Kunci berupa A-D untuk pilihan ganda atau jawaban ideal untuk esai.")
    pembahasan: str = Field(min_length=1, description="Penjelasan jawaban.")
    sumber: str = Field(min_length=1, description="Nama berkas dan lokasi sumber.")


class Kuis(BaseModel):
    soal: List[Soal] = Field(min_length=1)


class Kartu(BaseModel):
    depan: str = Field(min_length=1, description="Pertanyaan atau konsep pada sisi depan.")
    belakang: str = Field(min_length=1, description="Jawaban atau penjelasan pada sisi belakang.")


class SetKartu(BaseModel):
    kartu: List[Kartu] = Field(min_length=1)


# ==============================================================================
# Fungsi Pembantu (Helper)
# ==============================================================================

def extract_json_from_text(text: str) -> dict:
    """
    Mengekstrak objek JSON dari teks jawaban model.
    Menangani kasus di mana JSON dibungkus blok markdown (```json ... ```).
    """
    # Hapus pembungkus markdown jika ada.
    cleaned = re.sub(r"^```(?:json)?\s*", "", text.strip(), flags=re.MULTILINE)
    cleaned = re.sub(r"\s*```$", "", cleaned, flags=re.MULTILINE)

    # Ambil objek JSON pertama yang ditemukan.
    json_match = re.search(r"\{.*\}", cleaned, re.DOTALL)
    if json_match:
        cleaned = json_match.group(0)

    return json.loads(cleaned)


def _fetch_student_chunks(student_id: str, doc_id: Optional[str]) -> List[Dict[str, Any]]:
    """
    Mengambil semua chunk milik mahasiswa dari database menggunakan pagination.
    Pagination digunakan agar tidak ada chunk yang terlewat pada dokumen besar.
    """
    all_chunks: List[Dict[str, Any]] = []
    page_start = 0

    while True:
        query = (
            db.table("chunks")
            .select("id, content, citation")
            .eq("student_id", student_id)
            .order("id")
            .range(page_start, page_start + DB_PAGE_SIZE - 1)
        )
        if doc_id:
            query = query.eq("document_id", doc_id)

        page_data = query.execute().data or []
        all_chunks.extend(page_data)

        # Jika data yang dikembalikan lebih sedikit dari ukuran halaman, berarti sudah habis.
        if len(page_data) < DB_PAGE_SIZE:
            break
        page_start += DB_PAGE_SIZE

    return all_chunks


def select_spread_rows(rows: List[Dict[str, Any]], limit: int = CHUNK_SAMPLE_LIMIT) -> List[Dict[str, Any]]:
    """
    Memilih paling banyak `limit` chunk yang tersebar merata dari seluruh daftar.
    Teknik ini memastikan sampel mewakili seluruh dokumen (awal, tengah, akhir),
    bukan hanya bagian awal.
    """
    if limit <= 0 or not rows:
        return []
    if len(rows) <= limit:
        return rows
    if limit == 1:
        return [rows[len(rows) // 2]]

    # Hitung indeks yang tersebar merata dari 0 hingga len(rows)-1.
    spread_indexes = [round(position * (len(rows) - 1) / (limit - 1)) for position in range(limit)]
    return [rows[index] for index in spread_indexes]


def get_context_selection(
    student_id: str,
    doc_id: Optional[str] = None,
    limit: int = CHUNK_SAMPLE_LIMIT,
) -> Tuple[str, int, int]:
    """
    Mengambil sampel chunk dan menggabungkannya menjadi satu string konteks.
    Mengembalikan (teks_konteks, jumlah_chunk_terpilih, jumlah_chunk_keseluruhan).
    """
    all_chunks = _fetch_student_chunks(student_id, doc_id)
    if not all_chunks:
        raise ValueError("Belum ada materi untuk akun atau dokumen ini. Silakan unggah materi terlebih dahulu.")

    selected_chunks = select_spread_rows(all_chunks, limit)
    context_text = "\n\n".join(
        f"({chunk['citation']})\n{chunk['content']}" for chunk in selected_chunks
    )
    return context_text, len(selected_chunks), len(all_chunks)


def get_context(student_id: str, doc_id: Optional[str] = None, limit: int = CHUNK_SAMPLE_LIMIT) -> str:
    """Mengambil teks konteks sampel saja (tanpa mengembalikan statistik jumlah chunk)."""
    context_text, _selected_count, _total_count = get_context_selection(student_id, doc_id, limit)
    return context_text


# ==============================================================================
# Validasi Output Model
# ==============================================================================

def _validate_quiz(quiz: Kuis, expected_count: int, question_type: str) -> List[Soal]:
    """
    Memvalidasi struktur dan konten soal yang dihasilkan model.
    Memastikan jumlah soal, kelengkapan field, dan format opsi pilihan ganda sudah benar.
    """
    if len(quiz.soal) != expected_count:
        raise ValueError(f"Model menghasilkan {len(quiz.soal)} soal, sedangkan yang diminta {expected_count}.")

    for question_num, soal in enumerate(quiz.soal, 1):
        # Pastikan semua field teks tidak kosong.
        required_fields = [soal.pertanyaan, soal.jawaban, soal.pembahasan, soal.sumber]
        if not all(field.strip() for field in required_fields):
            raise ValueError(f"Soal nomor {question_num} memiliki bagian kosong.")

        if question_type == "Pilihan Ganda":
            # Validasi jumlah opsi.
            if len(soal.pilihan) != 4:
                raise ValueError(f"Soal pilihan ganda nomor {question_num} harus memiliki empat opsi.")

            # Validasi label A-D pada setiap opsi.
            option_labels = []
            for option in soal.pilihan:
                label_match = re.match(r"^\s*([A-D])[.)]\s*\S", option)
                if not label_match:
                    raise ValueError(f"Opsi soal nomor {question_num} harus menggunakan label A, B, C, dan D.")
                option_labels.append(label_match.group(1))

            if sorted(option_labels) != ["A", "B", "C", "D"]:
                raise ValueError(f"Label opsi soal nomor {question_num} harus terdiri dari A, B, C, dan D tanpa duplikasi.")

            # Normalisasi kunci jawaban menjadi huruf tunggal (A/B/C/D).
            answer_match = re.match(r"^\s*([A-D])(?:[.)]\s*.*)?$", soal.jawaban, flags=re.DOTALL)
            if not answer_match:
                raise ValueError(f"Kunci jawaban soal nomor {question_num} harus berupa huruf A, B, C, atau D.")
            soal.jawaban = answer_match.group(1)

        elif soal.pilihan:
            # Soal esai tidak boleh memiliki opsi pilihan ganda.
            raise ValueError(f"Soal esai nomor {question_num} tidak boleh memiliki opsi pilihan ganda.")

    return quiz.soal


# ==============================================================================
# Fungsi Generasi Utama
# ==============================================================================

def make_quiz(
    student_id: str,
    doc_id: Optional[str],
    question_count: int,
    difficulty: str,
    question_type: str,
) -> List[Soal]:
    """
    Membuat soal kuis (pilihan ganda atau esai) dari sampel materi mahasiswa.
    Soal divalidasi sebelum dikembalikan; RuntimeError dimunculkan jika format tidak sesuai.
    """
    context = get_context(student_id, doc_id)

    if question_type == "Pilihan Ganda":
        aturan = "pilihan ganda dengan empat opsi berlabel A, B, C, D"
        format_contoh = '{"pertanyaan":"...","pilihan":["A. ...","B. ...","C. ...","D. ..."],"jawaban":"A","pembahasan":"...","sumber":"nama berkas (Hal/Slide ...)"}'
    else:
        aturan = "esai; pilihan harus berupa daftar kosong [] dan jawaban berisi jawaban ideal"
        format_contoh = '{"pertanyaan":"...","pilihan":[],"jawaban":"...","pembahasan":"...","sumber":"nama berkas (Hal/Slide ...)"}'

    prompt = (
        f"Buat tepat {question_count} soal {aturan} dengan tingkat kesulitan {difficulty}. Gunakan hanya informasi dari konteks. "
        "Untuk soal pilihan ganda, isi kolom jawaban hanya dengan huruf A, B, C, atau D. "
        "Cantumkan sumber berdasarkan label yang tersedia.\n\n"
        f"KONTEKS MATERI (maksimal {CHUNK_SAMPLE_LIMIT} potongan yang dipilih merata dari materi):\n{context}\n\n"
        "Kembalikan hanya JSON valid dengan bentuk berikut:\n"
        f'{{"soal":[{format_contoh}]}}'
    )

    raw_text = to_text(llm.invoke(prompt))
    try:
        parsed_json = extract_json_from_text(raw_text)
        quiz = Kuis.model_validate(parsed_json)
        return _validate_quiz(quiz, question_count, question_type)
    except Exception as parse_error:
        raise RuntimeError(f"Format soal dari model belum sesuai: {parse_error}. Silakan buat soal kembali.") from parse_error


def make_flashcards(student_id: str, doc_id: Optional[str], card_count: int) -> List[Kartu]:
    """
    Membuat flashcard berbahasa Indonesia dari sampel materi mahasiswa.
    Setiap kartu memiliki sisi depan (pertanyaan/konsep) dan belakang (jawaban ringkas).
    RuntimeError dimunculkan jika jumlah atau format kartu tidak sesuai.
    """
    context = get_context(student_id, doc_id)

    prompt = (
        f"Buat tepat {card_count} flashcard berbahasa Indonesia dari konteks berikut. "
        "Sisi depan berisi pertanyaan atau konsep utama, sedangkan sisi belakang berisi jawaban singkat. "
        "Gunakan hanya informasi pada konteks dan kembalikan hanya JSON valid.\n\n"
        f"KONTEKS MATERI (maksimal {CHUNK_SAMPLE_LIMIT} potongan yang dipilih merata dari materi):\n{context}\n\n"
        'Format: {"kartu":[{"depan":"Pertanyaan atau konsep","belakang":"Jawaban ringkas"}]}'
    )

    raw_text = to_text(llm.invoke(prompt))
    try:
        parsed_json = extract_json_from_text(raw_text)
        flashcards = SetKartu.model_validate(parsed_json).kartu

        if len(flashcards) != card_count:
            raise ValueError(f"Model menghasilkan {len(flashcards)} kartu, sedangkan yang diminta {card_count}.")
        if any(not card.depan.strip() or not card.belakang.strip() for card in flashcards):
            raise ValueError("Ada kartu yang memiliki sisi depan atau belakang kosong.")

        return flashcards
    except Exception as parse_error:
        raise RuntimeError(f"Format flashcard dari model belum sesuai: {parse_error}. Silakan buat flashcard kembali.") from parse_error
