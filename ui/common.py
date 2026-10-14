"""Komponen antarmuka yang digunakan berulang pada berbagai tab."""
from typing import Optional

import streamlit as st

from core.db import list_documents


def pick_document(student_id: str, label: str = "Sumber Dokumen", key: Optional[str] = None) -> Optional[str]:
    """
    Menampilkan dropdown untuk memilih dokumen sebagai filter sumber RAG.
    Mengembalikan ID dokumen yang dipilih, atau None jika pengguna memilih 'Semua Dokumen'.
    """
    documents = list_documents(student_id)
    # Buat peta nama dokumen → ID agar mudah dicari setelah pengguna memilih.
    name_to_id = {document["name"]: document["id"] for document in documents}

    options = ["Semua Dokumen Saya"] + list(name_to_id.keys())
    selected_name = st.selectbox(label, options=options, key=key)

    # Jika nama yang dipilih tidak ada di peta, berarti "Semua Dokumen" terpilih → kembalikan None.
    return name_to_id.get(selected_name)
