"""Tampilan tab Dashboard Utama (Ringkasan aktivitas, statistik materi, dan status sistem)."""
from typing import Any, Dict

import streamlit as st

from core.config import EMBEDDING_MODEL, LLM_MODEL, VISION_MODEL
from core.db import list_documents


def render(student: Dict[str, Any]) -> None:
    """Merender tab Dashboard Ringkasan Akademik per mahasiswa."""
    documents = list_documents(student["id"])
    total_documents = len(documents)

    # Hitung total chunk dari semua dokumen (data berasal dari nested field Supabase).
    total_chunks = sum(
        document.get("chunks", [{}])[0].get("count", 0) if document.get("chunks") else 0
        for document in documents
    )

    # Kumpulkan format file unik yang sudah diunggah.
    file_types = {
        document.get("file_type", "").lower().replace(".", "").upper()
        for document in documents
        if document.get("file_type")
    }

    # ==========================================
    # 1. KARTU METRIK STATISTIK UTAMA
    # ==========================================
    col_docs, col_chunks, col_account = st.columns(3)

    with col_docs:
        st.metric(
            label="📁 Total Dokumen",
            value=f"{total_documents} Berkas",
            delta=f"{len(file_types)} Format" if file_types else "Belum ada materi"
        )

    with col_chunks:
        st.metric(
            label="🧩 Potongan Teks (Chunks)",
            value=f"{total_chunks:,}",
            delta="Terindeks Vektor" if total_chunks > 0 else "0 Indeks"
        )

    with col_account:
        st.metric(
            label="🛡️ Filter Data",
            value="Akun Aktif",
            delta=f"NIM: {student['nim']}"
        )

    st.markdown("<div style='height: 12px;'></div>", unsafe_allow_html=True)

    # ==========================================
    # 2. STATUS MATERI TERBARU & PANDUAN KERJA
    # ==========================================
    col_left, col_right = st.columns([1.6, 1.4])

    with col_left:
        st.subheader("📚 Ringkasan Dokumen Materi Anda")
        if not documents:
            st.info(
                "💡 **Belum ada materi yang diunggah.**\n\n"
                "Silakan buka tab **'📁 Dokumen Kuliah'** untuk mengunggah berkas PDF, Word, PPTX, "
                "atau foto materi catatan kuliah pertama Anda."
            )
        else:
            st.caption(f"Menampilkan {min(5, total_documents)} dari {total_documents} dokumen terbaru:")
            for document in documents[:5]:
                chunk_count = document.get("chunks", [{}])[0].get("count", 0) if document.get("chunks") else 0
                file_badge = document.get("file_type", "FILE").upper().replace(".", "")
                upload_date = document.get("created_at", "")[:10] if document.get("created_at") else "-"

                st.markdown(f"""
                <div style="background: rgba(255, 255, 255, 0.03); border: 1px solid rgba(255, 255, 255, 0.08); border-radius: 8px; padding: 10px 14px; margin-bottom: 8px; display: flex; justify-content: space-between; align-items: center;">
                    <div>
                        <span style="background: #3b82f6; color: white; padding: 2px 6px; border-radius: 4px; font-size: 11px; font-weight: bold; margin-right: 8px;">{file_badge}</span>
                        <strong>{document['name']}</strong>
                        <div style="color: #94a3b8; font-size: 12px; margin-top: 2px;">Diupload: {upload_date}</div>
                    </div>
                    <div style="text-align: right;">
                        <span style="background: rgba(16, 185, 129, 0.15); color: #10b981; padding: 4px 8px; border-radius: 6px; font-size: 12px; font-weight: 600;">{chunk_count} chunks</span>
                    </div>
                </div>
                """, unsafe_allow_html=True)

    with col_right:
        st.subheader("⚡ Navigasi Fitur Cerdas")
        st.markdown("""
        <div style="display: grid; grid-template-columns: 1fr; gap: 8px;">
            <div style="background: rgba(255, 255, 255, 0.02); border-left: 4px solid #3b82f6; border-radius: 6px; padding: 10px 14px;">
                <strong>📁 1. Dokumen Kuliah</strong><br>
                <small style="color: #94a3b8;">Unggah materi kuliah. Gambar yang diunggah langsung dan halaman PDF minim teks dapat dibaca dengan bantuan model visual.</small>
            </div>
            <div style="background: rgba(255, 255, 255, 0.02); border-left: 4px solid #10b981; border-radius: 6px; padding: 10px 14px;">
                <strong>💬 2. Chatbot & Sitasi</strong><br>
                <small style="color: #94a3b8;">Ajukan pertanyaan berdasarkan materi yang ditemukan. Jawaban dapat menampilkan rujukan sumber yang digunakan.</small>
            </div>
            <div style="background: rgba(255, 255, 255, 0.02); border-left: 4px solid #f59e0b; border-radius: 6px; padding: 10px 14px;">
                <strong>📝 3. Generatif Soal (Kuis)</strong><br>
                <small style="color: #94a3b8;">Buat latihan soal ujian (Pilihan Ganda & Essay) otomatis dari materi lengkap dengan kunci jawaban.</small>
            </div>
            <div style="background: rgba(255, 255, 255, 0.02); border-left: 4px solid #8b5cf6; border-radius: 6px; padding: 10px 14px;">
                <strong>🃏 4. Flashcard Pintar</strong><br>
                <small style="color: #94a3b8;">Kuis kartu bolak-balik untuk melatih daya ingat konsep penting (*active recall*).</small>
            </div>
        </div>
        """, unsafe_allow_html=True)

    st.markdown("<div style='height: 16px;'></div>", unsafe_allow_html=True)

    # ==========================================
    # 3. SPESIFIKASI & ARSITEKTUR MESIN AI
    # ==========================================
    with st.expander("⚙️ Spesifikasi Mesin AI & Infrastruktur Sistem", expanded=False):
        col_spec1, col_spec2 = st.columns(2)
        with col_spec1:
            st.markdown(f"""
            * **Model Bahasa Utama (LLM):** `{LLM_MODEL}` (Groq Engine)
            * **Model Vektor Embedding:** `{EMBEDDING_MODEL}` (Gemini 3072-dim)
            * **Model Pemrosesan Visual:** `{VISION_MODEL}` (Gemini Multimodal)
            """)
        with col_spec2:
            st.markdown(f"""
            * **Penyimpanan Basis Data:** `Supabase PostgreSQL (Cloud)`
            * **Ekstensi Pencarian Vektor:** `pgvector (Cosine Distance)`
            * **Mekanisme Isolasi Data:** `Filter aplikasi berdasarkan student_id`
            """)
