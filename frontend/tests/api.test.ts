import assert from 'node:assert/strict';
import test from 'node:test';
import { apiGet, apiPatch, apiPost, clearSessionToken, hasSessionToken, setSessionToken } from '../lib/api';

const storage = new Map<string, string>();
const fakeStorage = {
  getItem: (key: string): string | null => storage.get(key) ?? null,
  setItem: (key: string, value: string): void => { storage.set(key, value); },
  removeItem: (key: string): void => { storage.delete(key); },
  clear: (): void => { storage.clear(); },
  key: (index: number): string | null => [...storage.keys()][index] ?? null,
  get length(): number { return storage.size; },
} as Storage;
Object.defineProperty(globalThis, 'window', {
  configurable: true,
  value: { sessionStorage: fakeStorage } as unknown as Window,
});

function jsonResponse(status: number, payload: unknown): Response {
  return {
    status,
    ok: status >= 200 && status < 300,
    text: async () => JSON.stringify(payload),
  } as Response;
}

test('a pre-login auth check cannot erase the token issued by a later login', async () => {
  clearSessionToken();
  let resolveInitialCheck: () => void = () => undefined;
  let initialCheck = true;
  let lastAuthorization: string | null = null;
  let lastPreviewSessionHeader: string | null = null;

  globalThis.fetch = (async (input: RequestInfo | URL, options: RequestInit = {}): Promise<Response> => {
    const url = String(input);
    const headers = new Headers(options.headers);
    lastAuthorization = headers.get('Authorization');
    lastPreviewSessionHeader = headers.get('X-Rumah-Kecilku-Session');
    if (url.endsWith('/auth/me')) {
      if (initialCheck) {
        initialCheck = false;
        return new Promise<Response>((resolve) => {
          resolveInitialCheck = () => resolve(jsonResponse(200, { user: null }));
        });
      }
      return jsonResponse(200, { user: { id: 'demo-user' } });
    }
    if (url.endsWith('/auth/login')) {
      return jsonResponse(200, {
        user: { id: 'demo-user' },
        session_token: 'fresh-session-token',
      });
    }
    throw new Error(`Unexpected API path: ${url}`);
  }) as typeof fetch;

  const preLoginCheck = apiGet<{ user: null }>('auth/me');
  const login = await apiPost<{ user: { id: string }; session_token: string }>('auth/login', {
    email: 'demo@example.test',
    password: 'demo',
  });
  setSessionToken(login.session_token);
  resolveInitialCheck();
  await preLoginCheck;

  assert.equal(storage.get('rumah-kecilku-session-token'), 'fresh-session-token');
  const session = await apiGet<{ user: { id: string } }>('auth/me');
  assert.equal(lastAuthorization, 'Bearer fresh-session-token');
  assert.equal(lastPreviewSessionHeader, 'fresh-session-token');
  assert.equal(session.user.id, 'demo-user');
  clearSessionToken();
});

test('a fresh login token wins over a stale readable but unwritable sessionStorage value', async () => {
  const previousWindow = globalThis.window;
  const staleButUnwritableStorage = {
    getItem: (): string => 'stale-session-token',
    setItem: (): void => { throw new Error('storage write blocked'); },
    removeItem: (): void => { throw new Error('storage removal blocked'); },
  } as unknown as Storage;
  Object.defineProperty(globalThis, 'window', {
    configurable: true,
    value: { sessionStorage: staleButUnwritableStorage } as unknown as Window,
  });

  clearSessionToken();
  let loginAuthorization: string | null = null;
  let sessionAuthorization: string | null = null;
  let sessionFallbackHeader: string | null = null;
  globalThis.fetch = (async (input: RequestInfo | URL, options: RequestInit = {}): Promise<Response> => {
    const url = String(input);
    const headers = new Headers(options.headers);
    if (url.endsWith('/auth/login')) {
      loginAuthorization = headers.get('Authorization');
      return jsonResponse(200, {
        user: { id: 'demo-caregiver' },
        session_token: 'fresh-session-token',
      });
    }
    if (url.endsWith('/auth/me')) {
      sessionAuthorization = headers.get('Authorization');
      sessionFallbackHeader = headers.get('X-Rumah-Kecilku-Session');
      return jsonResponse(200, { user: { id: 'demo-caregiver' } });
    }
    throw new Error(`Unexpected API path: ${url}`);
  }) as typeof fetch;

  const login = await apiPost<{ user: { id: string }; session_token: string }>('auth/login', {
    email: 'pengasuh@rumahkecilku.demo',
    password: 'RK-Preview-2026!',
  });
  setSessionToken(login.session_token);
  const session = await apiGet<{ user: { id: string } }>('auth/me');

  assert.equal(loginAuthorization, null, 'a stale token must not be attached to the new login');
  assert.equal(sessionAuthorization, 'Bearer fresh-session-token');
  assert.equal(sessionFallbackHeader, 'fresh-session-token');
  assert.equal(session.user.id, login.user.id);

  Object.defineProperty(globalThis, 'window', {
    configurable: true,
    value: previousWindow,
  });
  clearSessionToken();
});

test('profile updates use PATCH with the current authenticated session', async () => {
  clearSessionToken();
  setSessionToken('profile-session-token');
  let requestMethod = '';
  let requestBody = '';
  let requestAuthorization: string | null = null;
  globalThis.fetch = (async (_input: RequestInfo | URL, options: RequestInit = {}): Promise<Response> => {
    requestMethod = options.method || '';
    requestBody = String(options.body || '');
    requestAuthorization = new Headers(options.headers).get('Authorization');
    return jsonResponse(200, { child: { id: 'child-demo', room: 'Ruang Melati' } });
  }) as typeof fetch;

  const response = await apiPatch<{ child: { id: string; room: string } }>('children/child-demo', { room: 'Ruang Melati' });
  assert.equal(requestMethod, 'PATCH');
  assert.deepEqual(JSON.parse(requestBody), { room: 'Ruang Melati' });
  assert.equal(requestAuthorization, 'Bearer profile-session-token');
  assert.equal(response.child.room, 'Ruang Melati');
  clearSessionToken();
});

test('background refresh can check whether the current tab still has a session', () => {
  clearSessionToken();
  assert.equal(hasSessionToken(), false);
  setSessionToken('active-session');
  assert.equal(hasSessionToken(), true);
  clearSessionToken();
  assert.equal(hasSessionToken(), false);
});
