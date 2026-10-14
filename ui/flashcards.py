"""Tampilan tab Flashcard Pintar untuk metode belajar active recall."""
from typing import Any, Dict

import streamlit as st

from core.generator import make_flashcards
from ui.common import pick_document


def render(student: Dict[str, Any]) -> None:
    """
    Merender antarmuka flashcard interaktif per mahasiswa.
    Status kartu (indeks aktif dan sisi yang terlihat) disimpan di session_state.
    """
    col_config, col_display = st.columns([1, 2])

    # Kunci session_state unik per mahasiswa.
    cards_key = f"cards_{student['id']}"
    current_index_key = f"card_idx_{student['id']}"
    is_flipped_key = f"card_flip_{student['id']}"

    # Inisialisasi state awal jika belum ada.
    if current_index_key not in st.session_state:
        st.session_state[current_index_key] = 0
    if is_flipped_key not in st.session_state:
        st.session_state[is_flipped_key] = False

    with col_config:
        st.subheader("Buat Flashcard")
        st.caption("Flashcard dibuat dari maksimal 15 potongan materi yang dipilih secara merata. Kartu hanya tersimpan selama sesi aplikasi.")

        doc_id = pick_document(student["id"], label="Pilih Dokumen Sumber:", key=f"cards_doc_{student['id']}")
        card_count = st.selectbox("Jumlah Kartu:", [5, 10, 15], key=f"cards_qty_{student['id']}")

        if st.button("✨ Buat Flashcard Baru", type="primary", use_container_width=True, key=f"cards_btn_{student['id']}"):
            with st.spinner("Mengekstrak konsep & membuat flashcard..."):
                try:
                    new_cards = make_flashcards(
                            student_id=student["id"],
                            doc_id=doc_id,
                            card_count=card_count,
                        )
                    st.session_state[cards_key] = new_cards
                    st.session_state[current_index_key] = 0
                    st.session_state[is_flipped_key] = False
                    st.rerun()
                except Exception as error:
                    st.error(f"Gagal membuat flashcard: {error}")

    with col_display:
        st.subheader("Flashcard Pintar")
        card_list = st.session_state.get(cards_key)

        if not card_list:
            st.info("Pilih dokumen dan klik 'Buat Flashcard Baru' untuk mulai belajar.")
            return

        # Pastikan indeks tidak melebihi panjang daftar kartu.
        current_index = st.session_state[current_index_key]
        if current_index >= len(card_list):
            current_index = 0
            st.session_state[current_index_key] = 0

        current_card = card_list[current_index]
        is_flipped = st.session_state[is_flipped_key]

        # Tentukan tampilan kartu berdasarkan sisi yang sedang dilihat.
        card_title = "💡 JAWABAN & PENJELASAN" if is_flipped else "❓ PERTANYAAN / KONSEP"
        card_content = current_card.belakang if is_flipped else current_card.depan
        card_border_color = "#10b981" if is_flipped else "#3b82f6"

        st.markdown(f"""
        <div style="background: rgba(255,255,255,0.03); border: 2px solid {card_border_color}; border-radius: 16px; padding: 36px 24px; min-height: 200px; text-align: center; margin: 16px 0;">
            <div style="font-size: 11px; font-weight: 800; color: {card_border_color}; letter-spacing: 0.08em; margin-bottom: 12px;">{card_title}</div>
            <div style="font-size: 18px; font-weight: 600; line-height: 1.5; color: #f8fafc;">{card_content}</div>
        </div>
        """, unsafe_allow_html=True)

        # Tombol navigasi: Sebelumnya | Balik Kartu | Berikutnya
        col_prev, col_flip, col_next = st.columns([1, 1.5, 1])

        with col_prev:
            if st.button("⬅️ Sebelumnya", use_container_width=True, disabled=(current_index == 0)):
                st.session_state[current_index_key] = max(0, current_index - 1)
                st.session_state[is_flipped_key] = False
                st.rerun()

        with col_flip:
            flip_label = "🔄 Balik ke Pertanyaan" if is_flipped else "🔄 Balik Lihat Jawaban"
            if st.button(flip_label, use_container_width=True, type="primary"):
                st.session_state[is_flipped_key] = not is_flipped
                st.rerun()

        with col_next:
            if st.button("Berikutnya ➡️", use_container_width=True, disabled=(current_index == len(card_list) - 1)):
                st.session_state[current_index_key] = min(len(card_list) - 1, current_index + 1)
                st.session_state[is_flipped_key] = False
                st.rerun()

        st.caption(f"<div style='text-align: center; margin-top: 10px;'>Kartu {current_index + 1} dari {len(card_list)}</div>", unsafe_allow_html=True)
