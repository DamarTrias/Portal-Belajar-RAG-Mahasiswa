"""Tab Chatbot Akademik interaktif."""
from typing import Any, Dict

import streamlit as st

from core.rag import answer
from ui.common import pick_document


def render(student: Dict[str, Any]) -> None:
    # Tampilan obrolan chatbot akademik dengan isolasi riwayat per mahasiswa
    col_sidebar, col_chat = st.columns([1, 2.5])
    chat_history_key = f"chat_{student['id']}"
    chat_history = st.session_state.setdefault(chat_history_key, [])

    # Sidebar: Pilih fokus dokumen dan tombol reset percakapan
    with col_sidebar:
        st.subheader("Fokus Sumber RAG")
        doc_id = pick_document(student["id"], label="Pilih Dokumen Acuan:", key=f"chat_doc_{student['id']}")

        st.markdown("""
        <div style="background: rgba(255,255,255,0.03); border: 1px solid rgba(255,255,255,0.1); border-radius: 8px; padding: 12px; margin: 12px 0;">
            <small style="color: #94a3b8;"><strong>💡 Panduan Pertanyaan:</strong><br>
            • "Jelaskan konsep utama materi..."<br>
            • "Apa hubungan konsep pada slide ini dengan materi sebelumnya?"<br>
            • "Sebutkan kelebihan dan kekurangan..."</small>
        </div>
        """, unsafe_allow_html=True)

        if st.button("🗑️ Bersihkan Percakapan", use_container_width=True, key=f"chat_clear_{student['id']}"):
            st.session_state[chat_history_key] = []
            st.rerun()

    # Kolom Utama: Tampilan riwayat chat dan form input pesan
    with col_chat:
        st.subheader("Ruang Tanya Jawab Akademik")

        if not chat_history:
            st.info(f"Halo {student['name']}! Silakan ajukan pertanyaan seputar materi kuliah Anda di bawah.")

        # Tampilkan daftar pesan riwayat percakapan
        for message in chat_history:
            avatar = "👨‍🎓" if message["role"] == "user" else "🎓"
            with st.chat_message(message["role"], avatar=avatar):
                st.markdown(message["text"])
                if message.get("sumber"):
                    with st.expander("📚 Sumber Materi (✅ = dirujuk dalam jawaban)"):
                        for source in message["sumber"]:
                            st.caption(f"• {source}")

        # Input pesan baru dari pengguna
        if user_prompt := st.chat_input("Tanyakan apa saja seputar materi kuliah Anda..."):
            chat_history.append({"role": "user", "text": user_prompt})

            with st.spinner("Mencari konteks rujukan & merumuskan jawaban..."):
                try:
                    bot_answer, sources = answer(student["id"], user_prompt, doc_id, history=chat_history)
                except Exception as error:
                    bot_answer = f"⚠️ Terjadi kesalahan saat memproses jawaban: {error}"
                    sources = []

            chat_history.append({"role": "assistant", "text": bot_answer, "sumber": sources})
            st.rerun()

