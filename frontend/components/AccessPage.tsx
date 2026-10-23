'use client';

import { useEffect, useRef, useState } from 'react';
import type { FormEvent, JSX } from 'react';
import { useRouter } from 'next/navigation';
import Link from 'next/link';
import { ApiError, apiGet, apiPost, clearSessionToken, setSessionToken } from '../lib/api';
import type { AuthUser, Role } from '../lib/types';

interface RoleOption {
  id: Role;
  label: string;
  detail: string;
}

interface DemoAccount {
  role: Role;
  label: string;
  email: string;
}

const ROLE_OPTIONS: RoleOption[] = [
  { id: 'parent', label: 'Orang tua', detail: 'Kabar hari dan laporan anak' },
  { id: 'caregiver', label: 'Pengasuh', detail: 'Aktivitas, observasi, dan ruang' },
  { id: 'doctor', label: 'Dokter', detail: 'KPSP dan tinjauan perkembangan' },
  { id: 'admin', label: 'Admin operasional', detail: 'Roster, kehadiran, dan katalog menu' },
];

const DEMO_ACCOUNTS: DemoAccount[] = [
  { role: 'caregiver', label: 'Pengasuh', email: 'pengasuh@rumahkecilku.demo' },
  { role: 'doctor', label: 'Dokter', email: 'dokter@rumahkecilku.demo' },
  { role: 'admin', label: 'Admin operasional', email: 'admin@rumahkecilku.demo' },
  { role: 'parent', label: 'Orang tua', email: 'orangtua@rumahkecilku.demo' },
];
const DEMO_PASSWORD = 'RK-Preview-2026!';
const DEMO_MODE = process.env.NEXT_PUBLIC_DEMO_MODE === '1';

function BrandWordmark() {
  return (
    <Link className="brand-wordmark" href="/" aria-label="Kembali ke beranda Rumah Kecilku">
      <span className="brand-wordmark-name">Rumah Kecilku</span>
      <span className="brand-wordmark-sub">DAY CARE</span>
    </Link>
  );
}

function RoleBadge({ role }: { role: Role }): JSX.Element {
  const roleLabel = ROLE_OPTIONS.find((item) => item.id === role)?.label || 'Pengguna';
  return <span className={`auth-role-badge auth-role-${role}`}>{roleLabel}</span>;
}

interface AccessPageProps {
  initialMode?: 'login' | 'register';
}

export default function AccessPage({ initialMode = 'login' }: AccessPageProps): JSX.Element {
  const router = useRouter();
  const routerRef = useRef(router);
  routerRef.current = router;
  const initialSessionCheckDone = useRef(false);
  const [mode, setMode] = useState(initialMode);
  const role: Role = 'parent';
  const [name, setName] = useState('');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');
  const [showPassword, setShowPassword] = useState(false);

  useEffect(() => {
    if (initialSessionCheckDone.current) return;
    initialSessionCheckDone.current = true;
    apiGet<{ user: AuthUser | null }>('auth/me')
      .then((payload) => { if (payload.user) routerRef.current.replace('/ruang-kerja'); })
      .catch(() => {});
  }, []);

  const updateMode = (nextMode: 'login' | 'register'): void => {
    setMode(nextMode);
    setError('');
    setNotice('');
    const params = new URLSearchParams(window.location.search);
    params.set('mode', nextMode);
    if (nextMode === 'register') params.set('role', 'parent');
    else params.delete('role');
    window.history.replaceState(null, '', `/masuk?${params.toString()}`);
  };

  const submitLogin = async (loginEmail: string, loginPassword: string): Promise<void> => {
    setBusy(true);
    setError('');
    setNotice('');
    clearSessionToken();
    try {
      const login = await apiPost<{ user: AuthUser; session_token?: string }>('auth/login', { email: loginEmail, password: loginPassword });
      if (!login?.user?.id) throw new ApiError('Akun belum dapat dikenali. Coba lagi.', 401);
      if (typeof login.session_token === 'string') setSessionToken(login.session_token);
      const session = await apiGet<{ user: AuthUser | null }>('auth/me');
      if (session?.user?.id !== login.user.id) {
        throw new ApiError('Akun dikenali, tetapi sesi masuk belum aktif. Muat ulang halaman lalu coba lagi.', 401);
      }
      router.replace('/ruang-kerja');
    } catch (cause) {
      setError(cause instanceof ApiError ? cause.message : 'Masuk belum berhasil. Coba lagi.');
      setBusy(false);
    }
  };

  const handleSubmit = async (event: FormEvent<HTMLFormElement>): Promise<void> => {
    event.preventDefault();
    if (busy) return;
    if (mode === 'login') {
      await submitLogin(email.trim(), password);
      return;
    }
    setBusy(true);
    setError('');
    setNotice('');
    clearSessionToken();
    try {
      const registration = await apiPost<{ user: AuthUser; session_token?: string }>('auth/register', { name: name.trim(), email: email.trim(), password, role: 'parent' });
      if (typeof registration?.session_token === 'string') setSessionToken(registration.session_token);
      const session = await apiGet<{ user: AuthUser | null }>('auth/me');
      if (!registration?.user?.id || session?.user?.id !== registration.user.id) {
        throw new ApiError('Akun dibuat, tetapi sesi masuk belum aktif. Muat ulang halaman lalu coba masuk.', 401);
      }
      router.replace('/ruang-kerja');
    } catch (cause) {
      setError(cause instanceof ApiError ? cause.message : 'Pendaftaran belum berhasil. Coba lagi.');
      setBusy(false);
    }
  };

  const openDemo = (account: DemoAccount): void => {
    setEmail(account.email);
    setPassword(DEMO_PASSWORD);
    setMode('login');
    setError('');
    setNotice(`Membuka ruang ${account.label.toLowerCase()} demo…`);
    const params = new URLSearchParams(window.location.search);
    params.set('mode', 'login');
    params.delete('role');
    window.history.replaceState(null, '', `/masuk?${params.toString()}`);
    void submitLogin(account.email, DEMO_PASSWORD);
  };

  return (
    <main className="access-page">
      <aside className="access-story" aria-label="Tentang ruang kerja Rumah Kecilku">
        <div className="access-story-top"><BrandWordmark /><Link href="/" className="access-back-link">Kembali ke beranda</Link></div>
        <div className="access-story-content">
          <p className="overline access-overline"><span className="overline-rule" />Ruang kerja sesuai tanggung jawab</p>
          <h1>Setiap catatan punya <em>tempat dan peninjau.</em></h1>
          <p>Masuk ke alur yang dirancang untuk kegiatan harian, komunikasi keluarga, serta tinjauan perkembangan yang berhati-hati.</p>
          <div className="access-story-flow">
            <div><span className="story-flow-index">A</span><span><strong>Dicatat pengasuh</strong><small>Kegiatan dan observasi</small></span></div>
            <i aria-hidden="true" />
            <div><span className="story-flow-index">B</span><span><strong>Ditinjau dokter</strong><small>Sebelum ringkasan terbit</small></span></div>
            <i aria-hidden="true" />
            <div><span className="story-flow-index">C</span><span><strong>Dibaca keluarga</strong><small>Sesuai izin dan peran</small></span></div>
          </div>
          <p className="access-story-footnote">KPSP adalah skrining, bukan diagnosis. Penilaian perkembangan otomatis belum tersedia pada versi uji.</p>
        </div>
        <div className="access-art" aria-hidden="true"><span className="access-art-layer access-art-layer-back" /><span className="access-art-layer access-art-layer-front" /><span className="access-art-leaf access-art-leaf-one" /><span className="access-art-leaf access-art-leaf-two" /></div>
      </aside>

      <section className="access-main" aria-labelledby="access-title">
        <div className="access-main-inner">
          <div className="access-mobile-brand"><BrandWordmark /><Link href="/" className="access-back-link">Beranda</Link></div>
          <div className="access-heading-row">
            <div>
              <p className="overline"><span className="overline-rule" />Rumah Kecilku Day Care</p>
              <h2 id="access-title">{mode === 'login' ? 'Selamat datang kembali.' : 'Daftar sebagai orang tua.'}</h2>
              <p>{mode === 'login' ? 'Masuk menggunakan akun dengan peran yang sudah terdaftar.' : 'Pendaftaran mandiri hanya tersedia untuk akun orang tua.'}</p>
            </div>
            {mode === 'register' && <RoleBadge role={role} />}
          </div>

          <div className="access-tabs" role="tablist" aria-label="Akses akun">
            <button type="button" role="tab" aria-selected={mode === 'login'} className={mode === 'login' ? 'access-tab access-tab-active' : 'access-tab'} onClick={() => updateMode('login')}>Masuk</button>
            <button type="button" role="tab" aria-selected={mode === 'register'} className={mode === 'register' ? 'access-tab access-tab-active' : 'access-tab'} onClick={() => updateMode('register')}>Daftar</button>
          </div>

          <form className="access-form" onSubmit={handleSubmit} aria-busy={busy}>
            {mode === 'register' && <label className="access-field"><span>Nama lengkap</span><input type="text" name="name" autoComplete="name" value={name} onChange={(event) => setName(event.target.value)} placeholder="Nama Anda" minLength={2} maxLength={80} required /></label>}
            <label className="access-field"><span>Email</span><input type="email" name="email" autoComplete="email" value={email} onChange={(event) => setEmail(event.target.value)} placeholder="nama@contoh.id" maxLength={160} required /></label>
            <div className="access-field"><label htmlFor="access-password">Kata sandi</label><span className="access-password-wrap"><input id="access-password" type={showPassword ? 'text' : 'password'} name="password" autoComplete={mode === 'login' ? 'current-password' : 'new-password'} value={password} onChange={(event) => setPassword(event.target.value)} placeholder={mode === 'login' ? 'Masukkan kata sandi' : 'Sedikitnya 10 karakter'} minLength={mode === 'register' ? 10 : 1} maxLength={200} required /><button className="password-toggle" type="button" onClick={() => setShowPassword((visible) => !visible)} aria-label={showPassword ? 'Sembunyikan kata sandi' : 'Lihat kata sandi'}>{showPassword ? 'Sembunyikan' : 'Lihat'}</button></span>{mode === 'register' && <small className="field-hint">Gunakan sedikitnya 10 karakter.</small>}</div>

            {mode === 'register' && <div className="access-role-note"><RoleBadge role="parent" /><p>Akun pengasuh dan dokter hanya dapat dibuat melalui proses undangan dan verifikasi institusi; pendaftaran mandiri tidak dapat memilih peran staf.</p></div>}

            {error && <div className="access-feedback access-feedback-error" role="alert">{error}</div>}
            {notice && <div className="access-feedback access-feedback-notice" role="status">{notice}</div>}
            <button className="button button-primary access-submit" type="submit" disabled={busy}>
              {busy ? <><span className="button-spinner" aria-hidden="true" />Sedang menghubungkan…</> : mode === 'login' ? 'Masuk ke ruang kerja' : 'Daftar dan lanjutkan'}
            </button>
            <p className="access-form-note">Sesi demo akan mengingat akun ini selama browser tetap masuk. Keluar dari menu akun untuk mengakhiri sesi.</p>
          </form>

          {mode === 'login' && DEMO_MODE && <section className="demo-access" aria-labelledby="demo-access-title">
            <div className="demo-access-heading"><span className="overline-rule" /><h3 id="demo-access-title">Coba akun demo</h3></div>
            <p>Akun berikut memakai profil anak contoh. Pilih akun untuk melihat ruang sesuai peran.</p>
            <div className="demo-account-list">{DEMO_ACCOUNTS.map((account) => <button key={account.role} type="button" className="demo-account-button" onClick={() => openDemo(account)} disabled={busy}><span className={`demo-account-initial demo-initial-${account.role}`}>{account.label.slice(0, 1)}</span><span><strong>{account.label}</strong><small>{account.email}</small></span><span className="demo-open-label">Buka</span></button>)}</div>
            <details className="demo-credentials"><summary>Perlu kata sandi untuk masuk manual?</summary><p>Kata sandi akun demo: <code>{DEMO_PASSWORD}</code>. Jangan gunakan data anak nyata pada versi uji ini.</p></details>
          </section>}

          <div className="access-footer"><span>Data demonstrasi bukan catatan anak nyata.</span><Link href="/">Tentang Rumah Kecilku</Link></div>
        </div>
      </section>
    </main>
  );
}
