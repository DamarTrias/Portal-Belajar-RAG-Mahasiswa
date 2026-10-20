"""Tab Generator Soal Latihan (Kuis Pilihan Ganda & Essay)."""
import re
from typing import Any, Dict

import streamlit as st

from core.generator import make_quiz
from ui.common import pick_document


def render(student: Dict[str, Any]) -> None:
    # Tampilan pembuat kuis otomatis dari dokumen materi
    col_config, col_quiz = st.columns([1, 2])
    quiz_state_key = f"quiz_{student['id']}"

    # Sidebar: Formulir konfigurasi pembuatan soal
    with col_config:
        st.subheader("Konfigurasi Pembuat Soal")
        doc_id = pick_document(student["id"], label="Pilih Dokumen Sumber:", key=f"quiz_doc_{student['id']}")
        st.caption("Soal dibuat dari maksimal 15 potongan materi yang dipilih secara merata. Jika dokumen memiliki lebih banyak potongan, tidak semua bagian digunakan.")
        question_count = st.selectbox("Jumlah Soal:", [3, 5, 10], index=1, key=f"quiz_qty_{student['id']}")
        difficulty = st.selectbox("Tingkat Kesulitan:", ["Mudah", "Sedang", "Sulit"], index=1, key=f"quiz_lvl_{student['id']}")
        question_type = st.selectbox("Tipe Soal:", ["Pilihan Ganda", "Essay"], key=f"quiz_type_{student['id']}")

        # Tombol generate soal kuis
        if st.button("✨ Buat Soal dari Dokumen", type="primary", use_container_width=True, key=f"quiz_btn_{student['id']}"):
            with st.spinner("Menganalisis materi & menyusun soal kuis cerdas..."):
                try:
                    soal_list, selected_count, total_count = make_quiz(
                        student_id=student["id"],
                        doc_id=doc_id,
                        question_count=question_count,
                        difficulty=difficulty,
                        question_type=question_type,
                    )
                    st.session_state[quiz_state_key] = {
                        "soal_list": soal_list,
                        "tipe": question_type,
                        "submitted": False,
                        "user_answers": {},
                        "selected_count": selected_count,
                        "total_count": total_count,
                    }
                    st.rerun()
                except Exception as error:
                    st.error(f"Gagal membuat soal: {error}")

    # Kolom Utama: Tampilan butir soal dan pembahasan
    with col_quiz:
        st.subheader("Latihan Soal Ujian")
        quiz_data = st.session_state.get(quiz_state_key)

        if not quiz_data or not quiz_data.get("soal_list"):
            st.info("Pilih konfigurasi di sebelah kiri dan klik 'Buat Soal dari Dokumen' untuk menghasilkan kuis.")
            return

        question_list = quiz_data["soal_list"]
        is_multiple_choice = (quiz_data["tipe"] == "Pilihan Ganda")

        # Indikator cakupan materi
        sel = quiz_data.get("selected_count", "?")
        tot = quiz_data.get("total_count", "?")
        st.caption(f"📊 Soal dibuat dari **{sel}** dari **{tot}** potongan materi yang tersedia.")

        # Form pengumpulan jawaban
        with st.form(f"quiz_form_{student['id']}"):
            user_answers = {}
            for num, item in enumerate(question_list, 1):
                st.markdown(f"**{num}. {item.pertanyaan}**")

                if is_multiple_choice and item.pilihan:
                    answer = st.radio(
                        f"Pilihan {num}",
                        options=item.pilihan,
                        index=None,
                        key=f"q_choice_{student['id']}_{num}",
                        label_visibility="collapsed"
                    )
                else:
                    answer = st.text_area(
                        "Jawaban Anda:",
                        key=f"q_essay_{student['id']}_{num}",
                        placeholder="Tuliskan analisis atau jawaban Anda di sini..."
                    )
                user_answers[num] = answer
                st.markdown("<hr style='margin: 12px 0; border: 0; border-top: 1px solid rgba(255,255,255,0.06);'>", unsafe_allow_html=True)

            if st.form_submit_button("✅ Kumpulkan & Periksa Jawaban", type="primary"):
                quiz_data["submitted"] = True
                quiz_data["user_answers"] = user_answers
                st.rerun()

        # Evaluasi nilai dan pembahasan setelah dikumpulkan
        if quiz_data.get("submitted"):
            st.markdown("### 📊 Hasil & Pembahasan")
            correct_count = 0

            for num, item in enumerate(question_list, 1):
                ans = quiz_data["user_answers"].get(num, "")

                if is_multiple_choice:
                    # Cek huruf kunci jawaban A-D
                    user_match = re.match(r"^\s*([A-D])\s*[.)]", ans or "", flags=re.IGNORECASE)
                    user_label = user_match.group(1).upper() if user_match else ""
                    correct_label = item.jawaban.strip().upper()[:1]
                    is_correct = bool(user_label and user_label == correct_label)

                    if is_correct:
                        correct_count += 1
                        st.success(f"**Nomor {num}: Benar! 🎉** (Jawaban Anda: {ans})")
                    else:
                        st.error(f"**Nomor {num}: Salah.** Jawaban Anda: {ans or 'Kosong'} | Kunci: **{correct_label}**")
                else:
                    st.markdown(f"**Soal {num}:**")
                    st.caption(f"Jawaban Anda: {ans or 'Kosong'}")
                    st.info(f"💡 **Model Jawaban Ideal:** {item.jawaban}")

                with st.expander(f"Lihat Pembahasan Lengkap No. {num}"):
                    st.write(item.pembahasan)
                    st.caption(f"📚 Rujukan: {item.sumber}")

            if is_multiple_choice:
                score = int((correct_count / len(question_list)) * 100)
                st.metric(label="Skor Kuis Anda", value=f"{score} / 100")

