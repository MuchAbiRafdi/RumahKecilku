# Audit login Rumah Kecilku — 15 Oktober 2026

## Temuan utama

Log sebelumnya menunjukkan pola: login API berhasil (`200`), lalu halaman ruang kerja memeriksa `/api/auth/me` dan kembali ke halaman masuk. Pada audit kode, ditemukan dua penyebab yang dapat membuat gejala itu terjadi:

1. **Respons pemeriksaan sesi yang terlambat bisa menghapus sesi baru.** Halaman masuk memanggil `/auth/me` saat pertama dibuka. Bila respons tanpa sesi itu datang setelah login berhasil, client sebelumnya menghapus token yang baru saja disimpan hanya karena respons berisi `user: null`. Tes regresi baru mereproduksi urutan ini dan memastikan token baru tetap utuh.
2. **Cookie dapat dibatasi di pratinjau yang tertanam.** Cookie tetap HttpOnly dan SameSite=Lax, tetapi browser bisa menolak atau tidak mengirim cookie dalam konteks iframe lintas-situs. Karena itu, versi pratinjau kini memiliki jalur sesi cadangan tanpa cookie.

## Perbaikan

- Respons `/auth/me` hanya boleh menghapus token bila permintaan itu memang memakai token yang sama dan token tersebut masih aktif. Respons dari pemeriksaan anonim yang dimulai sebelum login tidak dapat menghapus sesi yang baru dibuat.
- Login dan pendaftaran pratinjau menyimpan token sesi pada tab (`sessionStorage`, dengan cadangan memori bila penyimpanan browser dibatasi). Client mengirimkannya sebagai `Authorization: Bearer`.
- API menerima token tersebut untuk `/auth/me`, endpoint terlindungi, dan logout. Logout menghapus sesi di server serta token di browser.
- Token hanya dikirim ke client saat flag `RUMAH_BROWSER_SESSION_TOKEN=1` aktif. Flag ini dinyalakan oleh launcher pratinjau; default API tetap tidak mengembalikan token. Cookie HttpOnly tetap dipertahankan.
- Ditambahkan tes backend untuk login tanpa cookie pada ketiga peran dan tes client khusus untuk race pemeriksaan sesi.

## Perbaikan operasional pratinjau

Pada giliran audit berikutnya, tidak ada lagi proses yang mendengarkan port 3000/8000. `npm run dev` langsung gagal karena `node_modules` tidak tersedia (`concurrently: not found`); dependensi ini memang tidak ikut disimpan dalam snapshot workspace. Karena itu, preview sebelumnya dapat mati walau kode login sudah berubah.

Launcher `npm run dev` kini menjalankan `scripts/start-preview.sh`: ia memasang dependensi Node bila hilang, membuat ulang virtual environment Python bila perlu, lalu menjalankan frontend dan API. Skrip tes backend juga membuat ulang dependensi tes bila lingkungan belum ada.

## Verifikasi

- `npm run build` — berhasil.
- `npm run test:client` — 1 tes lulus.
- `npm run test:api` — 25 tes lulus. Ada satu peringatan deprecation dari `starlette.testclient`/`httpx`; tidak ada tes yang gagal.
- Browser Chromium nyata: ketiga akun demo berhasil membuka ruang sesuai perannya saat tidak ada cookie **dan** akses `sessionStorage` sengaja dibuat gagal. Pengujian juga menunda pemeriksaan `/auth/me` anonim agar race yang ditemukan benar-benar terjadi; token memori tetap terbawa pada navigasi client.
- Halaman `/`, `/masuk?mode=login`, dan `/ruang-kerja` merespons `200`.

## Batas verifikasi

Host pratinjau eksternal tidak dapat dipanggil dari sandbox tanpa token akses E2B. Chromium lokal membuktikan alur browser aplikasi, termasuk tanpa cookie dan respons awal yang terlambat, tetapi bukan sesi di browser perangkat pengguna. Jangan masukkan data anak nyata pada versi uji.

Akun demo: `pengasuh@rumahkecilku.demo`, `dokter@rumahkecilku.demo`, atau `orangtua@rumahkecilku.demo`; kata sandi `RK-Preview-2026!`.
