import type { KpspAge } from './types';

export const KPSP_SCHEDULE_MONTHS = Object.freeze([3, 6, 9, 12, 15, 18, 21, 24, 30, 36, 42, 48, 54, 60, 66, 72]);

function parseIsoDate(value: string | null | undefined): Date | null {
  if (!value || !/^\d{4}-\d{2}-\d{2}$/.test(value)) return null;
  const [year, month, day] = value.split('-').map(Number);
  const parsed = new Date(Date.UTC(year, month - 1, day));
  return parsed.getUTCFullYear() === year && parsed.getUTCMonth() === month - 1 && parsed.getUTCDate() === day
    ? parsed
    : null;
}

function addCalendarMonths(date: Date, months: number): Date {
  const monthIndex = date.getUTCFullYear() * 12 + date.getUTCMonth() + months;
  const year = Math.floor(monthIndex / 12);
  const month = monthIndex - year * 12;
  const lastDay = new Date(Date.UTC(year, month + 1, 0)).getUTCDate();
  return new Date(Date.UTC(year, month, Math.min(date.getUTCDate(), lastDay)));
}

export function todayIsoDate(now: Date = new Date()): string {
  const year = now.getFullYear();
  const month = String(now.getMonth() + 1).padStart(2, '0');
  const day = String(now.getDate()).padStart(2, '0');
  return `${year}-${month}-${day}`;
}

export function calculateAgeAt(
  birthDateValue: string | null | undefined,
  screeningDateValue: string | null | undefined,
): KpspAge | null {
  const birthDate = parseIsoDate(birthDateValue);
  const screeningDate = parseIsoDate(screeningDateValue);
  if (!birthDate || !screeningDate || birthDate > screeningDate) return null;

  let completedMonths = (screeningDate.getUTCFullYear() - birthDate.getUTCFullYear()) * 12
    + screeningDate.getUTCMonth() - birthDate.getUTCMonth();
  let anniversary = addCalendarMonths(birthDate, completedMonths);
  if (anniversary > screeningDate) {
    completedMonths -= 1;
    anniversary = addCalendarMonths(birthDate, completedMonths);
  }
  const remainderDays = Math.floor((screeningDate.getTime() - anniversary.getTime()) / 86400000);
  return {
    completedMonths,
    remainderDays,
    roundedMonths: completedMonths + (remainderDays > 16 ? 1 : 0),
  };
}

export type KpspScreeningMode = 'routine' | 'concern';
export function recommendedScreeningAge(roundedAgeMonths: number, mode: KpspScreeningMode = 'routine'): number | null {
  if (!Number.isInteger(roundedAgeMonths) || roundedAgeMonths < 0 || roundedAgeMonths > 72) return null;
  if (KPSP_SCHEDULE_MONTHS.includes(roundedAgeMonths)) return roundedAgeMonths;
  if (mode === 'routine') return KPSP_SCHEDULE_MONTHS.find((age) => age > roundedAgeMonths) ?? null;
  return [...KPSP_SCHEDULE_MONTHS].reverse().find((age) => age < roundedAgeMonths) ?? null;
}

export function approximateBirthDate(ageMonths: number, baseDate: Date = new Date()): string {
  const date = new Date(Date.UTC(baseDate.getFullYear(), baseDate.getMonth(), baseDate.getDate()));
  const targetMonth = date.getUTCFullYear() * 12 + date.getUTCMonth() - Number(ageMonths || 0);
  const year = Math.floor(targetMonth / 12);
  const month = targetMonth - year * 12;
  const lastDay = new Date(Date.UTC(year, month + 1, 0)).getUTCDate();
  const safeDay = Math.min(date.getUTCDate(), lastDay);
  return `${year}-${String(month + 1).padStart(2, '0')}-${String(safeDay).padStart(2, '0')}`;
}

export function formatAgeDetail(age: KpspAge | null | undefined): string {
  if (!age) return 'Tanggal lahir atau tanggal skrining belum valid.';
  const years = Math.floor(age.completedMonths / 12);
  const months = age.completedMonths % 12;
  const agePart = years ? `${years} tahun ${months} bulan` : `${months} bulan`;
  return `${agePart} ${age.remainderDays} hari · dibulatkan menjadi ${age.roundedMonths} bulan sesuai aturan pemeriksaan`;
}
