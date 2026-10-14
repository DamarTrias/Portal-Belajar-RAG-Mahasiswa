"""Tampilan tab Generatif Soal (Kuis Pilihan Ganda & Essay)."""
import re
from typing import Any, Dict

import streamlit as st

from core.generator import make_quiz
from ui.common import pick_document


def render(student: Dict[str, Any]) -> None:
    """
    Merender tab generator soal latihan ujian otomatis dari materi mahasiswa.
    Hasil kuis disimpan di session_state hingga sesi aplikasi berakhir.
    """
    col_config, col_quiz = st.columns([1, 2])
    quiz_state_key = f"quiz_{student['id']}"

    with col_config:
        st.subheader("Konfigurasi Pembuat Soal")
        doc_id = pick_document(student["id"], label="Pilih Dokumen Sumber:", key=f"quiz_doc_{student['id']}")
        st.caption("Soal dibuat dari maksimal 15 potongan materi yang dipilih secara merata. Jika dokumen memiliki lebih banyak potongan, tidak semua bagian digunakan.")
        question_count = st.selectbox("Jumlah Soal:", [3, 5, 10], index=1, key=f"quiz_qty_{student['id']}")
        difficulty = st.selectbox("Tingkat Kesulitan:", ["Mudah", "Sedang", "Sulit"], index=1, key=f"quiz_lvl_{student['id']}")
        question_type = st.selectbox("Tipe Soal:", ["Pilihan Ganda", "Essay"], key=f"quiz_type_{student['id']}")

        if st.button("✨ Buat Soal dari Dokumen", type="primary", use_container_width=True, key=f"quiz_btn_{student['id']}"):
            with st.spinner("Menganalisis materi & menyusun soal kuis cerdas..."):
                try:
                    st.session_state[quiz_state_key] = {
                        "soal_list": make_quiz(
                            student_id=student["id"],
                            doc_id=doc_id,
                            question_count=question_count,
                            difficulty=difficulty,
                            question_type=question_type,
                        ),
                        "tipe": question_type,
                        "submitted": False,
                        "user_answers": {},
                    }
                    st.rerun()
                except Exception as error:
                    st.error(f"Gagal membuat soal: {error}")

    with col_quiz:
        st.subheader("Latihan Soal Ujian")
        quiz_data = st.session_state.get(quiz_state_key)

        if not quiz_data or not quiz_data.get("soal_list"):
            st.info("Pilih konfigurasi di sebelah kiri dan klik 'Buat Soal dari Dokumen' untuk menghasilkan kuis.")
            return

        question_list = quiz_data["soal_list"]
        is_multiple_choice = (quiz_data["tipe"] == "Pilihan Ganda")

        # Tampilkan soal dalam form agar bisa dikumpulkan sekaligus.
        with st.form(f"quiz_form_{student['id']}"):
            user_answers = {}
            for question_num, question_item in enumerate(question_list, 1):
                st.markdown(f"**{question_num}. {question_item.pertanyaan}**")

                if is_multiple_choice and question_item.pilihan:
                    answer = st.radio(
                        f"Pilihan {question_num}",
                        options=question_item.pilihan,
                        index=None,
                        key=f"q_choice_{student['id']}_{question_num}",
                        label_visibility="collapsed"
                    )
                else:
                    answer = st.text_area(
                        "Jawaban Anda:",
                        key=f"q_essay_{student['id']}_{question_num}",
                        placeholder="Tuliskan analisis atau jawaban Anda di sini..."
                    )
                user_answers[question_num] = answer

                st.markdown("<hr style='margin: 12px 0; border: 0; border-top: 1px solid rgba(255,255,255,0.06);'>", unsafe_allow_html=True)

            submit_button = st.form_submit_button("✅ Kumpulkan & Periksa Jawaban", type="primary")
            if submit_button:
                quiz_data["submitted"] = True
                quiz_data["user_answers"] = user_answers
                st.rerun()

        # Tampilkan pembahasan dan nilai setelah jawaban dikumpulkan.
        if quiz_data.get("submitted"):
            st.markdown("### 📊 Hasil & Pembahasan")
            correct_count = 0

            for question_num, question_item in enumerate(question_list, 1):
                user_answer = quiz_data["user_answers"].get(question_num, "")

                if is_multiple_choice:
                    # Bandingkan hanya huruf opsi (A-D), bukan teks lengkap pilihan.
                    user_label_match = re.match(r"^\s*([A-D])\s*[.)]", user_answer or "", flags=re.IGNORECASE)
                    user_label = user_label_match.group(1).upper() if user_label_match else ""
                    correct_label = question_item.jawaban.strip().upper()[:1]
                    is_correct = bool(user_label and user_label == correct_label)

                    if is_correct:
                        correct_count += 1
                        st.success(f"**Nomor {question_num}: Benar! 🎉** (Jawaban Anda: {user_answer})")
                    else:
                        st.error(f"**Nomor {question_num}: Salah.** Jawaban Anda: {user_answer or 'Kosong'} | Kunci: **{correct_label}**")
                else:
                    st.markdown(f"**Soal {question_num}:**")
                    st.caption(f"Jawaban Anda: {user_answer or 'Kosong'}")
                    st.info(f"💡 **Model Jawaban Ideal:** {question_item.jawaban}")

                with st.expander(f"Lihat Pembahasan Lengkap No. {question_num}"):
                    st.write(question_item.pembahasan)
                    st.caption(f"📚 Rujukan: {question_item.sumber}")

            # Tampilkan skor akhir hanya untuk kuis pilihan ganda.
            if is_multiple_choice:
                score = int((correct_count / len(question_list)) * 100)
                st.metric(label="Skor Kuis Anda", value=f"{score} / 100")
