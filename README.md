# Portal Belajar RAG Mahasiswa

Aplikasi pembelajaran berbasis dokumen menggunakan Python 3.11, Streamlit, LangChain, Google Gemini, Groq, dan Supabase PostgreSQL/pgvector.

## Menjalankan secara lokal

1. Buat virtual environment dengan Python 3.11.
2. Aktifkan environment, lalu instal dependensi:
   `pip install -r requirements.txt`
3. Salin `.env.example` menjadi `.env` dan isi nilai `SUPABASE_URL`, `SUPABASE_SERVICE_KEY`, `GEMINI_API_KEY`, serta `GROQ_API_KEY`. Model default tercantum pada `.env.example`.
4. Jalankan `supabase_setup.sql` di SQL Editor proyek Supabase. Skrip menambah kolom `password_hash` jika belum tersedia dan membuat ulang fungsi pencarian tanpa menghapus tabel/data yang sudah ada.
5. Jalankan aplikasi dengan `streamlit run app.py`.

## Catatan sistem

- Autentikasi dikelola oleh kode aplikasi melalui tabel `students`; sistem tidak memakai Supabase Auth.
- File asli tidak disimpan. Aplikasi menyimpan metadata dan teks hasil ekstraksi dalam bentuk potongan materi.
- Gambar yang tertanam di dalam DOCX/PPTX belum diekstrak secara terpisah. Gambar yang diunggah langsung dan halaman PDF minim teks dapat diproses dengan model visual.
- Chatbot mencari maksimal lima potongan materi. Percakapan sebelumnya hanya ditampilkan di antarmuka dan tidak dikirim sebagai konteks ke permintaan jawaban berikutnya.
- Generasi soal dan flashcard menggunakan maksimal 15 potongan yang tersebar merata berdasarkan urutan ID. Flashcard hanya tersimpan selama sesi aplikasi.
- Pemisahan data dilakukan menggunakan filter `student_id` pada kode aplikasi. RLS diaktifkan tanpa policy karena koneksi server menggunakan service key; service key melewati policy RLS. Karena itu, jangan menaruh service key di frontend dan jangan menganggap akses langsung ke database telah dipisahkan per mahasiswa oleh RLS.
- Layanan Gemini, Groq, dan Supabase harus tersedia agar fitur terkait dapat digunakan.

## Pengujian

Jalankan skenario Black Box Testing dan evaluasi RAG yang tercantum pada Bab II. Catat status aktual dan bukti setiap skenario setelah pengujian dilakukan. Hasil pengujian belum disertakan di repositori ini karena perlu dicatat berdasarkan pelaksanaan aplikasi yang nyata.

Uji unit offline untuk hash kata sandi, pemilihan sampel chunk, dan validasi kunci kuis dapat dijalankan dengan:
`python -m unittest discover -s tests`
