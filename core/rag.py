"""Alur RAG: Ingest dokumen, retrieve konteks, dan generate jawaban bersitasi."""
import re
from typing import Any, Dict, List, Optional, Sequence, Tuple

from langchain_text_splitters import RecursiveCharacterTextSplitter

from core.ai import embeddings, llm, to_text
from core.db import db
from core.loader import load_file

# Potong dokumen jadi chunk ~800 karakter dengan overlap 120 karakter
splitter = RecursiveCharacterTextSplitter(chunk_size=800, chunk_overlap=120)


# --- Fungsi Pembantu (Helper) ---

def _format_context(chunks: List[Dict[str, Any]]) -> str:
    # Format chunk materi menjadi teks bernomor rujukan [1], [2], dst.
    return "\n\n".join(
        f"[{i}] ({c['citation']})\n{c['content']}" 
        for i, c in enumerate(chunks, 1)
    )


def _format_history(history: Optional[Sequence[Dict[str, str]]], max_turns: int = 3) -> str:
    # Ambil maksimal 3 pasang tanya-jawab terakhir sebagai konteks percakapan
    if not history:
        return ""
    recent = history[-(max_turns * 2):]
    lines = [
        f"{'Mahasiswa' if m.get('role') == 'user' else 'Asisten'}: {m.get('text', '').strip()}"
        for m in recent if m.get('text', '').strip()
    ]
    return "RIWAYAT PERCAKAPAN TERAKHIR:\n" + "\n".join(lines) + "\n\n" if lines else ""


def _clean_invalid_citations(text: str, max_ref: int) -> str:
    # Hapus nomor sitasi di luar rentang sumber (misal: [6] padahal cuma ada 3 sumber)
    def _keep_valid(match: re.Match) -> str:
        num = int(match.group(1))
        return match.group(0) if 1 <= num <= max_ref else ""

    return re.sub(r"\[(\d+)\]", _keep_valid, text).strip()


def _extract_cited_numbers(text: str, max_ref: int) -> List[int]:
    # Ambil daftar nomor rujukan yang benar-benar ada di dalam jawaban
    return sorted({
        int(n) for n in re.findall(r"\[(\d+)\]", text)
        if n.isdigit() and 1 <= int(n) <= max_ref
    })


def _build_source_checklist(chunks: List[Dict[str, Any]], cited: List[int]) -> List[str]:
    # Tandai ✅ untuk sumber yang dikutip, atau — untuk sumber pelengkap
    return [
        f"{'✅' if i in cited else '—'} [{i}] {c['citation']}"
        for i, c in enumerate(chunks, 1)
    ]


# --- 1. Ingest (Simpan Dokumen ke Database Vektor) ---

def ingest(student_id: str, filename: str, data: bytes) -> int:
    # 1. Ekstrak teks dari file
    pages, file_ext = load_file(filename, data)

    # 2. Pecah teks menjadi chunk dan buat label sitasinya
    texts, citations = [], []
    for page_text, page_label in pages:
        for chunk in splitter.split_text(page_text):
            if chunk.strip():
                texts.append(chunk.strip())
                citations.append(f"{filename} ({page_label})")

    if not texts:
        raise ValueError("Tidak ada teks atau gambar materi yang dapat dibaca dari file ini.")

    # 3. Buat vektor embedding untuk tiap chunk
    vectors = embeddings.embed_documents(texts)

    # 4. Simpan metadata dokumen ke tabel 'documents'
    doc_res = db.table("documents").insert({
        "student_id": student_id,
        "name": filename,
        "file_type": file_ext,
    }).execute()

    if not doc_res.data:
        raise RuntimeError("Gagal menyimpan dokumen ke database.")

    doc_id = doc_res.data[0]["id"]

    # 5. Simpan chunk dan vektor embedding ke tabel 'chunks' (per batch 50 baris)
    chunk_rows = [
        {
            "document_id": doc_id,
            "student_id": student_id,
            "content": text,
            "citation": citation,
            "embedding": vector,
        }
        for text, citation, vector in zip(texts, citations, vectors)
    ]

    for start in range(0, len(chunk_rows), 50):
        db.table("chunks").insert(chunk_rows[start:start + 50]).execute()

    return len(chunk_rows)


# --- 2. Retrieve (Pencarian Vektor Relevan) ---

def retrieve(
    student_id: str,
    question: str,
    doc_id: Optional[str] = None,
    top_k: int = 5,
) -> List[Dict[str, Any]]:
    if not question.strip():
        return []

    # Ubah pertanyaan jadi vektor lalu cari chunk terdekat via match_chunks di Supabase
    query_vector = embeddings.embed_query(question)
    rpc_params = {
        "query_embedding": query_vector,
        "p_student_id": student_id,
        "p_document_id": doc_id,
        "match_count": top_k,
    }
    response = db.rpc("match_chunks", rpc_params).execute()
    return response.data or []


# --- 3. Answer (Jawab Pertanyaan dengan Sitasi) ---

def answer(
    student_id: str,
    question: str,
    doc_id: Optional[str] = None,
    history: Optional[Sequence[Dict[str, str]]] = None,
) -> Tuple[str, List[str]]:
    # 1. Cari 5 potongan materi paling relevan
    chunks = retrieve(student_id, question, doc_id=doc_id, top_k=5)
    if not chunks:
        return "Materi terkait tidak ditemukan dalam dokumen Anda. Pastikan sudah mengunggah materi yang sesuai.", []

    total_sources = len(chunks)

    # 2. Siapkan konteks rujukan dan riwayat percakapan
    context_text = _format_context(chunks)
    history_text = _format_history(history, max_turns=3)

    # 3. Susun prompt untuk LLM
    prompt = (
        "Anda adalah asisten akademik. Jawab dengan bahasa Indonesia yang jelas dan hanya berdasarkan konteks di bawah.\n"
        f"Cantumkan nomor rujukan [1] sampai [{total_sources}] pada klaim yang didukung oleh konteks.\n"
        "PENTING: Hanya gunakan nomor rujukan yang benar-benar ada di daftar konteks. "
        "Jangan mencantumkan nomor yang tidak digunakan atau di luar rentang.\n"
        "Jika informasi tidak ditemukan dalam konteks, nyatakan bahwa materi belum memuat informasi tersebut.\n\n"
        f"{history_text}"
        f"KONTEKS MATERI:\n{context_text}\n\n"
        f"PERTANYAAN: {question}\n\n"
        "JAWABAN:"
    )

    # 4. Dapatkan jawaban dari LLM
    raw_answer = to_text(llm.invoke(prompt)).strip()

    # 5. Bersihkan nomor sitasi yang tidak valid dan buat daftar rujukan
    clean_answer = _clean_invalid_citations(raw_answer, max_ref=total_sources)
    used_citations = _extract_cited_numbers(clean_answer, max_ref=total_sources)
    source_list = _build_source_checklist(chunks, used_citations)

    # Catatan jika tidak ada sitasi yang tercantum
    if not used_citations:
        clean_answer += "\n\nCatatan: jawaban tidak memuat nomor sitasi yang dapat dicocokkan dengan potongan materi yang ditemukan."

    return clean_answer, source_list
