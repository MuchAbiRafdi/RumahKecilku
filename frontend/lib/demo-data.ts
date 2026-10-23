import type { DashboardData, Role } from './types';

export const DEMO_SEED: DashboardData = {
  linkedChildIds: [],
  children: [
    { id: 'a', name: 'Ananda A', ageMonths: 24, birthDate: '2024-10-15', room: 'Ruang Melati', attendance: 'Belum dicatat', checkIn: 'Belum dicatat', note: 'Profil anak contoh.' },
    { id: 'b', name: 'Ananda B', ageMonths: 12, birthDate: '2025-10-15', room: 'Ruang Kenanga', attendance: 'Belum dicatat', checkIn: 'Belum dicatat', note: 'Profil anak contoh.' },
    { id: 'c', name: 'Ananda C', ageMonths: 36, birthDate: '2023-10-15', room: 'Ruang Melati', attendance: 'Belum dicatat', checkIn: 'Belum dicatat', note: 'Profil anak contoh.' },
    { id: 'd', name: 'Ananda D', ageMonths: 48, birthDate: '2022-10-15', room: 'Ruang Anggrek', attendance: 'Belum dicatat', checkIn: 'Belum dicatat', note: 'Profil anak contoh.' },
    { id: 'e', name: 'Ananda E', ageMonths: 24, birthDate: '2024-10-15', room: 'Ruang Kenanga', attendance: 'Belum dicatat', checkIn: 'Belum dicatat', note: 'Profil anak contoh.' }, 
  ],
  activities: [],
  messages: [],
  notifications: [],
  queue: [],
  assessments: [],
  observations: [],
  recommendations: [],
  meals: [],
  developmentReports: [],
  insights: [],
  insightMeta: null,
  modelStatus: null,
  sensor: { connected: false, temperature: null, humidity: null, updatedAt: null, readings: [] },
  consents: {},
  tasks: [],
  audit: [],
};

export const ROLE_LABELS: Record<Role, string> = {
  caregiver: 'Pengasuh',
  doctor: 'Dokter',
  parent: 'Orang tua',
  admin: 'Admin operasional',
};
