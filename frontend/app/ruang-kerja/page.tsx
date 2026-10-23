import type { JSX } from 'react';
import DashboardGate from '../../components/DashboardGate';

export const metadata = {
  title: 'Ruang kerja | Rumah Kecilku Day Care',
  description: 'Ruang kerja sesuai peran pengasuh, dokter, atau orang tua.',
};

export default function WorkspaceRoute(): JSX.Element {
  return <DashboardGate />;
}
