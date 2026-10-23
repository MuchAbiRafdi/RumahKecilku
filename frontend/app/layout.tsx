import type { JSX, ReactNode } from 'react';
import './globals.css';
import './premium.css';

export const metadata = {
  title: 'Rumah Kecilku Day Care | Pengasuhan dengan catatan yang jernih',
  description: 'Ruang kerja sesuai peran untuk aktivitas harian, komunikasi keluarga, dan tinjauan perkembangan anak. Versi uji dengan profil anak contoh.',
};

export default function RootLayout({ children }: Readonly<{ children: ReactNode }>): JSX.Element {
  return (
    <html lang="id" data-scroll-behavior="smooth">
      <body>{children}</body>
    </html>
  );
}
