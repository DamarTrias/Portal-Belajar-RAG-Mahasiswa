"""Lapisan akses basis data Supabase, terisolasi per mahasiswa."""
from typing import List, Dict, Any

from supabase import create_client, Client

from core.config import SUPABASE_URL, SUPABASE_KEY

# Klien Supabase yang digunakan oleh seluruh modul aplikasi.
db: Client = create_client(SUPABASE_URL, SUPABASE_KEY)


def list_documents(student_id: str) -> List[Dict[str, Any]]:
    """
    Mengambil semua dokumen milik satu mahasiswa, diurutkan dari yang terbaru.
    Setiap dokumen menyertakan jumlah chunk (potongan teks) yang sudah diindeks.
    """
    response = (
        db.table("documents")
        .select("*, chunks(count)")
        .eq("student_id", student_id)
        .order("created_at", desc=True)
        .execute()
    )
    return response.data or []


def delete_document(student_id: str, doc_id: str) -> None:
    """
    Menghapus satu dokumen beserta seluruh chunk-nya secara permanen.
    Filter student_id memastikan mahasiswa hanya bisa menghapus dokumennya sendiri.
    """
    (
        db.table("documents")
        .delete()
        .eq("id", doc_id)
        .eq("student_id", student_id)
        .execute()
    )
