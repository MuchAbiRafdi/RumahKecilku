const API_BASE = '/api';
const SESSION_TOKEN_KEY = 'rumah-kecilku-session-token';
let memorySessionToken = '';
let hasAuthoritativeMemorySession = false;

function getSessionToken(): string {
  if (typeof window === 'undefined' || hasAuthoritativeMemorySession) return memorySessionToken;
  try {
    return window.sessionStorage.getItem(SESSION_TOKEN_KEY) || '';
  } catch {
    return memorySessionToken;
  }
}

export function setSessionToken(token: string | null | undefined): void {
  memorySessionToken = token || '';
  // The most recent login/logout must win even if storage is readable but unwritable.
  hasAuthoritativeMemorySession = true;
  if (typeof window === 'undefined') return;
  try {
    if (memorySessionToken) window.sessionStorage.setItem(SESSION_TOKEN_KEY, memorySessionToken);
    else window.sessionStorage.removeItem(SESSION_TOKEN_KEY);
  } catch {
    // Use the current tab's in-memory token when browser storage is unavailable.
  }
}

export function clearSessionToken(): void {
  setSessionToken('');
}

export function hasSessionToken(): boolean {
  return Boolean(getSessionToken());
}

export class ApiError extends Error {
  status: number;
  payload: unknown;

  constructor(message: string, status = 0, payload: unknown = null) {
    super(message);
    this.name = 'ApiError';
    this.status = status;
    this.payload = payload;
  }
}

interface ApiProblem {
  detail?: string | Array<{ msg?: string }>;
}

async function request<T = any>(path: string, options: RequestInit = {}): Promise<T> {
  const normalizedPath = String(path).replace(/^\/+/, '');
  const sessionToken = getSessionToken();
  let response: Response;
  try {
    const headers = new Headers(options.headers);
    if (options.body && !headers.has('Content-Type')) headers.set('Content-Type', 'application/json');
    if (sessionToken && !headers.has('Authorization')) headers.set('Authorization', `Bearer ${sessionToken}`);
    // Keep a namespaced fallback for embedded preview proxies that alter Authorization headers.
    if (sessionToken && !headers.has('X-Rumah-Kecilku-Session')) {
      headers.set('X-Rumah-Kecilku-Session', sessionToken);
    }
    response = await fetch(`${API_BASE}/${normalizedPath}`, {
      ...options,
      headers,
      credentials: 'same-origin',
      cache: 'no-store',
    });
  } catch (error) {
    throw new ApiError('Layanan Rumah Kecilku sedang tidak tersambung. Coba lagi sebentar.', 0, error);
  }

  const text = await response.text();
  let payload: any = null;
  if (text) {
    try {
      payload = JSON.parse(text) as unknown;
    } catch {
      payload = { detail: text };
    }
  }
  const sessionIsStillCurrent = Boolean(sessionToken) && sessionToken === getSessionToken();
  if (sessionIsStillCurrent && (response.status === 401 || (normalizedPath === 'auth/me' && payload?.user == null))) {
    clearSessionToken();
  }
  if (!response.ok) {
    const detail = (payload as ApiProblem | null)?.detail;
    const message = Array.isArray(detail)
      ? detail.map((item) => item.msg || '').filter(Boolean).join(' · ')
      : typeof detail === 'string'
        ? detail
        : `Permintaan gagal (${response.status}).`;
    throw new ApiError(message, response.status, payload);
  }
  return payload as T;
}

export function apiGet<T = any>(path: string): Promise<T> {
  return request<T>(path, { method: 'GET' });
}

export function apiPost<T = any>(path: string, body: unknown): Promise<T> {
  return request<T>(path, { method: 'POST', body: JSON.stringify(body) });
}

export function apiPatch<T = any>(path: string, body: unknown): Promise<T> {
  return request<T>(path, { method: 'PATCH', body: JSON.stringify(body) });
}
