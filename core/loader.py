"""
Membaca dan mengekstrak teks dari berbagai format dokumen (PDF, PPTX, DOCX, Gambar).
Setiap fungsi mengembalikan list pasangan (teks, label_sitasi).
"""
import base64
import io
from typing import List, Tuple, Callable

import fitz  # PyMuPDF
from docx import Document
from pptx import Presentation
from langchain_core.messages import HumanMessage

from core.ai import vision_llm, to_text


def read_image(file_bytes: bytes, file_extension: str) -> List[Tuple[str, str]]:
    """
    Mentranskripsi konten visual (gambar, diagram, rumus) menggunakan Gemini Vision.
    Mengembalikan satu pasangan (teks_transkripsi, 'Gambar').
    """
    mime_type = "jpeg" if file_extension.lower() in ("jpg", "jpeg") else file_extension.lower()
    base64_image = base64.b64encode(file_bytes).decode("utf-8")

    prompt_message = HumanMessage(content=[
        {
            "type": "text",
            "text": (
                "Transkripsikan semua teks, judul, poin-poin, diagram, bagan, dan rumus pada gambar ini "
                "secara lengkap dan terstruktur dalam Bahasa Indonesia untuk keperluan materi kuliah RAG."
            ),
        },
        {
            "type": "image_url",
            "image_url": f"data:image/{mime_type};base64,{base64_image}",
        },
    ])

    transcription = to_text(vision_llm.invoke([prompt_message]))
    return [(transcription, "Gambar")]


def read_pdf(file_bytes: bytes, file_extension: str) -> List[Tuple[str, str]]:
    """
    Membaca PDF halaman per halaman.
    Halaman yang minim teks digital (< 100 karakter) diproses ulang menggunakan
    OCR berbasis Vision untuk menangkap diagram dan infografis.
    """
    pdf_document = fitz.open(stream=file_bytes, filetype="pdf")
    results: List[Tuple[str, str]] = []

    for page_num, page in enumerate(pdf_document, 1):
        page_text = (page.get_text() or "").strip()
        is_visual_page = len(page_text) < 100

        if is_visual_page:
            try:
                # Render halaman ke PNG berkualitas tinggi untuk OCR yang presisi.
                pixmap = page.get_pixmap(dpi=130)
                image_bytes = pixmap.tobytes("png")
                ocr_text, _ignored_citation = read_image(image_bytes, "png")[0]

                # Gabungkan teks judul (jika ada) dengan hasil transkripsi visual.
                if page_text and ocr_text:
                    page_text = f"{page_text}\n\n[Transkripsi Visual & Infografis]:\n{ocr_text}"
                elif ocr_text:
                    page_text = ocr_text

            except Exception as error:
                print(f"[Warning] OCR gagal pada PDF Halaman {page_num}: {error}")

        if page_text:
            results.append((page_text, f"Hal {page_num}"))

    pdf_document.close()
    return results


def read_pptx(file_bytes: bytes, file_extension: str) -> List[Tuple[str, str]]:
    """
    Membaca presentasi PowerPoint slide per slide.
    Mengekstrak judul, kotak teks, tabel, dan catatan presenter.
    """
    presentation = Presentation(io.BytesIO(file_bytes))
    results: List[Tuple[str, str]] = []

    for slide_num, slide in enumerate(presentation.slides, 1):
        slide_parts = []

        # Tambahkan judul slide jika tersedia.
        if slide.shapes.title and slide.shapes.title.text:
            slide_parts.append(f"Judul: {slide.shapes.title.text.strip()}")

        # Kumpulkan teks dari setiap shape (kotak teks dan tabel).
        for shape in slide.shapes:
            if shape == slide.shapes.title:
                continue  # Judul sudah ditangani di atas.

            if shape.has_text_frame and shape.text_frame:
                text = shape.text_frame.text.strip()
                if text:
                    slide_parts.append(text)

            elif shape.has_table:
                for row in shape.table.rows:
                    row_text = " | ".join(cell.text.strip() for cell in row.cells if cell.text.strip())
                    if row_text:
                        slide_parts.append(row_text)

        # Tambahkan catatan presenter jika ada.
        if slide.has_notes_slide and slide.notes_slide.notes_text_frame:
            notes = slide.notes_slide.notes_text_frame.text.strip()
            if notes:
                slide_parts.append(f"[Catatan: {notes}]")

        full_text = "\n".join(slide_parts).strip()
        if full_text:
            results.append((full_text, f"Slide {slide_num}"))

    return results


def read_docx(file_bytes: bytes, file_extension: str) -> List[Tuple[str, str]]:
    """
    Membaca dokumen Word (.docx).
    Paragraf dikelompokkan per 12 paragraf sebagai satu bagian logis.
    Tabel diekstrak secara terpisah.
    """
    docx_document = Document(io.BytesIO(file_bytes))
    paragraphs = [paragraph.text.strip() for paragraph in docx_document.paragraphs if paragraph.text.strip()]
    results: List[Tuple[str, str]] = []

    # Kelompokkan paragraf menjadi bagian-bagian berukuran tetap.
    batch_size = 12
    for batch_start in range(0, len(paragraphs), batch_size):
        section_num = batch_start // batch_size + 1
        section_text = "\n".join(paragraphs[batch_start:batch_start + batch_size]).strip()
        if section_text:
            results.append((section_text, f"Bagian {section_num}"))

    # Ekstrak isi tabel secara terpisah.
    for table_num, table in enumerate(docx_document.tables, 1):
        table_rows = []
        for row in table.rows:
            row_text = " | ".join(cell.text.strip() for cell in row.cells if cell.text.strip())
            if row_text:
                table_rows.append(row_text)
        if table_rows:
            results.append(("\n".join(table_rows), f"Tabel {table_num}"))

    return results


# Peta ekstensi file ke fungsi pembaca yang sesuai.
READERS: dict[str, Callable] = {
    "pdf": read_pdf,
    "pptx": read_pptx,
    "docx": read_docx,
    "png": read_image,
    "jpg": read_image,
    "jpeg": read_image,
}


def load_file(filename: str, file_bytes: bytes) -> Tuple[List[Tuple[str, str]], str]:
    """
    Mendeteksi format file dan mengekstrak seluruh teks beserta label sitasi.
    Mengembalikan (list_halaman, ekstensi_file).
    Memunculkan ValueError jika format tidak didukung.
    """
    file_extension = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""

    if file_extension not in READERS:
        supported_formats = ", ".join(f".{extension_name}" for extension_name in READERS)
        raise ValueError(f"Format .{file_extension} tidak didukung. Format yang didukung: {supported_formats}")

    extracted_pages = READERS[file_extension](file_bytes, file_extension)
    return extracted_pages, file_extension
