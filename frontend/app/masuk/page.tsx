import type { JSX } from 'react';
import AccessPage from '../../components/AccessPage';

export const metadata = {
  title: 'Masuk atau daftar | Rumah Kecilku Day Care',
  description: 'Akses ruang Rumah Kecilku Day Care sesuai peran Anda.',
};

interface AccessRouteProps {
  searchParams: Promise<{ mode?: string | string[] }>;
}

export default async function AccessRoute({ searchParams }: AccessRouteProps): Promise<JSX.Element> {
  const params = await searchParams;
  const initialMode = params.mode === 'register' ? 'register' : 'login';
  return <AccessPage initialMode={initialMode} />;
}
