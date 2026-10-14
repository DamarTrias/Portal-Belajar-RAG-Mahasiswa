"""
Inisialisasi klien model AI yang digunakan di seluruh aplikasi:
- embeddings : Google Gemini untuk mengubah teks menjadi vektor.
- llm        : Groq untuk penalaran dan tanya-jawab.
- vision_llm : Gemini Multimodal untuk membaca gambar/infografis.
"""
from typing import Any

from langchain_google_genai import ChatGoogleGenerativeAI, GoogleGenerativeAIEmbeddings
from langchain_groq import ChatGroq

from core.config import (
    GEMINI_API_KEY,
    GROQ_API_KEY,
    LLM_MODEL,
    VISION_MODEL,
    EMBEDDING_MODEL,
)

# Model embedding: mengubah teks menjadi vektor numerik untuk pencarian semantik.
embeddings = GoogleGenerativeAIEmbeddings(
    model=EMBEDDING_MODEL,
    google_api_key=GEMINI_API_KEY,
)

# Model bahasa utama: digunakan untuk menjawab pertanyaan dan membuat soal/flashcard.
llm = ChatGroq(
    model=LLM_MODEL,
    groq_api_key=GROQ_API_KEY,
    temperature=0.3,
)

# Model visual: digunakan untuk mentranskripsi gambar, diagram, dan infografis.
vision_llm = ChatGoogleGenerativeAI(
    model=VISION_MODEL,
    google_api_key=GEMINI_API_KEY,
    temperature=0.1,
)


def to_text(response: Any) -> str:
    """
    Mengambil teks bersih dari respons LLM.

    Model bisa mengembalikan respons berupa string biasa atau list blok pesan
    (misalnya saat menggunakan Gemini multimodal). Fungsi ini menangani keduanya.
    """
    if not response:
        return ""

    # Ambil atribut 'content' jika tersedia (standar LangChain response).
    content = response.content if hasattr(response, "content") else response

    if isinstance(content, str):
        return content.strip()

    # Tangani format list blok pesan (digunakan oleh beberapa model multimodal).
    if isinstance(content, list):
        text_parts = []
        for part in content:
            if isinstance(part, str):
                text_parts.append(part)
            elif isinstance(part, dict):
                text_parts.append(part.get("text", ""))
        return "".join(text_parts).strip()

    return str(content).strip()
