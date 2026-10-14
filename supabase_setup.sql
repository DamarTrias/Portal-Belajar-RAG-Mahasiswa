-- Skema Portal Belajar RAG Mahasiswa.
-- Skrip ini dapat dijalankan ulang tanpa menghapus data yang sudah ada.
create extension if not exists vector;

create table if not exists students (
  id uuid primary key default gen_random_uuid(),
  name text not null,
  nim text not null unique,
  password_hash text
);

-- Migrasi untuk basis data yang tabel students-nya sudah dibuat sebelumnya.
alter table students add column if not exists password_hash text;

create table if not exists documents (
  id uuid primary key default gen_random_uuid(),
  student_id uuid not null references students(id) on delete cascade,
  name text not null,
  file_type text,
  created_at timestamptz default now()
);

create table if not exists chunks (
  id bigserial primary key,
  document_id uuid not null references documents(id) on delete cascade,
  student_id uuid not null references students(id) on delete cascade,
  content text not null,
  citation text not null,
  embedding vector(3072)
);

create or replace function match_chunks(
  query_embedding vector(3072),
  p_student_id uuid,
  p_document_id uuid default null,
  match_count int default 5
)
returns table (content text, citation text, similarity float)
language sql stable as $$
  select chunks.content, chunks.citation, 1 - (chunks.embedding <=> query_embedding)
  from chunks
  where chunks.student_id = p_student_id
    and (p_document_id is null or chunks.document_id = p_document_id)
  order by chunks.embedding <=> query_embedding
  limit greatest(match_count, 0);
$$;

-- Koneksi aplikasi di server menggunakan service key.
-- RLS diaktifkan, tetapi pembatasan pada jalur aplikasi diterapkan melalui filter student_id.
alter table students enable row level security;
alter table documents enable row level security;
alter table chunks enable row level security;
