"""Pembuatan soal latihan dan flashcard dari materi mahasiswa."""
import json
import re
from typing import Any, Dict, List, Optional, Tuple

from pydantic import BaseModel, Field

from core.ai import llm, to_text
from core.db import db
from core.rag import retrieve

# Batas maksimal chunk sampel dan ukuran halaman pagination database
CHUNK_SAMPLE_LIMIT = 15
DB_PAGE_SIZE = 500


# --- Model Data Pydantic ---

class Soal(BaseModel):
    pertanyaan: str = Field(min_length=1)
    pilihan: List[str] = Field(default_factory=list)
    jawaban: str = Field(min_length=1)
    pembahasan: str = Field(min_length=1)
    sumber: str = Field(min_length=1)


class Kuis(BaseModel):
    soal: List[Soal] = Field(min_length=1)


class Kartu(BaseModel):
    depan: str = Field(min_length=1)
    belakang: str = Field(min_length=1)


class SetKartu(BaseModel):
    kartu: List[Kartu] = Field(min_length=1)


# --- Fungsi Pembantu (Helper) ---

def extract_json_from_text(text: str) -> dict:
    # Bersihkan markdown ```json dan ambil objek JSON pertama
    cleaned = re.sub(r"^```(?:json)?\s*", "", text.strip(), flags=re.MULTILINE)
    cleaned = re.sub(r"\s*```$", "", cleaned, flags=re.MULTILINE)
    match = re.search(r"\{.*\}", cleaned, re.DOTALL)
    if match:
        cleaned = match.group(0)
    return json.loads(cleaned)


def _fetch_student_chunks(student_id: str, doc_id: Optional[str]) -> List[Dict[str, Any]]:
    # Ambil semua chunk milik mahasiswa dari database dengan pagination
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

        if len(page_data) < DB_PAGE_SIZE:
            break
        page_start += DB_PAGE_SIZE

    return all_chunks


def select_spread_rows(rows: List[Dict[str, Any]], limit: int = CHUNK_SAMPLE_LIMIT) -> List[Dict[str, Any]]:
    # Pilih sampel chunk yang tersebar merata dari awal hingga akhir dokumen
    if limit <= 0 or not rows:
        return []
    if len(rows) <= limit:
        return rows
    if limit == 1:
        return [rows[len(rows) // 2]]

    indexes = [round(pos * (len(rows) - 1) / (limit - 1)) for pos in range(limit)]
    return [rows[idx] for idx in indexes]


def get_context_selection(
    student_id: str,
    doc_id: Optional[str] = None,
    limit: int = CHUNK_SAMPLE_LIMIT,
    query: Optional[str] = None,
) -> Tuple[str, int, int]:
    # Ambil chunk relevan via semantic retrieval atau spread sampling
    all_chunks = _fetch_student_chunks(student_id, doc_id)
    if not all_chunks:
        raise ValueError("Belum ada materi untuk akun atau dokumen ini. Silakan unggah materi terlebih dahulu.")

    if query and query.strip():
        # Retrieval semantik berdasarkan query
        retrieved = retrieve(student_id, query, doc_id=doc_id, top_k=min(limit, len(all_chunks)))
        retrieved_contents = {c['content'] for c in retrieved}
        selected_chunks = [c for c in all_chunks if c['content'] in retrieved_contents]

        # Lengkapi sisa kuota dengan spread sampling
        if len(selected_chunks) < limit:
            remaining = [c for c in all_chunks if c['content'] not in retrieved_contents]
            selected_chunks.extend(select_spread_rows(remaining, limit - len(selected_chunks)))
    else:
        # Spread sampling merata dari seluruh dokumen
        selected_chunks = select_spread_rows(all_chunks, limit)

    context_text = "\n\n".join(f"({c['citation']})\n{c['content']}" for c in selected_chunks)
    return context_text, len(selected_chunks), len(all_chunks)


def get_context(
    student_id: str,
    doc_id: Optional[str] = None,
    limit: int = CHUNK_SAMPLE_LIMIT,
    query: Optional[str] = None,
) -> str:
    # Ambil teks konteks saja
    context_text, _, _ = get_context_selection(student_id, doc_id, limit, query=query)
    return context_text


def _validate_quiz(quiz: Kuis, expected_count: int, question_type: str) -> List[Soal]:
    # Validasi jumlah soal, opsi A-D, dan format jawaban
    if len(quiz.soal) != expected_count:
        raise ValueError(f"Model menghasilkan {len(quiz.soal)} soal, diminta {expected_count}.")

    for num, soal in enumerate(quiz.soal, 1):
        if not all(field.strip() for field in [soal.pertanyaan, soal.jawaban, soal.pembahasan, soal.sumber]):
            raise ValueError(f"Soal nomor {num} memiliki bagian kosong.")

        if question_type == "Pilihan Ganda":
            if len(soal.pilihan) != 4:
                raise ValueError(f"Soal pilihan ganda nomor {num} harus memiliki 4 opsi.")

            # Periksa dan normalisasi label A, B, C, D
            labels = []
            for opt in soal.pilihan:
                match = re.match(r"^\s*([A-D])[.)]\s*\S", opt)
                if not match:
                    raise ValueError(f"Opsi soal nomor {num} harus menggunakan label A-D.")
                labels.append(match.group(1))

            if sorted(labels) != ["A", "B", "C", "D"]:
                raise ValueError(f"Label opsi nomor {num} harus lengkap A, B, C, D tanpa duplikasi.")

            ans_match = re.match(r"^\s*([A-D])(?:[.)]\s*.*)?$", soal.jawaban, flags=re.DOTALL)
            if not ans_match:
                raise ValueError(f"Kunci jawaban nomor {num} harus berupa huruf A, B, C, atau D.")
            soal.jawaban = ans_match.group(1)

        elif soal.pilihan:
            raise ValueError(f"Soal esai nomor {num} tidak boleh memiliki opsi pilihan ganda.")

    return quiz.soal


# --- Fungsi Generasi Kuis & Flashcard ---

def make_quiz(
    student_id: str,
    doc_id: Optional[str],
    question_count: int,
    difficulty: str,
    question_type: str,
) -> Tuple[List[Soal], int, int]:
    # 1. Ambil konteks materi yang merata
    context, selected_count, total_count = get_context_selection(student_id, doc_id)

    if question_type == "Pilihan Ganda":
        aturan = "pilihan ganda dengan 4 opsi berlabel A, B, C, D"
        format_contoh = '{"pertanyaan":"...","pilihan":["A. ...","B. ...","C. ...","D. ..."],"jawaban":"A","pembahasan":"...","sumber":"nama berkas (Hal/Slide ...)"}'
    else:
        aturan = "esai; pilihan harus berupa daftar kosong [] dan jawaban berisi jawaban ideal"
        format_contoh = '{"pertanyaan":"...","pilihan":[],"jawaban":"...","pembahasan":"...","sumber":"nama berkas (Hal/Slide ...)"}'

    # 2. Susun prompt untuk LLM
    prompt = (
        f"Buat tepat {question_count} soal {aturan} tingkat kesulitan {difficulty}. Gunakan hanya informasi dari konteks. "
        "Untuk pilihan ganda, isi kolom jawaban hanya huruf A, B, C, atau D. Cantumkan sumber berdasarkan label materi.\n\n"
        f"KONTEKS MATERI ({selected_count} dari {total_count} potongan):\n{context}\n\n"
        "Kembalikan hanya JSON valid:\n"
        f'{{"soal":[{format_contoh}]}}'
    )

    # 3. Panggil AI dan validasi output JSON
    raw_text = to_text(llm.invoke(prompt))
    try:
        parsed = extract_json_from_text(raw_text)
        quiz = Kuis.model_validate(parsed)
        return _validate_quiz(quiz, question_count, question_type), selected_count, total_count
    except Exception as error:
        raise RuntimeError(f"Format soal dari model belum sesuai: {error}. Silakan coba lagi.") from error


def make_flashcards(
    student_id: str,
    doc_id: Optional[str],
    card_count: int,
) -> Tuple[List[Kartu], int, int]:
    # 1. Ambil konteks materi yang merata
    context, selected_count, total_count = get_context_selection(student_id, doc_id)

    # 2. Susun prompt untuk pembuatan flashcard
    prompt = (
        f"Buat tepat {card_count} flashcard bahasa Indonesia dari konteks berikut. "
        "Sisi depan berisi pertanyaan/konsep utama, sisi belakang berisi penjelasan ringkas. "
        "Gunakan hanya info dari konteks dan kembalikan hanya JSON valid.\n\n"
        f"KONTEKS MATERI ({selected_count} dari {total_count} potongan):\n{context}\n\n"
        'Format: {"kartu":[{"depan":"Pertanyaan atau konsep","belakang":"Jawaban ringkas"}]}'
    )

    # 3. Panggil AI dan validasi output JSON
    raw_text = to_text(llm.invoke(prompt))
    try:
        parsed = extract_json_from_text(raw_text)
        cards = SetKartu.model_validate(parsed).kartu

        if len(cards) != card_count:
            raise ValueError(f"Model menghasilkan {len(cards)} kartu, diminta {card_count}.")
        if any(not c.depan.strip() or not c.belakang.strip() for c in cards):
            raise ValueError("Ada kartu yang memiliki bagian depan atau belakang kosong.")

        return cards, selected_count, total_count
    except Exception as error:
        raise RuntimeError(f"Format flashcard dari model belum sesuai: {error}. Silakan coba lagi.") from error


# --- Database Persistensi Flashcard (Supabase) ---

def save_flashcards(student_id: str, doc_id: Optional[str], cards: List[Kartu]) -> int:
    # Simpan flashcard ke tabel 'flashcards' di Supabase
    rows = [
        {"student_id": student_id, "document_id": doc_id, "front": c.depan, "back": c.belakang}
        for c in cards
    ]
    if not rows:
        return 0

    for start in range(0, len(rows), 50):
        db.table("flashcards").insert(rows[start:start + 50]).execute()

    return len(rows)


def load_flashcards(student_id: str, doc_id: Optional[str] = None) -> List[Kartu]:
    # Ambil flashcard tersimpan untuk mahasiswa (dan dokumen tertentu jika dipilih)
    query = db.table("flashcards").select("front, back").eq("student_id", student_id).order("created_at", desc=True)
    if doc_id:
        query = query.eq("document_id", doc_id)

    response = query.execute()
    return [Kartu(depan=r["front"], belakang=r["back"]) for r in (response.data or [])]


def delete_flashcards(student_id: str, doc_id: Optional[str] = None) -> None:
    # Hapus flashcard dari database
    query = db.table("flashcards").delete().eq("student_id", student_id)
    if doc_id:
        query = query.eq("document_id", doc_id)
    query.execute()

