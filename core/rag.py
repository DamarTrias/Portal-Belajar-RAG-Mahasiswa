"""Alur RAG: pemrosesan materi, pencarian konteks semantik, dan jawaban bersitasi."""
import re
from typing import Any, Dict, List, Optional, Tuple

from langchain_text_splitters import RecursiveCharacterTextSplitter

from core.ai import embeddings, llm, to_text
from core.db import db
from core.loader import load_file

# Pembagi teks: memotong dokumen menjadi chunk ~800 karakter dengan tumpang-tindih 120 karakter.
splitter = RecursiveCharacterTextSplitter(chunk_size=800, chunk_overlap=120)


def ingest(student_id: str, filename: str, data: bytes) -> int:
    """
    Membaca berkas, memecahnya menjadi chunk, membuat vektor embedding,
    lalu menyimpan metadata dokumen dan chunk ke Supabase.
    Mengembalikan jumlah chunk yang berhasil disimpan.
    """
    pages, file_extension = load_file(filename, data)

    # Pecah setiap halaman/slide menjadi chunk dan buat label sitasinya.
    texts: List[str] = []
    citations: List[str] = []
    for page_text, page_label in pages:
        for chunk in splitter.split_text(page_text):
            cleaned_chunk = chunk.strip()
            if cleaned_chunk:
                texts.append(cleaned_chunk)
                citations.append(f"{filename} ({page_label})")

    if not texts:
        raise ValueError("Tidak ada teks atau gambar materi yang dapat dibaca dari file ini.")

    # Buat vektor embedding untuk semua chunk sekaligus (satu API call).
    vectors = embeddings.embed_documents(texts)

    # Simpan metadata dokumen terlebih dahulu untuk mendapatkan doc_id.
    doc_response = db.table("documents").insert({
        "student_id": student_id,
        "name": filename,
        "file_type": file_extension,
    }).execute()

    if not doc_response.data:
        raise RuntimeError("Gagal menyimpan metadata dokumen ke Supabase.")

    doc_id = doc_response.data[0]["id"]

    # Susun baris yang akan dimasukkan ke tabel chunks.
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

    # Masukkan chunk dalam batch 50 baris untuk menghindari batas ukuran request.
    batch_size = 50
    for batch_start in range(0, len(chunk_rows), batch_size):
        db.table("chunks").insert(chunk_rows[batch_start:batch_start + batch_size]).execute()

    return len(chunk_rows)


def retrieve(student_id: str, question: str, doc_id: Optional[str] = None, top_k: int = 5) -> List[Dict[str, Any]]:
    """
    Mengambil maksimal top_k chunk yang paling relevan secara semantik terhadap pertanyaan.
    Pencarian menggunakan fungsi RPC `match_chunks` yang mengurutkan berdasarkan cosine distance.
    Filter student_id dan doc_id memastikan isolasi data per mahasiswa.
    """
    if not question.strip():
        return []

    query_vector = embeddings.embed_query(question)
    rpc_params = {
        "query_embedding": query_vector,
        "p_student_id": student_id,
        "p_document_id": doc_id,
        "match_count": top_k,
    }
    response = db.rpc("match_chunks", rpc_params).execute()
    return response.data or []


def answer(student_id: str, question: str, doc_id: Optional[str] = None) -> Tuple[str, List[str]]:
    """
    Menjawab pertanyaan berdasarkan 5 chunk teratas dari retrieval.
    Mengembalikan tuple (teks_jawaban, list_sitasi_yang_digunakan).
    Model diminta mencantumkan nomor rujukan [1]-[5] pada klaim yang didukung konteks.
    """
    retrieved_chunks = retrieve(student_id, question, doc_id=doc_id, top_k=5)

    if not retrieved_chunks:
        return (
            "Materi terkait tidak ditemukan dalam dokumen Anda. Pastikan Anda telah mengunggah materi yang sesuai.",
            [],
        )

    # Susun konteks dengan nomor rujukan agar model bisa mengutip sumber secara spesifik.
    context = "\n\n".join(
        f"[{ref_num}] ({chunk['citation']})\n{chunk['content']}"
        for ref_num, chunk in enumerate(retrieved_chunks, 1)
    )

    prompt = (
        "Anda adalah asisten akademik. Jawab dengan bahasa Indonesia yang jelas dan hanya berdasarkan konteks di bawah.\n"
        "Cantumkan nomor rujukan [1] sampai [5] pada klaim yang didukung oleh konteks. Jangan mencantumkan nomor yang tidak digunakan.\n"
        "Jika informasi tidak ditemukan dalam konteks, nyatakan bahwa materi belum memuat informasi tersebut.\n\n"
        f"KONTEKS MATERI:\n{context}\n\nPERTANYAAN: {question}\n\nJAWABAN:"
    )

    raw_answer = to_text(llm.invoke(prompt)).strip()

    # Ekstrak nomor rujukan yang benar-benar digunakan dalam jawaban.
    used_ref_numbers = sorted({
        int(citation_num)
        for citation_num in re.findall(r"\[(\d+)\]", raw_answer)
        if citation_num.isdigit() and 1 <= int(citation_num) <= len(retrieved_chunks)
    })
    source_list = [f"[{ref_number}] {retrieved_chunks[ref_number - 1]['citation']}" for ref_number in used_ref_numbers]

    if not source_list:
        raw_answer += (
            "\n\nCatatan: jawaban tidak memuat nomor sitasi yang dapat dicocokkan "
            "dengan potongan materi yang ditemukan."
        )

    return raw_answer, source_list
