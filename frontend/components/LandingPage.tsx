'use client';

import { useState } from 'react';
import type { JSX } from 'react';
import Link from 'next/link';

const roles = [
  {
    key: 'caregiver',
    label: 'Pengasuh',
    title: 'Kegiatan hari ini tercatat dengan rapi.',
    detail: 'Catat kehadiran, kegiatan, dan hal penting yang terjadi selama anak berada di daycare.',
    className: 'role-card-caregiver',
  },
  {
    key: 'doctor',
    label: 'Dokter',
    title: 'Pemeriksaan ditinjau sebelum dibagikan.',
    detail: 'Periksa formulir KPSP, baca catatan yang tersedia, lalu tulis ringkasan untuk keluarga.',
    className: 'role-card-doctor',
  },
  {
    key: 'parent',
    label: 'Orang tua',
    title: 'Kabar anak mudah diikuti.',
    detail: 'Lihat kegiatan yang dibagikan pengasuh dan ringkasan yang sudah ditinjau dokter.',
    className: 'role-card-parent',
  },
];

function BrandWordmark({ inverse = false }: { inverse?: boolean }): JSX.Element {
  return (
    <Link className={`brand-wordmark ${inverse ? 'brand-wordmark-inverse' : ''}`} href="/" aria-label="Rumah Kecilku, beranda">
      <span className="brand-wordmark-name">Rumah Kecilku</span>
      <span className="brand-wordmark-sub">DAY CARE</span>
    </Link>
  );
}

export default function LandingPage(): JSX.Element {
  const [menuOpen, setMenuOpen] = useState(false);
  const closeMenu = () => setMenuOpen(false);

  return (
    <div className="site-home">
      <header className="site-header">
        <div className="site-header-inner">
          <BrandWordmark />
          <button
            className={`mobile-nav-trigger ${menuOpen ? 'is-open' : ''}`}
            type="button"
            onClick={() => setMenuOpen((open) => !open)}
            aria-label={menuOpen ? 'Tutup menu' : 'Buka menu'}
            aria-expanded={menuOpen}
            aria-controls="site-navigation"
          >
            <span /><span />
          </button>
          <nav id="site-navigation" className={`site-navigation ${menuOpen ? 'site-navigation-open' : ''}`} aria-label="Navigasi situs">
            <a href="#alur" onClick={closeMenu}>Cara kerja</a>
            <a href="#ruang-kerja" onClick={closeMenu}>Fitur</a>
            <a href="#peran" onClick={closeMenu}>Untuk siapa</a>
            <Link className="site-nav-login" href="/masuk?mode=login" onClick={closeMenu}>Masuk</Link>
            <Link className="site-nav-cta" href="/masuk?mode=register" onClick={closeMenu}>Daftar orang tua</Link>
          </nav>
        </div>
      </header>

      <main>
        <section className="home-hero" aria-labelledby="home-heading">
          <div className="home-hero-inner">
            <div className="home-hero-copy">
              <p className="overline home-overline"><span className="overline-rule" />Tempat pengasuh dan keluarga saling terhubung</p>
              <h1 id="home-heading">Hari di daycare, tetap terasa <em>dekat di rumah.</em></h1>
              <p className="home-hero-description">
                Rumah Kecilku membantu pengasuh mencatat kegiatan, dokter meninjau pemeriksaan, dan keluarga mengikuti kabar anak dengan lebih mudah.
              </p>
              <div className="home-hero-actions">
                <Link className="button button-primary button-large" href="/masuk?mode=login">Masuk ke akun</Link>
                <a className="button button-text button-large" href="#alur">Kenali cara kerjanya</a>
              </div>
              <p className="home-hero-note"><span className="note-mark" aria-hidden="true">i</span> Profil dan catatan anak di halaman ini adalah contoh. Foto hanya ilustrasi.</p>
            </div>

            <div className="home-hero-art" aria-label="Suasana kegiatan anak di daycare">
              <figure className="hero-photo-frame">
                <img
                  src="/images/daycare-play.jpg"
                  alt="Pengasuh menemani beberapa anak bermain bersama di dalam ruangan."
                  fetchPriority="high"
                />
                <div className="hero-photo-topline"><span>HARI DI DAYCARE</span><span><i /> SUASANA KEGIATAN</span></div>
                <figcaption className="hero-photo-caption"><span>Waktu untuk bermain dan belajar</span><strong>Setiap momen punya cerita.</strong></figcaption>
              </figure>
              <div className="hero-photo-credit"><span>Foto ilustrasi</span><span>Foto oleh Ksenia Chernaya · Pexels</span></div>
            </div>
          </div>
          <div className="hero-footer-rule"><span>Kegiatan harian</span><span>Pemeriksaan dokter</span><span>Kabar keluarga</span></div>
        </section>

        <section id="alur" className="care-principle section-wrap" aria-labelledby="principle-heading">
          <div className="section-heading section-heading-split">
            <p className="overline"><span className="overline-rule" />Cara kerja</p>
            <div><h2 id="principle-heading">Satu hari, dirawat dengan <em>perhatian yang sama.</em></h2><p>Catatan berawal dari kegiatan, pemeriksaan dibaca dokter, lalu kabar yang dipilih sampai kepada keluarga.</p></div>
          </div>
          <div className="principle-flow">
            <article className="principle-step principle-step-first">
              <span className="principle-index">A</span>
              <div><h3>Pengasuh mencatat</h3><p>Makan, istirahat, bermain, dan hal penting lainnya dicatat setelah kegiatan berlangsung.</p></div>
              <span className="principle-label">KEGIATAN HARIAN</span>
            </article>
            <article className="principle-step principle-step-middle">
              <span className="principle-index">B</span>
              <div><h3>Dokter meninjau</h3><p>Hasil pemeriksaan perkembangan dibaca dokter sebelum ringkasan disiapkan untuk keluarga.</p></div>
              <span className="principle-label">TINJAUAN DOKTER</span>
            </article>
            <article className="principle-step principle-step-last">
              <span className="principle-index">C</span>
              <div><h3>Keluarga menerima kabar</h3><p>Orang tua melihat kegiatan yang dibagikan dan ringkasan yang sudah ditinjau.</p></div>
              <span className="principle-label">KABAR UNTUK KELUARGA</span>
            </article>
          </div>
          <p className="principle-footnote">KPSP membantu skrining perkembangan. Hasilnya bukan diagnosis dan perlu dibahas dengan tenaga kesehatan.</p>
        </section>

        <section id="ruang-kerja" className="product-story" aria-labelledby="product-heading">
          <div className="section-wrap product-story-inner">
            <div className="section-heading section-heading-split product-heading">
              <p className="overline"><span className="overline-rule" />Fitur Rumah Kecilku</p>
              <div><h2 id="product-heading">Rutinitas lebih ringan ketika <em>kabar tersusun rapi.</em></h2><p>Setiap bagian dibuat untuk membantu pekerjaan daycare sehari-hari dan menjaga komunikasi dengan keluarga.</p></div>
            </div>

            <div className="product-feature-grid">
              <article className="feature-ledger feature-surface">
                <div className="feature-ledger-copy">
                  <span className="feature-index">01 / KEGIATAN HARIAN</span>
                  <h3>Catat kegiatan saat masih segar di ingatan.</h3>
                  <p>Pengasuh dapat mencatat waktu makan, minum, tidur, bermain, dan hal yang perlu diketahui keluarga. Kabar hanya diteruskan saat dipilih untuk dibagikan.</p>
                  <Link href="/masuk?mode=login" className="feature-link">Masuk sebagai pengasuh <span aria-hidden="true">↗</span></Link>
                </div>
                <figure className="feature-photo-card">
                  <img src="/images/daycare-storytime.jpg" alt="Anak-anak duduk bersama seorang guru saat kegiatan membaca buku." loading="lazy" />
                  <figcaption><span>KEGIATAN BERSAMA</span><strong>Mendengar cerita, belajar bergiliran.</strong><small>Foto ilustrasi · Ksenia Chernaya / Pexels</small></figcaption>
                </figure>
              </article>

              <article className="feature-development">
                <div className="feature-development-copy">
                  <span className="feature-index">02 / PEMERIKSAAN PERKEMBANGAN</span>
                  <h3>Hasil pemeriksaan dibaca <em>oleh dokter.</em></h3>
                  <p>Pengasuh mencatat hal yang diamati. Dokter mengisi KPSP, memeriksa catatan yang tersedia, lalu menulis ringkasan untuk keluarga.</p>
                  <div className="aspect-line" aria-label="Empat area perkembangan">
                    <span>Gerak tubuh</span><i /> <span>Gerak tangan</span><i /> <span>Bahasa</span><i /> <span>Hubungan sosial</span>
                  </div>
                  <div className="feature-safety-note"><strong>Skrining bukan diagnosis.</strong><span>Ringkasan hanya dibagikan setelah diperiksa dan diterbitkan dokter.</span></div>
                </div>
                <div className="feature-development-art" aria-hidden="true">
                  <div className="orbit-ring orbit-ring-a" /><div className="orbit-ring orbit-ring-b" />
                  <div className="evidence-paper evidence-paper-back"><span>CATATAN</span><i /><i /><i /></div>
                  <div className="evidence-paper evidence-paper-front"><span>RINGKASAN DOKTER</span><strong>Dibagikan<br />setelah ditinjau</strong><small>Dengan penjelasan yang jelas</small></div>
                </div>
              </article>

              <article className="feature-climate">
                <div className="climate-copy">
                  <span className="feature-index">03 / KONDISI RUANG</span>
                  <h3>Suhu ruang tercatat saat alat tersedia.</h3>
                  <p>Pengasuh dapat melihat suhu dan kelembapan setelah alat pengukur terhubung. Kami tidak menampilkan angka perkiraan.</p>
                  <span className="feature-link feature-link-static">Belum ada alat yang terhubung</span>
                </div>
                <div className="climate-art" aria-label="Belum ada pembacaan suhu atau kelembapan">
                  <div className="climate-art-head"><span>KONDISI RUANG</span><span className="climate-status climate-status-offline"><i /> BELUM TERHUBUNG</span></div>
                  <div className="climate-reading"><span className="climate-gauge climate-gauge-temp"><i>°</i></span><span><small>SUHU</small><strong>--</strong><em>Belum ada pembacaan</em></span></div>
                  <div className="climate-reading climate-reading-humidity"><span className="climate-gauge climate-gauge-humidity"><i>~</i></span><span><small>KELEMBAPAN</small><strong>--</strong><em>Belum ada pembacaan</em></span></div>
                  <p>Angka akan muncul setelah alat terhubung dan mengirim pembacaan.</p>
                </div>
              </article>

              <article className="feature-messages">
                <div className="message-quote-mark" aria-hidden="true">“</div>
                <span className="feature-index">04 / KABAR UNTUK KELUARGA</span>
                <h3>Pesan berangkat dari catatan pengasuh.</h3>
                <p>Pengasuh memilih kegiatan yang boleh dibagikan. MessaCare membantu menyusun kabar berdasarkan catatan itu, tanpa menilai perkembangan anak.</p>
                <div className="message-preview message-preview-plain"><span className="message-preview-label">SEBELUM DIBAGIKAN</span><div className="message-steps"><span>Catatan kegiatan</span><i>→</i><span>Periksa isi pesan</span><i>→</i><span>Kirim ke keluarga</span></div><span className="message-preview-source">Keluarga menerima kabar yang dipilih pengasuh.</span></div>
              </article>
            </div>
          </div>
        </section>

        <section id="peran" className="roles-section section-wrap" aria-labelledby="roles-heading">
          <div className="section-heading section-heading-split">
            <p className="overline"><span className="overline-rule" />Akses sesuai peran</p>
            <div><h2 id="roles-heading">Satu tempat, <em>ruang kerja yang sesuai.</em></h2><p>Masuk menggunakan akun sendiri. Setiap peran membuka kegiatan yang berbeda.</p></div>
          </div>
          <div className="role-card-grid">
            {roles.map((role) => (
              <article className={`role-card ${role.className}`} key={role.key}>
                <span className="role-card-label">{role.label}</span>
                <h3>{role.title}</h3>
                <p>{role.detail}</p>
                {role.key === 'parent' ? (
                  <Link className="role-card-link" href="/masuk?mode=register">Daftar sebagai orang tua <span aria-hidden="true">↗</span></Link>
                ) : (
                  <Link className="role-card-link" href="/masuk?mode=login">Masuk dengan akun terverifikasi <span aria-hidden="true">↗</span></Link>
                )}
              </article>
            ))}
          </div>
          <p className="role-setup-note">Pendaftaran mandiri hanya untuk orang tua dan belum memverifikasi hubungan keluarga dengan anak. Akun pengasuh dan dokter memerlukan undangan serta verifikasi institusi.</p>
        </section>

        <section className="publication-section" aria-labelledby="publication-heading">
          <div className="publication-inner section-wrap">
            <div className="publication-label">TINJAUAN DOKTER</div>
            <div className="publication-copy">
              <p className="overline">Hal yang selalu dijaga</p>
              <h2 id="publication-heading">Hasil skrining <em>bukan diagnosis.</em></h2>
              <p>Pengasuh mengamati. Dokter memeriksa. Keluarga menerima ringkasan setelah dokter meninjaunya.</p>
            </div>
            <Link href="/masuk?mode=login" className="button button-light button-large">Masuk ke akun</Link>
          </div>
        </section>

        <section className="final-invitation section-wrap" aria-labelledby="invitation-heading">
          <div><p className="overline"><span className="overline-rule" />Rumah Kecilku Day Care</p><h2 id="invitation-heading">Mulai dengan kabar yang <em>lebih bermakna.</em></h2></div>
          <div className="final-invitation-actions"><Link className="button button-primary button-large" href="/masuk?mode=register">Daftar sebagai orang tua</Link><Link className="button button-outline button-large" href="/masuk?mode=login">Saya sudah punya akun</Link></div>
        </section>
      </main>

      <footer className="site-footer">
        <BrandWordmark />
        <p>Profil anak yang terlihat di halaman ini adalah contoh. Foto kegiatan berasal dari Pexels.</p>
        <nav aria-label="Navigasi footer"><a href="#alur">Cara kerja</a><a href="#ruang-kerja">Fitur</a><a href="#peran">Peran</a><Link href="/masuk?mode=login">Masuk</Link></nav>
        <span className="footer-signoff">Pengasuhan dengan perhatian dan kabar yang jernih.</span>
      </footer>
    </div>
  );
}
