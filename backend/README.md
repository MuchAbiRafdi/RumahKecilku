# FastAPI backend

Jalankan dari repository root dengan `npm run dev:api` atau langsung:

```bash
backend/.venv/bin/python -m uvicorn app.main:app --app-dir backend --host 0.0.0.0 --port 8000 --reload
```

FastAPI menyediakan sesi akun demo, pencatatan aktivitas pengasuh dan pengumuman MessaCare, formulir KPSP berdasarkan usia, validasi umur dan skoring sesuai PDF, penyimpanan ke SQLite, serta status model perkembangan.

## Autentikasi demonstrasi

- Password disimpan sebagai hash scrypt. Token sesi mentah tidak disimpan di database; SQLite hanya menyimpan SHA-256 token.
- Cookie sesi HttpOnly dan SameSite=Lax berlaku 12 jam. Flag Secure diaktifkan untuk koneksi HTTPS, `X-Forwarded-Proto: https`, atau request dengan Origin HTTPS.
- Launcher pratinjau tertanam mengaktifkan token sesi cadangan selama 12 jam karena beberapa browser memblokir cookie pihak ketiga di dalam iframe. Token hanya disimpan pada tab (`sessionStorage`, dengan cadangan memori), dikirim melalui header Authorization, dan dinonaktifkan secara default jika API dijalankan langsung. Ini khusus versi uji dan tidak untuk data anak nyata.
- Formulir, jadwal, riwayat, dan penyimpanan KPSP dibatasi untuk peran dokter. `POST /api/activities` serta endpoint MessaCare dibatasi untuk pengasuh; aktivitas baru disimpan di SQLite dan pengumuman opsional disimpan bersama aktivitas. `GET /api/activities` dibatasi untuk pengasuh dan dokter, tanpa isolasi antar-anak/unit pada prototipe ini. Endpoint status model memerlukan sesi.
- `/api/auth/me` mengembalikan `{"user": null}` saat belum masuk supaya pemeriksaan sesi publik tidak menjadi error browser.
- Pendaftaran masih membolehkan pemohon memilih sendiri peran. Tidak ada verifikasi email/institusi atau relasi kepemilikan anak. Ini bukan autentikasi/RBAC produksi dan tidak boleh menerima data nyata.

**Pagar keselamatan:** model IRT pada `app/ml/bayesian_irt.py` sengaja dinonaktifkan dan gagal tertutup. Lampiran tidak menyediakan parameter butir, kalibrasi, atau validasi klinis; endpoint status menyatakan estimasi belum tersedia. KPSP adalah skrining, bukan diagnosis.
