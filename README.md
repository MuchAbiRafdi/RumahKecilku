# Rumah Kecilku Day Care: prototipe dashboard

Ruang kerja demonstrasi untuk empat peran: pengasuh, dokter, admin operasional, dan orang tua. Frontend memakai Next.js; backend memakai FastAPI dan SQLite. Alur berawal dari landing page, lalu masuk atau daftar, kemudian dashboard dengan navigasi sesuai peran akun.

> **Cakupan implementasi terbaru:** fondasi multi-daycare, pembatasan akses berbasis organisasi/anak, role admin berhak minimum, katalog menu per tenant, dan kredensial sensor unik per perangkat sudah ditambahkan serta diuji. Check-in/out dan catatan serah-terima penjemput berizin tersedia sebagai alur demo terbatas: admin mencatat setelah konfirmasi orang tua di luar aplikasi, lalu staf mencocokkan nama secara langsung. Verifikasi identitas independen, kontak darurat, penerimaan daycare/staf, jadwal/rasio staf, modul insiden/obat, serta kontrol privasi/retensi tetap belum lengkap. Jangan gunakan data anak nyata.

> **Mode demonstrasi.** Semua profil dan catatan bawaan adalah sintetis. Jangan memasukkan identitas atau data kesehatan anak nyata. Akun dan pembatasan peran ini belum layak untuk produksi atau penggunaan klinis.

## Menjalankan frontend dan backend

Persyaratan: Node.js 20+ dan Python 3.11+.

```bash
npm install
python3 -m venv backend/.venv
backend/.venv/bin/pip install -r backend/requirements-dev.txt
npm run dev
```

`npm run dev` menjalankan Next.js pada port `3000` dan FastAPI pada port `8000`. Next.js meneruskan `/api/*` ke backend, default-nya `http://127.0.0.1:8000`. Atur `BACKEND_ORIGIN` bila backend berjalan di alamat berbeda.

Perintah verifikasi:

```bash
npm run test:api  # aturan umur, KPSP, autentikasi, akses peran, dan API
npm run build     # build produksi Next.js
npm run start     # jalankan hasil build Next.js; backend dijalankan terpisah
```

Jika backend dijalankan langsung tanpa flag seed demo, database default berada di `backend/data/rumah_kecilku.sqlite3`. Launcher preview membuat database sintetis sementara di `/tmp` saat `RUMAH_DB_PATH` tidak diatur; atur `RUMAH_DB_PATH` eksplisit hanya ke file database preview yang terpisah bila perlu mempertahankan sesi demo.

## Akun dan sesi

- `/` adalah landing page publik; `/ruang-kerja` memeriksa sesi aktif sebelum memuat dashboard.
- Pendaftaran publik hanya dapat membuat akun **orang tua**. Akun dokter/pengasuh/admin tidak dapat dipilih saat mendaftar. Alur undangan dan verifikasi institusi belum tersedia; staf/daycare hanya dapat disiapkan lewat provisioning terkontrol oleh operator sampai alur tersebut dibangun.
- Akun demo hanya dibuat atau diperbaiki saat `RUMAH_DEMO_MODE=1` dalam `RUMAH_APP_ENV=preview`. Launcher `npm run dev` dan `npm run preview` secara eksplisit mengaktifkan mode itu untuk data sintetis. Sembilan observasi demo bertanda `DATA SINTETIS DEMO` di-seed idempotent hanya saat `RUMAH_DEMO_SAMPLE_DATA=1` pada preview; launcher backend memakai database sementara di `/tmp` bila `RUMAH_DB_PATH` tidak ditentukan, agar tidak mengubah database lokal lain. `scripts/start-production-preview.sh` adalah nama lama untuk preview ter-embed—bukan launcher produksi.
- Password disimpan sebagai hash scrypt. Sesi memakai token acak yang disimpan sebagai hash, cookie HttpOnly/SameSite=Lax, dan berakhir setelah 12 jam. Percobaan login dibatasi per alamat akun; header bearer hanya diterima pada preview sintetis yang mengaktifkan flag token browser.
- Basis data baru dibuat dengan izin file privat pada POSIX. Ini bukan enkripsi at-rest dan bukan pengganti enkripsi volume, manajemen kunci, kontrol backup, atau hardening host.

Akun demo memakai profil sintetis. Kredensial bersama `RK-Preview-2026!` hanya untuk preview dan tidak boleh digunakan untuk akun atau data nyata.

| Peran | Email demo |
|---|---|
| Pengasuh | `pengasuh@rumahkecilku.demo` |
| Dokter | `dokter@rumahkecilku.demo` |
| Admin operasional | `admin@rumahkecilku.demo` |
| Orang tua | `orangtua@rumahkecilku.demo` |

**Penting:** `RUMAH_APP_ENV=production` saat ini sengaja membuat aplikasi menolak startup. Lihat [`SECURITY_AUDIT.md`](SECURITY_AUDIT.md) untuk temuan, mitigasi, tes regresi, dan blocker sebelum data anak nyata boleh diproses.

## Endpoint dan batas akses

- `POST /api/auth/register` hanya menerima role `parent`; `POST /api/auth/login`, `POST /api/auth/logout`, dan `GET /api/auth/me` mengelola sesi. `GET /api/auth/me` mengembalikan `{"user": null}` bila belum masuk. API menambahkan header keamanan/no-store dan menolak request body di atas 5 MiB.
- `GET /api/children` hanya mengembalikan profil tenant aktif atau profil keluarga yang sudah tertaut; `GET /api/children/links` memberi cakupan anak staf dari membership server-side. `POST /api/children` dan `PATCH /api/children/{child_id}` hanya admin tenant yang dapat membuat atau memperbarui nama, tanggal lahir, dan ruang roster. Perubahan profil mencatat actor dan nama kolom yang berubah (bukan nilai lama/baru) pada audit yang hanya admin tenant dapat baca lewat `GET /api/children/{child_id}/profile-audit`. Orang tua mendapat akses hanya setelah status relasi wali `verified`.
- Relasi wali memakai dua langkah: admin tenant memilih akun parent yang sudah menjadi anggota daycare yang sama dan mencatat metode pemeriksaan institusi (tanpa menyimpan nomor/foto dokumen), lalu parent harus mengonfirmasi sendiri. `GET /api/children/{child_id}/guardian-candidates`, `GET /api/children/{child_id}/guardians`, `POST /api/children/{child_id}/guardians`, `POST /api/children/{child_id}/guardians/{parent_user_id}/revoke`, `GET /api/children/{child_id}/guardian-links/audit`, dan endpoint parent `/api/children/guardian-invitations` serta `.../{child_id}/guardian-invitations/{accept|reject}` mengelola alur tersebut. Relasi lama tanpa bukti pemeriksaan bermigrasi ke `pending` (tidak memberi akses sampai ditinjau ulang); akun demo memakai tautan berlabel seed sintetis. Alur undangan email/akun baru dan verifikasi identitas institusional penuh belum tersedia.
- Kehadiran: `POST /api/attendance/check-in` dan `POST /api/attendance/check-out` mencatat waktu lokal, petugas, dan penjemput berizin; check-out gagal jika tidak ada check-in aktif, nama tidak aktif, atau staf belum mengirim `pickup_name_match_confirmed: true`. Konfirmasi pencocokan nama itu tercatat pada peristiwa check-out. Admin menambah/mencabut nama di `/api/attendance/children/{child_id}/authorized-pickups` setelah merekam konfirmasi orang tua di luar aplikasi. Caregiver hanya membaca nama/relasi untuk serah-terima; jejak audit (`GET /api/attendance/events`) hanya admin. `GET /api/attendance` membatasi catatan ke anak dalam cakupan sesi; keluarga tertaut dapat membaca nama penjemput yang tercatat, dokter tidak. Tidak ada nomor telepon, nomor identitas, atau foto dokumen yang disimpan. Pencocokan langsung adalah kontrol operasional, bukan verifikasi identitas independen.
- `POST /api/activities` hanya dapat dipakai pengasuh untuk anak dalam tenant aktif. `GET /api/activities` dan foto menerapkan cakupan anak server-side; orang tua hanya melihat aktivitas yang dibagikan untuk anak tertaut. MessaCare tetap memakai template deterministik (tanpa LLM/API AI eksternal).
- Tenant dan keanggotaan organisasi menjadi dasar pembatasan aktivitas, observasi, laporan, KPSP, kehadiran, pesan/notifikasi, menu, dan sensor. Tes regresi memverifikasi dua daycare berbeda tidak dapat saling membaca atau mengubah roster/kehadiran/aktivitas/katalog. Namun onboarding daycare/staf dan verifikasi institusi belum tersedia; hal ini bukan bukti kesiapan produksi.
- `GET /api/notifications`, `POST /api/notifications/reminders`, `POST /api/notifications/{id}/read`, dan `POST /api/notifications/{id}/complete` mengelola kabar dan pengingat tersimpan. Pesan chat juga membuat notifikasi untuk penerima terkait.
- `GET /api/sensors/summary` hanya untuk pengasuh, dokter, atau admin dan hanya membaca perangkat dari tenant yang diotorisasi. Admin mendaftarkan perangkat melalui `POST /api/sensors/devices`; kunci unik perangkat ditampilkan sekali. Perangkat mengirim `POST /api/sensors/readings` menggunakan header `X-Sensor-Key`. Kunci API global lama tidak lagi digunakan. Gunakan HTTPS dan simpan kunci perangkat di secret store perangkat.
- Katalog pangan memuat contoh data TKPI Kemenkes (nasi, bayam, susu sapi segar, pisang ambon, ubi kukus, dan biskuit). Nilai per 100 g BDD ditampilkan bersama contoh porsi yang dihitung proporsional. Setiap entri menautkan sumber; data TKPI 2019 bayam/susu/pisang memakai halaman sekunder yang mengutip Kemenkes/TKPI, sedangkan TKPI 2020 menautkan katalog buku Kemenkes. Entri kustom tersimpan per organisasi; hanya dokter/admin tenant yang dapat menambahnya.
- Jadwal, formulir, dan penyimpanan asesmen KPSP hanya dapat dipakai akun dokter yang sedang masuk.
- `POST /api/ai/messacare/announcement` hanya dapat dipakai akun pengasuh sebagai endpoint template terpisah.
- `GET /api/development/insights/{child_id}` hanya untuk pengasuh/dokter dan menggunakan observasi milestone terstruktur pada periode yang dipilih; log aktivitas umum dan jawaban KPSP mentah tidak dianalisis. Respons menunjukkan jumlah/kategori catatan, tanggal terakhir, langkah pengasuh, titik tinjauan dokter, dan data berikutnya yang membantu. Isi catatan bebas tidak ditampilkan di kartu insight atau dikirim ke pihak ketiga. Ringkasan bukti memakai aturan lokal deterministik. Dalam mode demo, kategori ide aktivitas umum dipilih oleh Naive Bayes lokal yang dilatih dari 96 skenario mock sintetis di `backend/app/data/mock_activity_training.json`; model tidak memakai catatan anak untuk pelatihan, tidak menilai perkembangan, dan belum divalidasi klinis.
- `GET /api/development/model-status` memerlukan sesi. Endpoint menjelaskan bahwa model aktivitas demo terlatih pada contoh sintetis, tidak memakai API AI pihak ketiga, serta bukan model klinis. IRT/Bayesian dan penilaian/prediksi perkembangan otomatis belum tersedia.
- `GET /api/health` menyediakan status layanan dasar.

## Struktur repository

```text
frontend/
  app/                 # rute Next.js, metadata, dan desain responsif
  components/          # landing, autentikasi, dashboard peran, dan workspace KPSP
  lib/                 # API client, data demo, kalkulasi umur
  public/kpsp-assets/  # stimulus gambar yang diekstrak dari PDF
  public/kpsp-catalog.json  # katalog fallback saat API offline
backend/
  app/api/routes/      # autentikasi, KPSP, MessaCare, dan status model
  app/ai/              # insight bukti lokal dan classifier aktivitas demo
  app/core/            # hash password/token sesi, konfigurasi fail-closed, middleware keamanan
  app/data/kpsp_forms.json  # katalog dari PDF
  app/data/mock_activity_training.json  # 96 skenario training sintetis, tanpa data anak
  app/repositories/    # penyimpanan SQLite
  app/services/        # kalkulasi umur dan skor skrining
  tests/               # tes backend
scripts/                # runner dan utilitas
```

## KPSP dari PDF terlampir

Sumber: `pdf-kpsp-depkes_compress.pdf` dari pengguna. Tersedia 16 kelompok usia: 3, 6, 9, 12, 15, 18, 21, 24, 30, 36, 42, 48, 54, 60, 66, dan 72 bulan. Formulir usia 42 dan 48 bulan masing-masing memiliki 9 butir; kelompok usia lain memiliki 10 butir. Stimulus gambar diambil dari halaman PDF.

Aturan implementasi:

- Umur dihitung dari tanggal lahir dan tanggal pemeriksaan. Bila sisa umur **lebih dari 16 hari**, umur dibulatkan naik satu bulan. Sisa 16 hari atau kurang tidak dibulatkan.
- Pemeriksaan rutin sebelum usia skrining berikutnya hanya dijadwalkan; formulir tidak diisi lebih awal. Bila tepat pada usia jadwal, gunakan usia itu.
- Bila ada keluhan dan umur bukan umur skrining, pilih usia skrining terdekat yang lebih muda. Jika belum ada kelompok lebih muda, arahkan ke tenaga kesehatan.
- Skor S/M/P dihitung menurut jumlah jawaban “Ya” dan jumlah butir pada formulir. Rincian jawaban “Tidak” per domain hanya diberikan bila domain tercantum di PDF. Butir 6–10 pada formulir 24 bulan tetap tanpa domain.
- Catatan pemeriksa dipisahkan dari pertanyaan agar kunci tidak terbaca sebagai prompt.
- Hasil KPSP adalah **skrining, bukan diagnosis**. Hasil tersimpan untuk tinjauan dokter dan tidak ditampilkan kepada keluarga sebelum dokter menerbitkan ringkasan.

Endpoint utama: `GET /api/kpsp/schedules`, `GET /api/kpsp/forms/{age_months}`, `POST /api/kpsp/assessments`, dan `GET /api/kpsp/children/{child_id}/assessments`.

## Fitur yang berjalan dan batas prototipe

- Pengasuh mencatat aktivitas per sesi, memilih mood dengan emoji, merangkai beberapa bahan menu, dan dapat membagikan foto dummy dengan konfirmasi privasi. `POST /api/activities` menyimpan aktivitas, snapshot gizi, dan foto di SQLite; jika dibagikan, keluarga tertaut mendapat notifikasi tersimpan.
- Dokter dapat membuka KPSP, meninjau antrean demo, menyimpan catatan tinjauan, dan menerbitkan ringkasan yang kemudian terlihat pada ruang keluarga demo.
- Orang tua pada UI demo melihat aktivitas/foto yang dibagikan, notifikasi dan pengingat tersimpan, serta ringkasan dokter yang diterbitkan. Pemberitahuan in-app diperbarui dengan polling saat aplikasi terbuka; pop-up browser memerlukan izin. Web Push/service worker untuk aplikasi tertutup belum dipasang. Tautan keluarga baru memakai pemeriksaan admin + konfirmasi parent, dapat dicabut, dan jejaknya tersimpan; tautan demo tetap sintetis. Undangan email/akun wali baru, pemeriksaan identitas institusional penuh, dan audit tahan perubahan belum tersedia.
- Rekap kelas dihitung dari kehadiran dan aktivitas yang tersimpan. Pembacaan suhu/kelembapan tidak dibuat-buat: panel tetap kosong sampai perangkat mengirim data melalui endpoint sensor yang terkunci API key. Preview ini belum dikonfigurasi dengan perangkat fisik atau kunci sensor.
- Estimasi Child Development Intelligence untuk empat aspek belum dihitung. IRT/Bayesian sengaja fail-closed karena bank butir, parameter, data kalibrasi, dan validasi klinis belum tersedia. Ringkasan bukti tetap memakai aturan lokal; dalam mode demo, model Multinomial Naive Bayes yang benar-benar dilatih dari 96 contoh aktivitas sintetis memilih satu ide kegiatan umum berdasarkan aspek dan kategori bukti. Data latihan tidak berisi rekam anak atau label klinis. Ide model menampilkan sumber sintetis dan batas penggunaan; belum ada validasi klinis dan tidak ada diagnosis, skrining, prediksi, atau terapi. Kartu juga menunjukkan dasar jumlah/tanggal, keterbatasan, langkah terpisah untuk pengasuh/dokter, dan data yang masih membantu.
- Sebagian besar tampilan/fitur dashboard tetap prototipe dan beberapa preferensi hanya disimpan di `localStorage`. Isolasi organisasi dan pemeriksaan akses berdasarkan `organization_id`/`child_id` sudah menjadi fondasi backend; alur relasi wali demo memakai konfirmasi admin+parent. Alur check-in/out dan penjemput berizin kini ada dengan pencatatan admin setelah konfirmasi parent di luar aplikasi, tetapi bukan verifikasi identitas independen. Onboarding daycare/staf, kontak darurat, verifikasi identitas penuh, jadwal/rasio staf, catatan insiden/alergi/obat yang dibatasi, ekspor berhak akses, serta pemulihan akun/MFA belum diimplementasikan.
- Consent dan pencabutan izin yang dapat diaudit, retensi/penghapusan terverifikasi, audit tahan perubahan, enkripsi produksi, backup terenkripsi, monitoring, pengujian E2E lintas browser, dan validasi klinis tetap belum lengkap. Demo mengandung akun bersama dan data sintetis. Aplikasi sengaja menolak `RUMAH_APP_ENV=production`; jangan membuka produksi atau menyimpan data nyata sebelum blocker ini ditutup.
