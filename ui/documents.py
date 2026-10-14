"""Tampilan tab manajemen dokumen materi kuliah (Upload & Hapus, terisolasi per mahasiswa)."""
from typing import Any, Dict

import streamlit as st

from core.db import delete_document, list_documents
from core.rag import ingest


def render(student: Dict[str, Any]) -> None:
    """
    Merender tab unggah materi kuliah dan daftar dokumen aktif.
    Setiap aksi (upload/hapus) terisolasi berdasarkan student_id.
    """
    col_upload, col_list = st.columns([1.1, 1.9])

    with col_upload:
        st.subheader("Unggah Materi Kuliah")
        st.caption("Format: PDF, PPTX, DOCX, PNG, JPG, dan JPEG. Gambar yang tertanam di dalam DOCX/PPTX belum diekstrak sebagai gambar terpisah.")

        uploaded_files = st.file_uploader(
            "Pilih file materi:",
            accept_multiple_files=True,
            type=["pdf", "pptx", "docx", "png", "jpg", "jpeg"],
            key=f"uploader_{student['id']}"
        )

        if st.button("🚀 Proses Dokumen", type="primary", key=f"btn_process_{student['id']}") and uploaded_files:
            for uploaded_file in uploaded_files:
                with st.spinner(f"Memproses & menganalisis {uploaded_file.name}..."):
                    try:
                        chunk_count = ingest(student["id"], uploaded_file.name, uploaded_file.read())
                        st.success(f"✅ {uploaded_file.name}: {chunk_count} chunk berhasil diekstrak dan disimpan.")
                    except Exception as error:
                        st.error(f"❌ {uploaded_file.name}: {error}")
            st.rerun()

    with col_list:
        st.subheader("Daftar Dokumen Anda")
        st.caption(f"Milik: {student['name']}")

        documents = list_documents(student["id"])
        if not documents:
            st.info("Belum ada dokumen yang diunggah untuk akun mahasiswa ini.")
            return

        for document in documents:
            col_format, col_name, col_chunk, col_delete = st.columns([1, 4, 2, 1])

            with col_format:
                st.code(document.get("file_type", "FILE").upper())
            with col_name:
                st.write(f"**{document['name']}**")
            with col_chunk:
                # Ambil jumlah chunk dari nested field yang dikembalikan Supabase.
                chunk_count = document.get("chunks", [{}])[0].get("count", 0) if document.get("chunks") else 0
                st.caption(f"{chunk_count} chunk")
            with col_delete:
                if st.button("🗑️ Hapus", key=f"del_{document['id']}", help="Hapus dokumen ini"):
                    delete_document(student["id"], document["id"])
                    st.success(f"Dokumen {document['name']} berhasil dihapus.")
                    st.rerun()

            st.markdown("<hr style='margin: 8px 0; border: 0; border-top: 1px solid rgba(255,255,255,0.08);'>", unsafe_allow_html=True)
