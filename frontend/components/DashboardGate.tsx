'use client';

import { useCallback, useEffect, useRef, useState } from 'react';
import { useRouter } from 'next/navigation';
import DashboardApp from './DashboardApp';
import type { JSX } from 'react';
import { ApiError, apiGet, apiPost, clearSessionToken } from '../lib/api';
import type { AuthUser } from '../lib/types';

export default function DashboardGate(): JSX.Element {
  const router = useRouter();
  const routerRef = useRef(router);
  routerRef.current = router;
  const checkedAttemptRef = useRef<number | null>(null);
  const [user, setUser] = useState<AuthUser | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [attempt, setAttempt] = useState(0);

  useEffect(() => {
    if (checkedAttemptRef.current === attempt) return;
    checkedAttemptRef.current = attempt;
    setLoading(true);
    setError('');
    apiGet<{ user: AuthUser | null }>('auth/me')
      .then((payload) => {
        if (payload.user) setUser(payload.user);
        else routerRef.current.replace('/masuk?mode=login');
      })
      .catch((cause) => {
        if (cause instanceof ApiError && cause.status === 401) {
          routerRef.current.replace('/masuk?mode=login');
          return;
        }
        setError(cause instanceof Error ? cause.message : 'Ruang kerja belum dapat dimuat.');
      })
      .finally(() => setLoading(false));
  }, [attempt]);

  const logout = useCallback(async () => {
    // Send the revocation with the current token, then immediately block any background refreshes.
    const revocation = apiPost('auth/logout', {});
    clearSessionToken();
    try { await revocation; } catch { /* local exit remains available if the API is offline */ }
    router.replace('/');
  }, [router]);

  if (user) return <DashboardApp user={user} onLogout={logout} />;
  if (error) return <main className="gate-state"><div className="gate-card"><p className="overline"><span className="overline-rule" />Ruang Rumah Kecilku</p><h1>Ruang kerja belum tersambung.</h1><p>{error}</p><div className="gate-actions"><button className="button button-primary" type="button" onClick={() => setAttempt((value) => value + 1)}>Coba lagi</button><a className="button button-outline" href="/masuk?mode=login">Kembali ke masuk</a></div></div></main>;
  if (loading) return <main className="gate-state" aria-live="polite"><div className="gate-loading"><span className="button-spinner" aria-hidden="true" /><p>Memeriksa sesi dan menyiapkan ruang kerja…</p></div></main>;
  return <main className="gate-state"><div className="gate-loading"><p>Mengalihkan ke halaman masuk…</p></div></main>;
}
