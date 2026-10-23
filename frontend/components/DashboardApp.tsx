'use client';

import React, { useEffect, useMemo, useRef, useState } from 'react';
import { DEMO_SEED, ROLE_LABELS } from '../lib/demo-data';
import { Icon } from './icons';
import KpspWorkspace from './kpsp/KpspWorkspace';
import { ApiError, apiGet, apiPatch, apiPost, hasSessionToken } from '../lib/api';
import { approximateBirthDate, calculateAgeAt, todayIsoDate } from '../lib/kpsp-age';
import type { AuthUser, DashboardData, DashboardRecord, IconName, Role } from '../lib/types';

type LooseProps = Record<string, any>;
interface NavItem { id: string; label: string; icon: IconName }
interface NavGroup { group: string; items: NavItem[] }

const STORE_KEY = 'rumah-kecilku-dashboard-v3';
const copySeed = (): DashboardData => JSON.parse(JSON.stringify(DEMO_SEED)) as DashboardData;

function loadDemo(storageKey: string): DashboardData {
  const seed = copySeed();
  try {
    const saved = window.localStorage.getItem(storageKey);
    if (!saved) return seed;
    const parsed = JSON.parse(saved);
    const children = (Array.isArray(parsed.children) ? parsed.children : seed.children).map((child) => ({
      ...child,
      birthDate: child.birthDate || approximateBirthDate(child.ageMonths),
      attendance: 'Belum dicatat',
      checkIn: 'Belum dicatat',
      checkOut: 'Belum dicatat',
      pickupPersonName: '',
    }));
    // Catatan operasional dibaca ulang dari layanan penyimpanan, bukan dari cache lama di browser.
    return { ...seed, children, consents: parsed.consents || {} };
  } catch {
    return seed;
  }
}

const NAV: Record<Role, NavGroup[]> = {
  caregiver: [
    { group: 'SmartDayCare AI', items: [
      { id: 'home', label: 'Ringkasan harian', icon: 'home' },
      { id: 'activities', label: 'Catatan harian', icon: 'activity' },
      { id: 'sensors', label: 'Suhu & kelembapan', icon: 'sensor' },
    ] },
    { group: 'Skrining & perkembangan anak', items: [
      { id: 'development', label: 'Skrining & perkembangan', icon: 'growth' },
    ] },
    { group: 'Operasional', items: [
      { id: 'children', label: 'Anak & jadwal', icon: 'child' },
    ] },
    { group: 'Komunikasi & data', items: [
      { id: 'messages', label: 'Pesan keluarga', icon: 'message' },
      { id: 'reports', label: 'Laporan shift', icon: 'report' },
      { id: 'privacy', label: 'Persetujuan & jejak', icon: 'privacy' },
    ] },
  ],
  doctor: [
    { group: 'SmartDayCare AI', items: [
      { id: 'activities', label: 'Catatan harian', icon: 'activity' },
    ] },
    { group: 'Skrining & perkembangan anak', items: [
      { id: 'development', label: 'Skrining & perkembangan', icon: 'growth' },
      { id: 'queue', label: 'Tinjauan dokter', icon: 'review' },
      { id: 'kpsp', label: 'Input KPSP', icon: 'clipboard' },
    ] },
    { group: 'Ruang dokter', items: [
      { id: 'home', label: 'Beranda dokter', icon: 'home' },
      { id: 'reports', label: 'Laporan', icon: 'report' },
      { id: 'messages', label: 'Pesan & kontak', icon: 'message' },
      { id: 'privacy', label: 'Persetujuan & audit', icon: 'privacy' },
    ] },
  ],
  parent: [
    { group: 'SmartDayCare AI', items: [
      { id: 'activities', label: 'Kegiatan yang dibagikan', icon: 'activity' },
    ] },
    { group: 'Skrining & perkembangan anak', items: [
      { id: 'development', label: 'Skrining & perkembangan', icon: 'growth' },
    ] },
    { group: 'Anak & daycare', items: [
      { id: 'home', label: 'Ringkasan hari ini', icon: 'home' },
      { id: 'messages', label: 'Pesan daycare', icon: 'message' },
      { id: 'reports', label: 'Laporan anak', icon: 'report' },
      { id: 'privacy', label: 'Izin & data saya', icon: 'privacy' },
    ] },
  ],
  admin: [
    { group: 'Operasional daycare', items: [
      { id: 'home', label: 'Ringkasan operasional', icon: 'home' },
      { id: 'children', label: 'Daftar anak', icon: 'child' },
      { id: 'sensors', label: 'Sensor ruang', icon: 'sensor' },
    ] },
  ],
};

const TITLES: Record<string, string> = {
  home: 'Ringkasan hari ini',
  activities: 'Catatan harian · SmartDayCare AI',
  meals: 'Menu & nilai gizi · SmartDayCare AI',
  children: 'Anak & jadwal',
  development: 'Skrining & perkembangan anak',
  sensors: 'Kondisi ruang · SmartDayCare AI',
  recommendations: 'Rencana stimulasi',
  messages: 'Pesan keluarga',
  reports: 'Laporan',
  privacy: 'Persetujuan & jejak data',
  queue: 'Antrean tinjauan dokter',
  kpsp: 'Input KPSP',
};

const DEVELOPMENT_ASPECTS: Array<{ id: string; label: string; color: string; icon: IconName }> = [
  { id: 'gross', label: 'Motorik kasar', color: 'coral', icon: 'growth' },
  { id: 'fine', label: 'Motorik halus', color: 'sage', icon: 'growth' },
  { id: 'language', label: 'Bahasa', color: 'plum', icon: 'book' },
  { id: 'social', label: 'Sosial-emosional', color: 'gold', icon: 'child' },
];

const dateLabel = new Intl.DateTimeFormat('id-ID', {
  weekday: 'long', day: 'numeric', month: 'long', year: 'numeric', timeZone: 'Asia/Jakarta',
}).format(new Date());
const shortDateLabel = new Intl.DateTimeFormat('id-ID', {
  day: '2-digit', month: 'short', year: 'numeric', timeZone: 'Asia/Jakarta',
}).format(new Date());

function uid(prefix = 'item'): string {
  return `${prefix}-${Date.now()}-${Math.floor(Math.random() * 900 + 100)}`;
}

function shiftIsoDateByMonths(isoDate: string, months: number): string {
  const [year, month, day] = isoDate.split('-').map(Number);
  const target = new Date(Date.UTC(year, month - 1 + months, 1));
  const lastDay = new Date(Date.UTC(target.getUTCFullYear(), target.getUTCMonth() + 1, 0)).getUTCDate();
  const safeDay = Math.min(day, lastDay);
  return `${target.getUTCFullYear()}-${String(target.getUTCMonth() + 1).padStart(2, '0')}-${String(safeDay).padStart(2, '0')}`;
}

function addAudit(data: DashboardData, event: string, childId: string, source: string): DashboardRecord[] {
  return [{ id: uid('audit'), event, actor: ROLE_LABELS[data.__role || 'caregiver'], childId, time: new Intl.DateTimeFormat('en-GB', { hour: '2-digit', minute: '2-digit', hourCycle: 'h23', timeZone: 'Asia/Jakarta' }).format(new Date()), source }, ...(data.audit || [])].slice(0, 30);
}

function mapNotification(record: DashboardRecord): DashboardRecord {
  return {
    id: record.id,
    childId: record.child_id ?? null,
    category: record.category,
    title: record.title,
    body: record.body,
    relatedActivityId: record.related_activity_id,
    relatedMessageId: record.related_message_id,
    dueAt: record.due_at,
    createdAt: record.created_at,
    readAt: record.read_at,
    completedAt: record.completed_at,
  };
}

interface ButtonProps extends Omit<React.ButtonHTMLAttributes<HTMLButtonElement>, 'type' | 'size'> {
  variant?: string;
  size?: string;
  icon?: IconName;
  type?: React.ButtonHTMLAttributes<HTMLButtonElement>['type'];
  children: React.ReactNode;
}

function Button({ children, variant = 'primary', size = 'normal', icon, onClick, type = 'button', className = '', disabled = false, ...props }: ButtonProps): React.JSX.Element {
  return (
    <button type={type} className={`btn btn-${variant} btn-${size} ${className}`} onClick={onClick} disabled={disabled} {...props}>
      {icon && <Icon name={icon} size={size === 'small' ? 16 : 18} />}
      <span>{children}</span>
    </button>
  );
}

function Pill({ children, tone = 'neutral', dot = false, className = '' }: LooseProps): React.JSX.Element {
  return <span className={`pill pill-${tone} ${className}`}>{dot && <i aria-hidden="true" />}{children}</span>;
}

function PageTitle({ eyebrow, title, description, action }: LooseProps): React.JSX.Element {
  return (
    <div className="page-title-row">
      <div>
        {eyebrow && <div className="eyebrow">{eyebrow}</div>}
        <h1>{title}</h1>
        {description && <p className="page-description">{description}</p>}
      </div>
      {action && <div className="page-title-action">{action}</div>}
    </div>
  );
}

function CardTitle({ eyebrow, title, action }: LooseProps): React.JSX.Element {
  return (
    <div className="card-title-row">
      <div>
        {eyebrow && <div className="eyebrow">{eyebrow}</div>}
        <h2>{title}</h2>
      </div>
      {action}
    </div>
  );
}

function Sparkline({ values = [20, 31, 27, 42, 38, 54, 61], color = '#b86650', fillId = 'spark-fill' }: { values?: number[]; color?: string; fillId?: string }): React.JSX.Element {
  const points = values.map((value, index) => `${(index / (values.length - 1)) * 100},${38 - (value / 100) * 30}`).join(' ');
  const first = points.split(' ')[0].split(',');
  const last = points.split(' ').at(-1).split(',');
  const area = `M ${first[0]} 40 L ${points.replaceAll(' ', ' L ')} L ${last[0]} 40 Z`;
  return (
    <svg className="sparkline" viewBox="0 0 100 42" role="img" aria-label="Grafik tren ilustratif">
      <defs><linearGradient id={fillId} x1="0" x2="0" y1="0" y2="1"><stop offset="0" stopColor={color} stopOpacity=".2"/><stop offset="1" stopColor={color} stopOpacity="0"/></linearGradient></defs>
      <path d={area} fill={`url(#${fillId})`} />
      <polyline points={points} fill="none" stroke={color} strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round" />
      <circle cx={last[0]} cy={last[1]} r="2.6" fill={color} />
    </svg>
  );
}

function StatCard({ label, value, note, icon, tone = 'plain', trend, onClick }: LooseProps): React.JSX.Element {
  const content = (
    <>
      <div className="stat-top"><span className={`stat-icon stat-icon-${tone}`}><Icon name={icon} size={18} /></span><span className="stat-label">{label}</span></div>
      <div className="stat-value-row"><strong>{value}</strong>{trend && <span className="stat-trend">{trend}</span>}</div>
      <div className="stat-bottom"><span>{note}</span></div>
    </>
  );
  return onClick ? <button className={`stat-card stat-card-${tone}`} onClick={onClick}>{content}</button> : <div className={`stat-card stat-card-${tone}`}>{content}</div>;
}

function EmptyState({ icon = 'activity', title, detail, action }: LooseProps): React.JSX.Element {
  return (
    <div className="empty-state">
      <div className="empty-icon"><Icon name={icon} size={22} /></div>
      <h3>{title}</h3>
      <p>{detail}</p>
      {action}
    </div>
  );
}

function InsightActionList({ title, items }: { title: string; items?: string[] }): React.JSX.Element | null {
  if (!items?.length) return null;
  return <div className="insight-action-list"><strong>{title}</strong><ul>{items.map((item, index) => <li key={`${title}-${index}`}>{item}</li>)}</ul></div>;
}

function LocalInsightCards({ insights = [], role }: { insights: DashboardRecord[]; role: Role }): React.JSX.Element {
  return <div className="local-insight-grid local-insight-grid-guidance">{insights.map((item) => <article className="local-guidance-card" key={item.aspect}>
    <div className="local-guidance-top"><Pill tone={item.observation_count ? 'neutral' : 'gold'}>{item.aspect}</Pill><small>{item.observation_count} catatan · {item.recorded_days || 0} hari</small></div>
    <strong className="local-guidance-status">{item.status}</strong>
    <div className="local-evidence-summary"><small>Bukti yang dipakai</small><p>{item.evidence_summary}</p></div>
    {item.model_activity_idea && <div className="ml-demo-activity-idea"><div className="ml-demo-activity-meta"><Pill tone="plum">Ide aktivitas · ML demo</Pill><small>{item.model_activity_idea.training_examples} skenario sintetis</small></div><p>{item.model_activity_idea.text}</p><small>Model hanya memilih ide kegiatan umum. Data mock; belum divalidasi klinis dan bukan penilaian kemampuan.</small></div>}
    <InsightActionList title="Langkah untuk pengasuh" items={item.caregiver_actions} />
    {role === 'doctor' && <InsightActionList title="Titik tinjauan dokter" items={item.doctor_actions} />}
    <InsightActionList title="Data berikutnya yang membantu" items={item.data_needed} />
  </article>)}</div>;
}

function PersonalizedStimulation({ data, child, onFeedback, onStartActivity, readOnly = false }: LooseProps): React.JSX.Element | null {
  const bundle = data?.personalized_stimulation;
  const recommendations = bundle?.recommendations || [];
  const [selectedOutcome, setSelectedOutcome] = useState<Record<string, string>>({});
  const [notes, setNotes] = useState<Record<string, string>>({});
  const [saving, setSaving] = useState('');
  if (!bundle || !child) return null;
  const saveFeedback = async (activityId: string) => {
    const outcome = selectedOutcome[activityId] || 'belum_dicoba';
    setSaving(activityId);
    const saved = await onFeedback(child.id, { activity_id: activityId, outcome, duration_minutes: null, note: notes[activityId] || '' });
    if (saved) {
      setSelectedOutcome((current) => ({ ...current, [activityId]: '' }));
      setNotes((current) => ({ ...current, [activityId]: '' }));
    }
    setSaving('');
  };
  return <section className="panel personalized-stimulation-panel">
    <CardTitle eyebrow="Katalog aktivitas · v1" title="Saran stimulasi yang lebih personal" action={<Pill tone="plum">{bundle.catalog_count} aktivitas</Pill>} />
    <p className="page-description">Saran disaring berdasarkan usia, aspek yang belum banyak terdokumentasi, dan feedback kegiatan sebelumnya. Ini ide aktivitas nonklinis, bukan penilaian kemampuan.</p>
    <div className="stimulation-card-grid">{recommendations.map((item: DashboardRecord) => <article className="stimulation-card" key={item.id}>
      <div className="stimulation-card-top"><Pill tone="warm">{item.aspect}</Pill><small>{item.duration_minutes} menit · usia {item.min_age_months}–{item.max_age_months} bln</small></div>
      <h3>{item.title}</h3><p>{item.goal}</p>
      <div className="stimulation-reason"><strong>Kenapa disarankan</strong><span>{item.reason}</span></div>
      <div className="stimulation-meta"><strong>Alat</strong><span>{item.materials.join(' · ')}</span><strong>Langkah</strong><ol>{item.steps.map((step: string) => <li key={step}>{step}</li>)}</ol><strong>Keamanan</strong><span>{item.safety}</span></div>
      {!readOnly && <div className="stimulation-feedback"><div className="button-row"><Button size="small" variant="outline" icon="activity" onClick={() => onStartActivity(item.title)}>Catat kegiatan</Button></div><label className="field"><span>Hasil percobaan</span><select value={selectedOutcome[item.id] || 'belum_dicoba'} onChange={(event) => setSelectedOutcome((current) => ({ ...current, [item.id]: event.target.value }))}><option value="belum_dicoba">Belum dicoba</option><option value="tertarik">Anak tertarik</option><option value="sebagian">Mencoba sebagian</option><option value="menolak">Belum tertarik / menolak</option></select></label><label className="field"><span>Catatan singkat (opsional)</span><input value={notes[item.id] || ''} onChange={(event) => setNotes((current) => ({ ...current, [item.id]: event.target.value }))} placeholder="Contoh: perlu bantuan di awal" maxLength={500} /></label><Button size="small" icon="check" onClick={() => saveFeedback(item.id)} disabled={saving === item.id}>{saving === item.id ? 'Menyimpan…' : 'Simpan feedback'}</Button></div>}
    </article>)}</div>
    {data.stimulation_feedback?.length > 0 && <details className="stimulation-history"><summary>Riwayat feedback aktivitas ({data.stimulation_feedback.length})</summary><div className="stimulation-history-list">{data.stimulation_feedback.slice(0, 8).map((entry: DashboardRecord) => <div key={entry.id}><strong>{entry.activity_title || entry.activity_id}</strong><span>{entry.outcome === 'tertarik' ? 'Anak tertarik' : entry.outcome === 'sebagian' ? 'Mencoba sebagian' : entry.outcome === 'menolak' ? 'Belum tertarik / menolak' : 'Belum dicoba'} · {new Intl.DateTimeFormat('id-ID', { dateStyle: 'medium', timeZone: 'Asia/Jakarta' }).format(new Date(entry.created_at))}</span>{entry.note && <small>{entry.note}</small>}</div>)}</div></details>}
    <div className="quarterly-analytics-note"><Icon name="info" size={15} /><span>{bundle.method} {bundle.boundary}</span></div>
  </section>;
}

function SyntheticDemoNotice({ insightMeta }: LooseProps): React.JSX.Element | null {
  if (!insightMeta?.synthetic_observation_count) return null;
  return <div className="synthetic-demo-banner" role="note"><Icon name="info" size={17} /><span><strong>Data sintetis untuk demo saja</strong><small>{insightMeta.synthetic_demo_notice || `${insightMeta.synthetic_observation_count} catatan demo sintetis. Jangan gunakan untuk keputusan klinis atau pelatihan model.`}</small></span></div>;
}

function InsightLoadMessage({ status, error, onRetry }: LooseProps): React.JSX.Element | null {
  if (status === 'loading') return <EmptyState icon="refresh" title="Memuat saran lokal…" detail="Sistem sedang mengambil catatan untuk profil yang dipilih." />;
  if (status === 'error') return <EmptyState icon="info" title="Saran belum dapat dimuat" detail={error || 'Periksa koneksi atau akses akun, lalu coba lagi.'} action={<Button size="small" variant="outline" onClick={onRetry}>Coba lagi</Button>} />;
  return null;
}

function ModalShell({ title, subtitle, onClose, children, width = 'medium' }: LooseProps): React.JSX.Element {
  const dialogRef = useRef<HTMLElement | null>(null);
  useEffect(() => {
    const oldOverflow = document.body.style.overflow;
    document.body.style.overflow = 'hidden';
    dialogRef.current?.querySelector<HTMLElement>('button, input, select, textarea')?.focus();
    const handleKeys = (event: KeyboardEvent) => {
      if (event.key === 'Escape') onClose();
      if (event.key === 'Tab' && dialogRef.current) {
        const focusable = [...dialogRef.current.querySelectorAll<HTMLElement>('button:not([disabled]), input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])')];
        if (!focusable.length) return;
        const first = focusable[0];
        const last = focusable[focusable.length - 1];
        if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last.focus(); }
        else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first.focus(); }
      }
    };
    window.addEventListener('keydown', handleKeys);
    return () => { document.body.style.overflow = oldOverflow; window.removeEventListener('keydown', handleKeys); };
  }, [onClose]);
  return (
    <div className="modal-backdrop" onMouseDown={(event) => { if (event.target === event.currentTarget) onClose(); }}>
      <section ref={dialogRef} className={`modal modal-${width}`} role="dialog" aria-modal="true" aria-labelledby="modal-title" tabIndex={-1}>
        <div className="modal-head">
          <div><h2 id="modal-title">{title}</h2>{subtitle && <p>{subtitle}</p>}</div>
          <button className="icon-button modal-close" onClick={onClose} aria-label="Tutup dialog"><Icon name="close" /></button>
        </div>
        <div className="modal-body">{children}</div>
      </section>
    </div>
  );
}

function AdminHome({ data, onGo }: LooseProps): React.JSX.Element {
  const activeChildren = data.children.filter((child) => child.status !== 'inactive');
  const presentCount = activeChildren.filter((child) => child.attendance === 'Hadir').length;
  return <>
    <PageTitle eyebrow="Admin operasional · akses minimum" title="Ringkasan operasional daycare" description="Kelola roster, kehadiran, dan kondisi ruang. Catatan klinis serta jawaban KPSP tidak termasuk akses admin bawaan." />
    <div className="stats-grid">
      <StatCard label="Profil aktif" value={activeChildren.length} note="Dalam daftar daycare ini" icon="child" tone="coral" onClick={() => onGo('children')} />
      <StatCard label="Hadir hari ini" value={presentCount} note="Dari kehadiran tersimpan" icon="check" tone="sage" onClick={() => onGo('children')} />
    </div>
    <section className="panel" style={{ marginTop: 20 }}>
      <CardTitle eyebrow="Ruang kerja admin" title="Pengelolaan operasional" />
      <p className="page-description">Informasi yang ditampilkan di sini berasal dari roster, kehadiran, dan katalog menu. Data kesehatan atau perkembangan tidak disalin ke ringkasan admin.</p>
      <div className="button-row" style={{ marginTop: 16 }}>
        <Button variant="outline" icon="child" onClick={() => onGo('children')}>Buka daftar anak</Button>
      </div>
    </section>
  </>;
}

function CaregiverHome({ data, onGo, onNewActivity, onOpenActivity, onOpenReview, onToggleTask }: LooseProps) {
  const present = data.children.filter((child) => child.attendance === 'Hadir').length;
  const latest = data.activities.slice(0, 4);
  const todayActivities = data.activities.filter((item) => item.createdAt === shortDateLabel);
  const todayCount = (category: string) => todayActivities.filter((item) => category === 'Makan & minum' ? ['Makan & minum', 'Makan', 'Minum'].includes(item.category) : item.category === category).length;
  const todayCategories = [['makan & minum', todayCount('Makan & minum')], ['istirahat', todayCount('Tidur')], ['bermain/stimulasi', todayCount('Bermain') + todayCount('Belajar') + todayCount('Stimulasi')]].filter(([, count]) => count > 0).map(([label, count]) => `${count} ${label}`).join(' · ');
  const localSummary = todayActivities.length ? `Tersimpan ${todayActivities.length} catatan (${todayCategories || 'kategori lain'}); ${todayActivities.filter((item) => !item.shared).length} belum dibagikan.` : 'Belum ada catatan hari ini; ringkasan menunggu data yang tersimpan.';
  const specialCases = data.activities.filter((item) => item.createdAt === shortDateLabel && (item.category === 'Kejadian' || item.mood === 'Membutuhkan dukungan'));
  const pendingChildren = data.children.filter((child) => child.attendance === 'Hadir' && !todayActivities.some((item) => item.childId === child.id));
  const weeklyActivities = data.activities.filter((item) => item.createdAtIso ? Date.now() - Date.parse(item.createdAtIso) <= 7 * 24 * 60 * 60 * 1000 : item.createdAt === shortDateLabel);
  const repeatedAttention = Object.entries(specialCases.reduce((counts, item) => ({ ...counts, [item.childId]: (counts[item.childId] || 0) + 1 }), {} as Record<string, number>)).filter(([, count]) => Number(count) > 1);
  const dailySummary = todayActivities.length ? `Hari ini tercatat ${todayActivities.length} kegiatan untuk ${new Set(todayActivities.map((item) => item.childId)).size} anak.` : 'Belum ada cukup catatan untuk membuat ringkasan.';
  const hasSensorReading = Number.isFinite(data.sensor?.temperature) && Number.isFinite(data.sensor?.humidity);
  return (
    <>
      <PageTitle eyebrow={dateLabel} title="Ruang kerja pengasuh" description="Selesaikan catatan penting dengan beberapa klik." action={<Button variant="soft" icon="calendar" onClick={() => onGo('children')}>Lihat jadwal anak</Button>} />
      <div className="demo-data-banner"><Icon name="info" size={16} /><span><strong>Simulasi aktif:</strong> 16 profil sintetis dari usia 3 sampai 72 bulan tersedia untuk menguji alur KPSP, analitik, dan saran stimulasi.</span></div>
      <section className="care-hero gradient-warm">
        <div className="care-hero-copy">
          <Pill tone="warm" dot>Kegiatan di Rumah Kecilku</Pill>
          <h2>Mulai dari kegiatan yang sudah selesai.</h2>
          <p>Pilih satu kegiatan untuk semua anak yang hadir. Catatan khusus hanya dibuat jika ada anak yang perlu diperhatikan.</p>
          <div className="hero-actions"><Button icon="plus" onClick={onNewActivity}>Catat kegiatan kelas</Button><Button variant="outline" onClick={() => onGo('activities')}>Buka catatan</Button></div>
        </div>
        <div className="care-hero-art" aria-hidden="true">
          <div className="hero-orbit orbit-one" /><div className="hero-orbit orbit-two" />
          <div className="hero-note hero-note-main"><span className="hero-note-mark"><Icon name="book" size={19} /></span><div><small>CATATAN TERBARU</small><strong>{latest?.[0]?.title || 'Belum ada catatan'}</strong><span>{latest?.[0] ? `${latest[0].time} · ${latest[0].shared ? 'dibagikan' : 'belum dibagikan'}` : 'Catat sesi sesudah kegiatan'}</span></div>{latest?.[0]?.shared && <span className="hero-note-check"><Icon name="check" size={15} /></span>}</div>
          <div className="hero-note hero-note-mini"><span className="mini-icon mini-sage"><Icon name="drop" size={17} /></span><div><strong>Kondisi ruang</strong><small>Belum ada alat terhubung</small></div></div>
          <div className="hero-note hero-note-bubble"><span>{present}</span><small>hadir</small></div>
        </div>
      </section>
      <div className="stat-grid four">
        <StatCard label="Anak hadir" value={`${present}/${data.children.length}`} note="profil anak contoh" icon="child" tone="coral" trend="hari ini" onClick={() => onGo('children')} />
        <StatCard label="Sesi tercatat" value={data.activities.length} note="semua kategori kegiatan" icon="activity" tone="sage" trend="catatan" onClick={() => onGo('activities')} />
        <StatCard label="Tinjauan dokter" value={data.queue.filter((item) => !item.reviewed).length} note="hasil menunggu tinjauan dokter" icon="review" tone="plum" trend="lintas peran" onClick={() => onGo('development')} />
        <StatCard label="Catatan belum dibagikan" value={data.activities.filter((item) => !item.shared).length} note="periksa sebelum akhir sesi" icon="message" tone="gold" trend="tindak lanjut" onClick={() => onGo('activities')} />
      </div>
      <section className="caregiver-action-grid">
        <section className="panel caregiver-priority-panel"><CardTitle eyebrow="Perlu perhatian" title="Kasus dan catatan tertunda" action={<Pill tone={specialCases.length ? 'coral' : 'sage'}>{specialCases.length} kasus</Pill>} />
          {specialCases.length ? <div className="caregiver-priority-list">{specialCases.slice(0, 4).map((item) => <button className="caregiver-priority-row" key={item.id} onClick={() => onOpenActivity(item)}><span className="priority-alert-icon">!</span><span><strong>{item.childName || data.children.find((child) => child.id === item.childId)?.name || 'Anak'}</strong><small>{item.title} · {item.note}</small></span><Icon name="chevron" size={16} /></button>)}{repeatedAttention.length > 0 && <small className="caregiver-pattern-note"><Icon name="spark" size={14} />Pola perhatian berulang terdeteksi pada {repeatedAttention.length} profil hari ini. Periksa catatan dan konsultasikan ke dokter bila diperlukan.</small>}</div> : <EmptyState icon="check" title="Tidak ada kasus khusus" detail="Kasus sakit, mood kurang baik, atau kejadian akan muncul di sini." />}
          {pendingChildren.length > 0 && <button className="caregiver-pending-note" onClick={onNewActivity}><Icon name="info" size={15} />{pendingChildren.length} anak hadir belum punya catatan hari ini · Catat sekarang</button>}
        </section>
        <section className="panel caregiver-ai-summary"><CardTitle eyebrow="Ringkasan catatan" title="Ringkasan hari ini" action={<Pill tone="plum">Bantuan lokal</Pill>} /><p className="caregiver-ai-lead">{dailySummary}</p><div className="caregiver-ai-metrics"><div><strong>{weeklyActivities.length}</strong><small>catatan 2 hari</small></div><div><strong>{specialCases.length}</strong><small>perlu diperiksa</small></div><div><strong>{todayActivities.filter((item) => item.shared).length}</strong><small>sudah dibagikan</small></div></div><small className="caregiver-ai-note">Ringkasan hanya mengelompokkan catatan tersimpan; bukan penilaian perkembangan.</small></section>
      </section>
      <div className="dashboard-grid dashboard-grid-main">
        <section className="panel panel-large">
          <CardTitle eyebrow="Alur hari ini" title="Catatan aktivitas terbaru" action={<button className="text-link" onClick={() => onGo('activities')}>Lihat semua <Icon name="arrow" size={15} /></button>} />
          {latest.length ? <div className="activity-feed compact-feed">
            {latest.map((item, index) => {
              const child = data.children.find((entry) => entry.id === item.childId);
              return <button className="feed-row" key={item.id} onClick={() => onOpenActivity(item)}>
                <span className={`feed-symbol feed-symbol-${index % 4}`}><Icon name={item.category === 'Makan' ? 'activity' : item.category === 'Tidur' ? 'clock' : item.category === 'Stimulasi' ? 'book' : 'child'} size={17} /></span>
                <span className="feed-main"><strong>{item.title}</strong><small>{child?.name || 'Profil anak' } · {item.session} · {item.time}</small></span>
                <span className="feed-right"><Pill tone={item.shared ? 'sage' : 'neutral'}>{item.shared ? 'Dibagikan' : 'Belum dibagikan'}</Pill><Icon name="chevron" size={16} /></span>
              </button>;
            })}
          </div> : <EmptyState title="Belum ada kegiatan yang dicatat" detail="Catatan akan muncul setelah pengasuh menyimpan kegiatan." action={<Button size="small" onClick={onNewActivity}>Catat kegiatan</Button>} />}
        </section>
        <section className="panel task-panel">
          <CardTitle eyebrow="Daftar cek" title="Sebelum pergantian sesi" />
          <div className="task-list">
            {data.tasks.length ? data.tasks.map((task) => <label className={`task-row ${task.done ? 'is-done' : ''}`} key={task.id}>
              <input type="checkbox" checked={task.done} onChange={() => onToggleTask(task.id)} />
              <span className="task-copy"><strong>{task.label}</strong><small>{task.detail}</small></span>
            </label>) : <EmptyState title="Belum ada tugas" detail="Tugas yang ditambahkan tim akan muncul di sini." />}
          </div>
          <div className="task-footer"><Icon name="info" size={15} /><span>Gunakan daftar ini untuk hal yang masih perlu ditindaklanjuti.</span></div>
        </section>
      </div>
      <section className="split-panels smartdaycare-overview">
        <div className="panel sensor-summary-card gradient-cool">
          <div className="sensor-summary-top"><span className="summary-icon"><Icon name="sensor" size={19} /></span><Pill tone={data.sensor.fresh ? 'sage' : hasSensorReading ? 'gold' : 'neutral'} dot>{data.sensor.fresh ? 'Data langsung' : hasSensorReading ? 'Data terakhir' : 'Menunggu sensor'}</Pill></div>
          <div className="sensor-summary-values"><div><strong>{hasSensorReading ? `${data.sensor.temperature.toFixed(1)}°` : '--'}</strong><small>Suhu ruang</small></div><div className="sensor-divider" /><div><strong>{hasSensorReading ? `${data.sensor.humidity.toFixed(1)}%` : '--'}</strong><small>Kelembapan</small></div></div>
          <div className="sensor-summary-bottom"><span>{hasSensorReading ? `${data.sensor.roomId || 'Ruang daycare'} · ${data.sensor.updatedAt || 'waktu tidak tersedia'}` : 'Nilai akan tampil setelah perangkat mengirim data.'}</span><button className="text-link" onClick={() => onGo('sensors')}>Detail sensor <Icon name="arrow" size={15} /></button></div>
        </div>
        <section className="panel class-recap-home">
          <CardTitle eyebrow="SmartDayCare · rekap kelas" title="Catatan tersimpan hari ini" action={<button className="text-link" onClick={() => onGo('activities')}>Buka catatan <Icon name="arrow" size={14} /></button>} />
          <div className="class-recap-grid"><div><span className="recap-icon recap-coral"><Icon name="child" size={16} /></span><strong>{present}/{data.children.length}</strong><small>anak hadir</small></div><div><span className="recap-icon recap-sage"><Icon name="activity" size={16} /></span><strong>{todayCount('Makan') + todayCount('Minum')}</strong><small>makan & minum</small></div><div><span className="recap-icon recap-plum"><Icon name="clock" size={16} /></span><strong>{todayCount('Tidur')}</strong><small>istirahat</small></div><div><span className="recap-icon recap-gold"><Icon name="book" size={16} /></span><strong>{todayCount('Stimulasi') + todayCount('Bermain') + todayCount('Belajar')}</strong><small>bermain & stimulasi</small></div><div><span className="recap-icon recap-neutral"><Icon name="message" size={16} /></span><strong>{todayActivities.filter((item) => !item.shared).length}</strong><small>belum dibagikan</small></div></div>
          <div className="class-recap-foot"><Icon name="info" size={14} />Dihitung dari catatan dan kehadiran yang benar-benar tersimpan.</div>
          <div className="local-ops-summary"><span className="local-ops-icon"><Icon name="spark" size={15} /></span><div><strong>Rekap hitungan · transparan</strong><p>{localSummary}</p><small>Bagian rekap ini hanya mengelompokkan catatan tersimpan; tidak memakai model ML dan tidak menilai perkembangan.</small></div></div>
        </section>
      </section>
    </>
  );
}

function DoctorHome({ data, onGo, onOpenReview }: LooseProps) {
  const authorizedQueue = data.queue.filter((item) => data.consents[item.childId] !== false);
  const pending = authorizedQueue.filter((item) => !item.reviewed);
  const reviewed = authorizedQueue.filter((item) => item.reviewed).length;
  const draftAssessments = data.assessments.filter((item) => item.status === 'draft').length;
  const submittedAssessments = data.assessments.filter((item) => item.status === 'submitted').length;
  const attentionCases = data.activities.filter((item) => item.category === 'Kejadian' || item.mood === 'Membutuhkan dukungan');
  return (
    <>
      <PageTitle eyebrow={dateLabel} title="Periksa hasil sebelum berbagi" description="Lihat pemeriksaan KPSP yang dikirim, baca catatan yang tersedia, lalu tulis ringkasan untuk keluarga." action={<Button icon="clipboard" onClick={() => onGo('kpsp')}>Buka pemeriksaan KPSP</Button>} />
      <section className="doctor-hero gradient-violet-warm">
        <div className="doctor-hero-copy"><Pill tone="plum" dot>Ruang dokter</Pill><h2>Mulai dari hasil yang dikirim untuk ditinjau.</h2><p>Baca jawaban dan catatan sebelum menulis ringkasan. Hasil tidak dibagikan kepada keluarga sebelum dokter meninjaunya.</p><div className="hero-actions"><Button onClick={() => onGo('queue')}>Buka daftar tinjauan</Button><Button variant="outline" onClick={() => onGo('development')}>Lihat catatan perkembangan</Button></div></div>
        <div className="doctor-hero-stat"><span className="doctor-ring"><span>{pending.length}</span><small>menunggu</small></span><div><strong>{authorizedQueue.length} hasil masuk</strong><small>Hasil berubah saat pemeriksaan dikirim.</small></div></div>
      </section>
      <div className="stat-grid four">
        <StatCard label="Perlu ditinjau" value={pending.length} note="hasil menunggu dokter" icon="review" tone="plum" trend="antrean" onClick={() => onGo('queue')} />
        <StatCard label="KPSP tercatat" value={data.assessments.length} note={`${draftAssessments} jawaban sementara · ${submittedAssessments} terkirim`} icon="clipboard" tone="coral" trend="form" onClick={() => onGo('kpsp')} />
        <StatCard label="Sudah ditinjau" value={reviewed} note="riwayat pemeriksaan" icon="check" tone="sage" trend="riwayat" onClick={() => onGo('queue')} />
        <StatCard label="Kasus khusus" value={attentionCases.length} note="catatan yang perlu dibaca" icon="info" tone="gold" trend="perhatian" onClick={() => onGo('activities')} />
      </div>
      <div className="dashboard-grid dashboard-grid-main">
        <section className="panel panel-large">
          <CardTitle eyebrow="Prioritas tinjauan" title="Kasus menunggu dokter" action={<button className="text-link" onClick={() => onGo('queue')}>Buka antrean <Icon name="arrow" size={15} /></button>} />
          <QueuePreview data={data} pending={pending.slice(0, 3)} onOpenReview={onOpenReview} />
        </section>
        <section className="panel model-card">
          <div className="model-card-art"><div className="model-ring ring-a" /><div className="model-ring ring-b" /><span className="model-point" /></div>
          <Pill tone="warm">Tinjauan dokter</Pill><h3>Tidak ada penilaian otomatis.</h3><p>Dokter membaca hasil skrining dan catatan sebelum menulis ringkasan. Hasil yang belum ditinjau tidak ditampilkan kepada keluarga.</p><button className="text-link" onClick={() => onGo('development')}>Lihat catatan perkembangan <Icon name="arrow" size={15} /></button>
        </section>
      </div>
      <section className="notice-strip"><Icon name="privacy" size={18} /><div><strong>Hasil pemeriksaan bukan diagnosis.</strong><span>Dokter menentukan tindak lanjut dan membagikan ringkasan setelah meninjau hasil.</span></div><button className="text-link" onClick={() => onGo('privacy')}>Tentang data keluarga <Icon name="arrow" size={15} /></button></section>
    </>
  );
}

function ParentHome({ data, child, onGo, onOpenMessage, onToggleConsent }: LooseProps) {
  const childActivities = data.activities.filter((item) => item.childId === child.id && item.shared).slice(0, 3);
  const weeklyShared = data.activities.filter((item) => item.childId === child.id && item.shared && (!item.createdAtIso || Date.now() - Date.parse(item.createdAtIso) <= 7 * 24 * 60 * 60 * 1000));
  const newest = childActivities[0];
  const allowed = data.consents[child.id] === true;
  const childMessages = data.messages.filter((message) => message.role !== 'parent' && (message.childId === child.id || message.childId === 'all')).slice(0, 2);
  return (
    <>
      <PageTitle eyebrow={dateLabel} title="Hari ini di Rumah Kecilku" description="Pembaruan yang dibagikan tim pengasuh untuk keluarga." action={<Button variant="soft" icon="message" onClick={() => onGo('messages')}>Tulis ke daycare</Button>} />
      <section className="parent-hero gradient-rose">
        <div className="parent-child-badge"><span>{child.name.slice(-1)}</span><small>{child.ageMonths} bln</small></div>
        <div className="parent-hero-copy"><Pill tone="warm" dot>Profil anak contoh</Pill><h2>Halo, keluarga {child.name}.</h2><p>{newest ? `Kabar terbaru: ${newest.title.toLowerCase()} pada ${newest.time}.` : 'Belum ada kabar dari daycare untuk hari ini.'}</p><div className="hero-actions"><Button onClick={() => onGo('activities')}>Lihat kegiatan</Button><Button variant="outline" onClick={() => onGo('reports')}>Buka laporan anak</Button></div></div>
        <div className="parent-day-card"><small>HARI INI</small><strong>{childActivities.length}</strong><span>catatan aktivitas dibagikan</span><div className="parent-day-icons"><span><Icon name="activity" size={16} /></span><span><Icon name="book" size={16} /></span><span><Icon name="clock" size={16} /></span></div></div>
      </section>
      <div className="dashboard-grid parent-grid">
        <section className="panel panel-large">
          <CardTitle eyebrow="Pembaruan daycare" title="Yang sudah dilakukan" action={<button className="text-link" onClick={() => onGo('activities')}>Buka riwayat <Icon name="arrow" size={15} /></button>} />
          {childActivities.length ? <div className="activity-feed compact-feed">{childActivities.map((item, index) => <div className="feed-row parent-feed-row" key={item.id}><span className={`feed-symbol feed-symbol-${index % 4}`}><Icon name={item.category === 'Stimulasi' ? 'book' : item.category === 'Tidur' ? 'clock' : 'activity'} size={17} /></span><span className="feed-main"><strong>{item.title}</strong><small>{item.note}</small></span><span className="feed-right"><small>{item.time}</small><Pill tone="sage">Dibagikan</Pill></span></div>)}</div> : <EmptyState title="Belum ada catatan" detail="Catatan dari sesi daycare akan muncul di sini setelah dibagikan." />}
        </section>
        <section className="panel parent-message-card">
          <CardTitle eyebrow="Pesan terbaru" title="Dari tim daycare" />
          <div className="parent-message-stack">{childMessages.length ? childMessages.map((message) => <button key={message.id} className="parent-message" onClick={() => onOpenMessage(message)}><span className="message-avatar">RK</span><span><strong>{message.kind}</strong><small>{message.text}</small><em>{message.time} · {message.author}</em></span></button>) : <EmptyState title="Belum ada pesan" detail="Kabar dari pengasuh akan muncul di sini." />}</div>
          <Button variant="outline" size="small" onClick={() => onGo('messages')}>Buka ruang pesan</Button>
        </section>
      </div>
      <section className="panel parent-weekly-summary"><CardTitle eyebrow="Ringkasan mingguan" title="Kabar singkat untuk keluarga" /><p>Minggu ini ada <strong>{weeklyShared.length}</strong> catatan kegiatan yang dibagikan oleh tim daycare.</p><div className="button-row"><Button size="small" variant="outline" onClick={() => onGo('reports')}>Buka laporan lengkap</Button></div><small>Ringkasan berdasarkan catatan yang dibagikan, bukan penilaian medis.</small></section>
      <section className="parent-lower-grid">
        <div className="panel growth-gate-card">
          <div className="growth-gate-icon"><Icon name="growth" size={20} /></div><div><Pill tone={allowed ? 'sage' : 'gold'}>{allowed ? 'Saran ditampilkan' : 'Saran disembunyikan'}</Pill><h3>Ringkasan perkembangan</h3><p>Hasil hanya muncul setelah dokter meninjau dan membagikannya. Pengaturan di bawah hanya mengubah tampilan saran pada akun ini.</p><button className="text-link" onClick={() => onGo('development')}>Lihat ringkasan yang dibagikan <Icon name="arrow" size={15} /></button></div>
        </div>
        <div className="panel consent-card"><div className="consent-card-top"><Icon name="privacy" size={20} /><span>Pengaturan keluarga</span></div><h3>Tampilkan saran perkembangan</h3><p>Pengaturan ini mengubah tampilan saran pada akun contoh. Persetujuan keluarga untuk penggunaan data harus dicatat terpisah.</p><button className={`switch-row ${allowed ? 'switch-on' : ''}`} onClick={() => onToggleConsent(child.id)} aria-pressed={allowed}><span className="switch-track"><i /></span><span>{allowed ? 'Sembunyikan saran' : 'Tampilkan saran'}</span></button></div>
      </section>
    </>
  );
}

function ParentNoChildPage({ onGo }: LooseProps) {
  return <>
    <PageTitle eyebrow="Ruang keluarga" title="Hubungkan profil anak" description="Belum ada profil anak yang terhubung ke akun ini." />
    <section className="panel"><EmptyState icon="child" title="Belum ada profil anak yang ditautkan" detail="Minta tim Rumah Kecilku menghubungkan akun keluarga sebelum kabar anak ditampilkan." action={<Button variant="outline" onClick={() => onGo('messages')}>Hubungi daycare</Button>} /></section>
  </>;
}

function QueuePreview({ data, pending, onOpenReview }: LooseProps) {
  if (!pending.length) return <EmptyState icon="check" title="Belum ada pemeriksaan menunggu tinjauan" detail="Hasil KPSP yang dikirim akan muncul di sini." />;
  return <div className="queue-list compact-queue">{pending.map((item) => {
    const child = data.children.find((entry) => entry.id === item.childId);
    return <button className="queue-row" key={item.id} onClick={() => onOpenReview(item)}><span className="queue-priority"><Icon name="review" size={17} /></span><span className="queue-row-main"><strong>{child?.name || 'Profil anak'} <span>· {item.domain}</span></strong><small>{item.reason}</small><small className="queue-meta">{item.kpspResult ? `${item.kpspResult.yes_count}/${item.kpspResult.total_items} jawaban Ya` : `${item.evidenceCount} jawaban tersimpan`} · {item.date}</small></span><span className="queue-row-end"><Pill tone="plum">{item.priority}</Pill><Icon name="chevron" size={17} /></span></button>;
  })}</div>;
}

function ActivityPage({ role, data, children, search, filter, setFilter, onOpenActivity, onNewActivity }: LooseProps) {
  const visibleIds = new Set(children.map((child) => child.id));
  const visible = role === 'parent' ? data.activities.filter((item) => visibleIds.has(item.childId) && item.shared) : data.activities;
  const isMealCategory = (category: string) => category === 'Makan & minum' || category === 'Makan' || category === 'Minum';
  const filtered = visible.filter((item) => (filter === 'Semua' || (filter === 'Makan & minum' ? isMealCategory(item.category) : item.category === filter)) && (!search || `${item.title} ${item.note} ${data.children.find((c) => c.id === item.childId)?.name}`.toLowerCase().includes(search.toLowerCase())));
  const filters = ['Semua', 'Makan & minum', 'Tidur', 'Stimulasi', 'Bermain', 'Belajar', 'Kejadian'];
  const todayActivities = data.activities.filter((item) => item.createdAt === shortDateLabel);
  const presentCount = data.children.filter((child) => child.attendance === 'Hadir').length;
  const unsharedCount = todayActivities.filter((item) => !item.shared).length;
  const categoryCount = (category) => todayActivities.filter((item) => category === 'Makan & minum' ? isMealCategory(item.category) : item.category === category).length;
  return (
    <>
      <PageTitle eyebrow="SmartDayCare AI · rutinitas dan catatan pengasuh" title={role === 'parent' ? 'Kegiatan yang dibagikan' : 'Pencatatan harian terstruktur'} description={role === 'parent' ? 'Orang tua hanya membaca catatan kegiatan yang dibagikan untuk profil anak yang terhubung.' : 'Catat waktu, sesi, durasi, partisipasi, kebutuhan makan/minum, catatan faktual, dan foto ilustrasi/dummy. Ini bukan penilaian perkembangan.'} action={role !== 'parent' && <Button icon="plus" onClick={onNewActivity}>Catat kegiatan</Button>} />
      <section className="activity-progress-panel gradient-warm-light">
        <div className="progress-copy"><Pill tone="warm">Catatan kegiatan</Pill><h2>{filtered.length} kegiatan tersimpan</h2><p>Setiap catatan menyertakan waktu, kategori, dan apakah kabar telah dibagikan kepada keluarga.</p></div>
        <div className="progress-visual"><div className="progress-orbit"><span>{filtered.length}</span><small>catatan<br />tersimpan</small></div><div className="progress-note"><span className="progress-dot" /><strong>Pembaruan otomatis</strong><small>Diperbarui otomatis kira-kira tiap 10 detik</small></div></div>
      </section>
      {role !== 'parent' && <section className="class-recap panel"><div className="class-recap-heading"><div><div className="eyebrow">Rekap kelas hari ini</div><h2>Yang sudah masuk ke catatan</h2></div><Pill tone="neutral">Rumah Kecilku · {shortDateLabel}</Pill></div><div className="class-recap-grid"><div><span className="recap-icon recap-coral"><Icon name="child" size={16} /></span><strong>{presentCount}/{data.children.length}</strong><small>hadir hari ini</small></div><div><span className="recap-icon recap-sage"><Icon name="activity" size={16} /></span><strong>{categoryCount('Makan') + categoryCount('Minum')}</strong><small>catatan makan & minum</small></div><div><span className="recap-icon recap-plum"><Icon name="clock" size={16} /></span><strong>{categoryCount('Tidur')}</strong><small>catatan istirahat</small></div><div><span className="recap-icon recap-gold"><Icon name="book" size={16} /></span><strong>{categoryCount('Stimulasi')}</strong><small>kegiatan stimulasi</small></div><div><span className="recap-icon recap-neutral"><Icon name="message" size={16} /></span><strong>{unsharedCount}</strong><small>belum dibagikan</small></div></div><div className="class-recap-foot"><Icon name="info" size={14} />Angka dihitung dari catatan yang sudah tersimpan.</div></section>}
      <section className="panel table-panel">
        <div className="table-toolbar"><div><CardTitle eyebrow="Riwayat kegiatan" title="Catatan sesi" /></div><div className="toolbar-actions"><div className="filter-tabs" role="group" aria-label="Filter kategori aktivitas">{filters.map((item) => <button key={item} className={filter === item ? 'filter-active' : ''} onClick={() => setFilter(item)}>{item}</button>)}</div></div></div>
        {filtered.length ? <div className="table-scroll"><table className="data-table"><thead><tr><th>KEGIATAN</th><th>ANAK</th><th>SESI & WAKTU</th><th>SUMBER</th><th>KE KELUARGA</th><th><span className="sr-only">Detail</span></th></tr></thead><tbody>{filtered.map((item) => {
          const child = data.children.find((entry) => entry.id === item.childId);
          return <tr key={item.id}><td><div className="table-primary"><span className={`table-icon ${item.category === 'Stimulasi' ? 'table-icon-coral' : item.category === 'Tidur' ? 'table-icon-plum' : 'table-icon-sage'}`}><Icon name={item.category === 'Stimulasi' ? 'book' : item.category === 'Tidur' ? 'clock' : 'activity'} size={16} /></span><span><strong>{item.title}</strong><small>{item.category} · {item.note}</small>{item.mediaAvailable && <Pill tone="neutral">{item.mediaContentType?.startsWith('video/') ? 'Video terlampir' : 'Foto terlampir'}</Pill>}</span></div></td><td>{child?.name || 'Profil anak'}</td><td>{item.session}<small className="cell-sub">{item.createdAt} · {item.time}</small></td><td>{item.source}</td><td><Pill tone={item.shared ? 'sage' : 'neutral'} dot>{item.shared ? 'Dibagikan' : 'Belum dibagikan'}</Pill></td><td><button className="icon-button table-more" aria-label={`Lihat catatan ${item.title}`} onClick={() => onOpenActivity(item)}><Icon name="chevron" /></button></td></tr>;
        })}</tbody></table></div> : <EmptyState title="Tidak ada catatan pada filter ini" detail="Ubah kategori atau tambahkan catatan sesi baru." action={role !== 'parent' && <Button size="small" onClick={onNewActivity}>Catat sesi selesai</Button>} />}
      </section>
      <div className="info-footnote"><Icon name="info" size={16} /><span>Aktivitas harian menggambarkan konteks pengasuhan. Aktivitas bukan pengganti skrining atau pemeriksaan dokter.</span></div>
    </>
  );
}

function MealCatalogPage({ role, data, onAddMeal }: LooseProps) {
  const meals = data.meals || [];
  const canManageCatalog = role === 'doctor' || role === 'admin';
  return <>
    <PageTitle eyebrow="SmartDayCare AI · katalog makanan" title={role === 'parent' ? 'Menu & informasi gizi' : 'Katalog menu bergizi'} description={role === 'parent' ? 'Informasi gizi bersumber dari katalog daycare. Catatan makanan anak hanya terlihat bila dibagikan pengasuh.' : 'Setiap pilihan menampilkan nilai per 100 g BDD dan per porsi; menu gabungan dijumlah dari bahan katalog. Angka bukan rekomendasi diet individual.'} action={canManageCatalog && <Button icon="plus" onClick={onAddMeal}>Tambah menu</Button>} />
    {role === 'admin' && <div className="nutrition-admin-note"><Icon name="info" size={16} /><span>Hak admin pada halaman ini terbatas pada katalog menu operasional; catatan klinis dan KPSP tetap terpisah.</span></div>}
    <section className="panel meal-catalog-panel"><CardTitle eyebrow={`${meals.length} pilihan pangan`} title="Nilai gizi transparan · per 100 g dan per porsi" action={role === 'caregiver' ? <Pill tone="neutral">Lihat saja</Pill> : null} />
      {meals.length ? <div className="meal-catalog-grid">{meals.map((meal) => {
        const gramWeight = Math.max(Number(meal.servingGrams) || 100, 0.01);
        const nutrients = [['Energi', Number(meal.energyKcal), 'kkal'], ['Protein', Number(meal.proteinG), 'g'], ['Karbohidrat', Number(meal.carbohydrateG), 'g'], ['Lemak', Number(meal.fatG), 'g'], ['Serat', Number(meal.fiberG), 'g']];
        const displayValue = (value: number, multiplier: number) => (value * multiplier).toLocaleString('id-ID', { maximumFractionDigits: 2 });
        return <article className="meal-catalog-card" key={meal.id}>
          <div className="meal-card-heading"><span className="meal-card-icon"><Icon name="leaf" size={17} /></span><div><h3>{meal.name}</h3><small>Contoh porsi: {meal.servingLabel} · {gramWeight} g</small></div></div>
          <div className="meal-nutrition-block"><div className="meal-nutrition-heading"><strong>Per 100 g BDD</strong><small>Dinormalisasi dari ukuran porsi katalog</small></div><div className="nutrition-chip-row">{nutrients.map(([label, value, unit]) => <span key={`100-${label}`}><small>{label}</small><strong>{displayValue(Number(value), 100 / gramWeight)} {unit}</strong></span>)}</div></div>
          <div className="meal-nutrition-block meal-serving-block"><div className="meal-nutrition-heading"><strong>Per porsi yang dicontohkan</strong><small>{meal.servingLabel} · {gramWeight} g</small></div><div className="nutrition-chip-row">{nutrients.map(([label, value, unit]) => <span key={`serving-${label}`}><small>{label}</small><strong>{displayValue(Number(value), 1)} {unit}</strong></span>)}</div></div>
          {meal.allergens && <div className="meal-allergens"><strong>Informasi alergen:</strong> {meal.allergens}</div>}
          {meal.notes && <p>{meal.notes}</p>}
          <div className="meal-source"><strong>Sumber:</strong> {meal.sourceUrl ? <a href={meal.sourceUrl} target="_blank" rel="noreferrer">{meal.source}</a> : <span>{meal.source || 'Sumber belum dicantumkan'}</span>}</div>
          <div className="meal-card-foot">Katalog daycare · bukan rekomendasi diet individual</div>
        </article>;
      })}</div> : <EmptyState icon="leaf" title="Katalog menu belum diisi" detail={canManageCatalog ? 'Tambahkan menu, nilai gizi, dan sumber yang dapat ditelusuri. Pengasuh dapat memilih menu saat mencatat kegiatan makan.' : 'Menu akan muncul setelah pengelola menambahkan pilihan pangan ke katalog.'} action={canManageCatalog && <Button variant="outline" size="small" onClick={onAddMeal}>Tambah menu bergizi</Button>} />}
    </section>
    <div className="info-footnote"><Icon name="info" size={15} /><span>BDD berarti bagian yang dapat dimakan. Nilai per porsi dihitung proporsional dari TKPI dan ukuran porsi yang ditampilkan; untuk produk kemasan, utamakan label produk. Nilai bukan preskripsi atau saran diet.</span></div>
  </>;
}

function ModalMealForm({ onSave, onClose }: LooseProps) {
  const [name, setName] = useState('');
  const [servingLabel, setServingLabel] = useState('1 porsi');
  const [servingGrams, setServingGrams] = useState('150');
  const [energyKcal, setEnergyKcal] = useState('');
  const [proteinG, setProteinG] = useState('');
  const [carbohydrateG, setCarbohydrateG] = useState('');
  const [fatG, setFatG] = useState('');
  const [fiberG, setFiberG] = useState('');
  const [allergens, setAllergens] = useState('');
  const [source, setSource] = useState('');
  const [sourceUrl, setSourceUrl] = useState('');
  const [notes, setNotes] = useState('');
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  const submit = async (event) => {
    event.preventDefault();
    if (busy) return;
    setError('');
    if (!name.trim() || !servingLabel.trim() || !source.trim()) { setError('Isi nama menu, ukuran porsi, dan sumber nilai gizi.'); return; }
    if (sourceUrl.trim() && !/^https?:\/\//i.test(sourceUrl.trim())) { setError('Tautan sumber harus diawali http:// atau https://.'); return; }
    const requiredNumbers = [energyKcal, proteinG, carbohydrateG, fatG, fiberG];
    if (requiredNumbers.some((value) => value === '' || !Number.isFinite(Number(value)) || Number(value) < 0)) { setError('Isi nilai energi, protein, karbohidrat, lemak, dan serat dengan angka nol atau lebih.'); return; }
    setBusy(true);
    try { await onSave({ name: name.trim(), servingLabel: servingLabel.trim(), servingGrams: Number(servingGrams), energyKcal: Number(energyKcal), proteinG: Number(proteinG), carbohydrateG: Number(carbohydrateG), fatG: Number(fatG), fiberG: Number(fiberG), allergens: allergens.trim(), source: source.trim(), sourceUrl: sourceUrl.trim(), notes: notes.trim() }); }
    finally { setBusy(false); }
  };
  return <ModalShell title="Tambah menu ke katalog" subtitle="Masukkan nilai per porsi dengan berat yang jelas dan sumber yang dapat ditelusuri. Dokter mengelola katalog." onClose={onClose} width="wide">
    <form className="modal-form" onSubmit={submit}>
      <div className="form-grid"><label className="field field-full"><span>Nama menu</span><input value={name} onChange={(event) => setName(event.target.value)} placeholder="Contoh: nasi, ikan, dan sayur" required /></label><label className="field"><span>Label porsi</span><input value={servingLabel} onChange={(event) => setServingLabel(event.target.value)} placeholder="1 piring" required /></label><label className="field"><span>Berat porsi (gram)</span><input type="number" min="1" max="5000" step="1" value={servingGrams} onChange={(event) => setServingGrams(event.target.value)} required /></label><label className="field"><span>Energi (kkal / porsi)</span><input type="number" min="0" max="10000" step="0.1" value={energyKcal} onChange={(event) => setEnergyKcal(event.target.value)} required /></label><label className="field"><span>Protein (g / porsi)</span><input type="number" min="0" max="1000" step="0.1" value={proteinG} onChange={(event) => setProteinG(event.target.value)} required /></label><label className="field"><span>Karbohidrat (g / porsi)</span><input type="number" min="0" max="1000" step="0.1" value={carbohydrateG} onChange={(event) => setCarbohydrateG(event.target.value)} required /></label><label className="field"><span>Lemak (g / porsi)</span><input type="number" min="0" max="1000" step="0.1" value={fatG} onChange={(event) => setFatG(event.target.value)} required /></label><label className="field"><span>Serat (g / porsi)</span><input type="number" min="0" max="1000" step="0.1" value={fiberG} onChange={(event) => setFiberG(event.target.value)} required /></label><label className="field"><span>Informasi alergen</span><input value={allergens} onChange={(event) => setAllergens(event.target.value)} placeholder="Contoh: ikan; periksa label" /></label><label className="field"><span>Sumber nilai gizi (wajib)</span><input value={source} onChange={(event) => setSource(event.target.value)} placeholder="TKPI 2020 · kode pangan atau label produk" required /></label><label className="field field-full"><span>Tautan sumber (opsional)</span><input type="url" value={sourceUrl} onChange={(event) => setSourceUrl(event.target.value)} placeholder="https://..." /></label><label className="field field-full"><span>Catatan takaran/pengolahan</span><textarea rows={2} value={notes} onChange={(event) => setNotes(event.target.value)} placeholder="Jelaskan bagian dapat dimakan, asumsi takaran, atau proses olah." /></label></div>
      <div className="form-hint"><Icon name="info" size={15} />Katalog dibuat dokter. Cantumkan sumber yang bisa ditelusuri dan jangan memakai angka perkiraan atau menjadikannya preskripsi diet.</div>
      {error && <div className="form-error" role="alert">{error}</div>}
      <div className="modal-actions"><Button variant="outline" onClick={onClose} disabled={busy}>Batal</Button><Button type="submit" icon="check" disabled={busy}>{busy ? 'Menyimpan…' : 'Simpan menu'}</Button></div>
    </form>
  </ModalShell>;
}

function ChildrenPage({ role, data, selectedId, setSelectedId, search, onAddChild, onEditChild, onGo, onCheckIn, onCheckOut, onMarkAttendance }: LooseProps) {
  const isAdmin = role === 'admin';
  const canOperateAttendance = isAdmin || role === 'caregiver';
  const [attendanceFilter, setAttendanceFilter] = useState('Semua');
  const list = data.children.filter((child) => (attendanceFilter === 'Semua' || child.attendance === attendanceFilter) && (!search || child.name.toLowerCase().includes(search.toLowerCase())));
  const selected = data.children.find((child) => child.id === selectedId) || data.children[0];
  const [guardianLinks, setGuardianLinks] = useState([]);
  const [guardianCandidates, setGuardianCandidates] = useState([]);
  const [guardianInvitations, setGuardianInvitations] = useState([]);
  const [guardianAudit, setGuardianAudit] = useState([]);
  const [selectedCandidate, setSelectedCandidate] = useState('');
  const [guardianRelationship, setGuardianRelationship] = useState('Orang tua/wali');
  const [verificationMethod, setVerificationMethod] = useState('in_person');
  const [institutionCheckConfirmed, setInstitutionCheckConfirmed] = useState(false);
  const [guardianBusy, setGuardianBusy] = useState(false);
  const [guardianError, setGuardianError] = useState('');
  const [guardianMessage, setGuardianMessage] = useState('');
  const [authorizedPickups, setAuthorizedPickups] = useState([]);
  const [attendanceEvents, setAttendanceEvents] = useState([]);
  const [selectedPickupId, setSelectedPickupId] = useState('');
  const [pickupNameMatchConfirmed, setPickupNameMatchConfirmed] = useState(false);
  const [pickupName, setPickupName] = useState('');
  const [pickupRelationship, setPickupRelationship] = useState('');
  const [pickupConfirmationMethod, setPickupConfirmationMethod] = useState('in_person');
  const [parentConfirmationRecorded, setParentConfirmationRecorded] = useState(false);
  const [pickupBusy, setPickupBusy] = useState(false);
  const [pickupError, setPickupError] = useState('');
  const [pickupMessage, setPickupMessage] = useState('');

  useEffect(() => {
    let active = true;
    if (isAdmin && selected?.id && hasSessionToken()) {
      setGuardianError('');
      setGuardianMessage('');
      setGuardianLinks([]);
      setGuardianCandidates([]);
      setGuardianAudit([]);
      setSelectedCandidate('');
      Promise.all([
        apiGet(`children/${encodeURIComponent(selected.id)}/guardians`),
        apiGet(`children/${encodeURIComponent(selected.id)}/guardian-candidates`),
        apiGet(`children/${encodeURIComponent(selected.id)}/guardian-links/audit`),
      ]).then(([links, candidates, audit]) => {
        if (!active) return;
        setGuardianLinks(links.guardians || []);
        setGuardianCandidates(candidates.candidates || []);
        setGuardianAudit(audit.events || []);
        setSelectedCandidate((current) => (candidates.candidates || []).some((item) => item.id === current) ? current : (candidates.candidates?.[0]?.id || ''));
      }).catch((cause) => {
        if (active) setGuardianError(cause instanceof ApiError ? cause.message : 'Relasi wali belum dapat dimuat.');
      });
    } else {
      setGuardianLinks([]);
      setGuardianCandidates([]);
      setGuardianAudit([]);
    }
    return () => { active = false; };
  }, [isAdmin, selected?.id]);

  useEffect(() => {
    let active = true;
    setPickupError('');
    setPickupMessage('');
    setPickupNameMatchConfirmed(false);
    setPickupName('');
    setPickupRelationship('');
    setPickupConfirmationMethod('in_person');
    setParentConfirmationRecorded(false);
    setAuthorizedPickups([]);
    setAttendanceEvents([]);
    setSelectedPickupId('');
    if (canOperateAttendance && selected?.id && hasSessionToken()) {
      const eventRequest = isAdmin
        ? apiGet(`attendance/events?child_id=${encodeURIComponent(selected.id)}`)
        : Promise.resolve({ events: [] });
      Promise.all([
        apiGet(`attendance/children/${encodeURIComponent(selected.id)}/authorized-pickups`),
        eventRequest,
      ]).then(([pickupPayload, eventPayload]) => {
        if (!active) return;
        const entries = pickupPayload.authorized_pickups || [];
        setAuthorizedPickups(entries);
        setAttendanceEvents(eventPayload.events || []);
        setSelectedPickupId((current) => entries.some((item) => item.id === current) ? current : (entries[0]?.id || ''));
      }).catch((cause) => {
        if (active) setPickupError(cause instanceof ApiError ? cause.message : 'Daftar penjemput belum dapat dimuat.');
      });
    } else {
      setAuthorizedPickups([]);
      setAttendanceEvents([]);
      setSelectedPickupId('');
    }
    return () => { active = false; };
  }, [canOperateAttendance, selected?.id]);

  useEffect(() => {
    let active = true;
    if (role === 'parent' && hasSessionToken()) {
      apiGet('children/guardian-invitations')
        .then((payload) => { if (active) setGuardianInvitations(payload.invitations || []); })
        .catch((cause) => { if (active) setGuardianError(cause instanceof ApiError ? cause.message : 'Permintaan relasi wali belum dapat dimuat.'); });
    } else {
      setGuardianInvitations([]);
    }
    return () => { active = false; };
  }, [role]);

  const reloadGuardianAdminData = async (childId: string) => {
    const [links, candidates, audit] = await Promise.all([
      apiGet(`children/${encodeURIComponent(childId)}/guardians`),
      apiGet(`children/${encodeURIComponent(childId)}/guardian-candidates`),
      apiGet(`children/${encodeURIComponent(childId)}/guardian-links/audit`),
    ]);
    setGuardianLinks(links.guardians || []);
    setGuardianCandidates(candidates.candidates || []);
    setGuardianAudit(audit.events || []);
    setSelectedCandidate((current) => (candidates.candidates || []).some((item) => item.id === current) ? current : (candidates.candidates?.[0]?.id || ''));
  };

  const submitGuardianInvitation = async (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!selected?.id || !selectedCandidate || !institutionCheckConfirmed || guardianBusy) return;
    setGuardianBusy(true);
    setGuardianError('');
    setGuardianMessage('');
    try {
      await apiPost(`children/${encodeURIComponent(selected.id)}/guardians`, {
        parent_user_id: selectedCandidate,
        relationship: guardianRelationship,
        verification_method: verificationMethod,
        institution_check_confirmed: institutionCheckConfirmed,
      });
      await reloadGuardianAdminData(selected.id);
      setInstitutionCheckConfirmed(false);
      setGuardianMessage('Permintaan dikirim. Akses keluarga baru aktif setelah akun wali mengonfirmasi.');
    } catch (cause) {
      setGuardianError(cause instanceof ApiError ? cause.message : 'Permintaan wali belum tersimpan. Coba lagi.');
    } finally {
      setGuardianBusy(false);
    }
  };

  const revokeGuardian = async (link: DashboardRecord) => {
    if (!selected?.id || guardianBusy || !window.confirm(`Cabut tautan akses ${link.name} ke profil ini?`)) return;
    setGuardianBusy(true);
    setGuardianError('');
    setGuardianMessage('');
    try {
      await apiPost(`children/${encodeURIComponent(selected.id)}/guardians/${encodeURIComponent(link.parent_user_id)}/revoke`, {});
      await reloadGuardianAdminData(selected.id);
      setGuardianMessage('Tautan wali dicabut dan dicatat pada jejak audit.');
    } catch (cause) {
      setGuardianError(cause instanceof ApiError ? cause.message : 'Tautan wali belum dapat dicabut. Coba lagi.');
    } finally {
      setGuardianBusy(false);
    }
  };

  const reloadPickupData = async (childId: string) => {
    const [pickupPayload, eventPayload] = await Promise.all([
      apiGet(`attendance/children/${encodeURIComponent(childId)}/authorized-pickups`),
      isAdmin ? apiGet(`attendance/events?child_id=${encodeURIComponent(childId)}`) : Promise.resolve({ events: [] }),
    ]);
    const entries = pickupPayload.authorized_pickups || [];
    setAuthorizedPickups(entries);
    setAttendanceEvents(eventPayload.events || []);
    setSelectedPickupId((current) => entries.some((item) => item.id === current) ? current : (entries[0]?.id || ''));
  };

  const submitAuthorizedPickup = async (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!isAdmin || !selected?.id || !pickupName.trim() || !pickupRelationship.trim() || !parentConfirmationRecorded || pickupBusy) return;
    setPickupBusy(true);
    setPickupError('');
    setPickupMessage('');
    try {
      await apiPost(`attendance/children/${encodeURIComponent(selected.id)}/authorized-pickups`, {
        name: pickupName.trim(),
        relationship: pickupRelationship.trim(),
        parent_confirmation_method: pickupConfirmationMethod,
        parent_confirmation_recorded: parentConfirmationRecorded,
      });
      await reloadPickupData(selected.id);
      setPickupName('');
      setPickupRelationship('');
      setParentConfirmationRecorded(false);
      setPickupMessage('Penjemput tercatat setelah konfirmasi orang tua di luar aplikasi.');
    } catch (cause) {
      setPickupError(cause instanceof ApiError ? cause.message : 'Daftar penjemput belum tersimpan. Coba lagi.');
    } finally {
      setPickupBusy(false);
    }
  };

  const revokeAuthorizedPickup = async (pickup: DashboardRecord) => {
    if (!isAdmin || !selected?.id || pickupBusy || !window.confirm(`Cabut izin penjemput ${pickup.name}?`)) return;
    setPickupBusy(true);
    setPickupError('');
    setPickupMessage('');
    try {
      await apiPost(`attendance/children/${encodeURIComponent(selected.id)}/authorized-pickups/${encodeURIComponent(pickup.id)}/revoke`, {});
      await reloadPickupData(selected.id);
      setPickupMessage('Izin penjemput dicabut dan dicatat.');
    } catch (cause) {
      setPickupError(cause instanceof ApiError ? cause.message : 'Izin penjemput belum dapat dicabut. Coba lagi.');
    } finally {
      setPickupBusy(false);
    }
  };

  const recordCheckIn = async () => {
    if (!selected?.id || pickupBusy || !onCheckIn) return;
    setPickupBusy(true);
    setPickupError('');
    setPickupMessage('');
    try {
      const saved = await onCheckIn(selected.id);
      if (saved) {
        setPickupMessage('Check-in tersimpan dengan waktu dan petugas.');
        await reloadPickupData(selected.id);
      }
    } catch (cause) {
      setPickupError(cause instanceof ApiError ? cause.message : 'Jejak check-in belum dapat dimuat.');
    } finally {
      setPickupBusy(false);
    }
  };

  const recordCheckOut = async () => {
    if (!selected?.id || !selectedPickupId || !pickupNameMatchConfirmed || pickupBusy || !onCheckOut) return;
    setPickupBusy(true);
    setPickupError('');
    setPickupMessage('');
    try {
      const saved = await onCheckOut({ childId: selected.id, pickupAuthorizationId: selectedPickupId });
      if (saved) {
        setPickupNameMatchConfirmed(false);
        setPickupMessage('Check-out tersimpan bersama nama penjemput berizin.');
        await reloadPickupData(selected.id);
      }
    } catch (cause) {
      setPickupError(cause instanceof ApiError ? cause.message : 'Jejak check-out belum dapat dimuat.');
    } finally {
      setPickupBusy(false);
    }
  };

  const respondToGuardianInvitation = async (invitation: DashboardRecord, accept: boolean) => {
    if (guardianBusy) return;
    setGuardianBusy(true);
    setGuardianError('');
    setGuardianMessage('');
    try {
      const action = accept ? 'accept' : 'reject';
      await apiPost(`children/${encodeURIComponent(invitation.child_id)}/guardian-invitations/${action}`, accept ? { confirm_relationship: true } : {});
      const payload = await apiGet('children/guardian-invitations');
      setGuardianInvitations(payload.invitations || []);
      setGuardianMessage(accept ? 'Relasi dikonfirmasi. Akses ke profil anak akan muncul setelah data disegarkan.' : 'Permintaan relasi ditolak. Daycare tidak mendapat akses keluarga melalui tautan ini.');
    } catch (cause) {
      setGuardianError(cause instanceof ApiError ? cause.message : 'Respons belum tersimpan. Coba lagi.');
    } finally {
      setGuardianBusy(false);
    }
  };

  return (
    <>
      <PageTitle eyebrow={isAdmin ? 'Roster operasional' : 'Profil anak contoh'} title="Daftar anak" description={isAdmin ? 'Akses admin dibatasi pada roster, ruang, kehadiran, dan relasi wali yang perlu diverifikasi. Catatan kesehatan, observasi, dan KPSP tidak ditampilkan.' : 'Nama dan usia yang terlihat adalah contoh untuk mencoba alur. Jangan masukkan identitas anak yang sebenarnya.'} action={<Button icon="plus" onClick={onAddChild}>{isAdmin ? 'Tambah profil' : 'Tambah profil contoh'}</Button>} />
      {role === 'parent' && (guardianInvitations.length > 0 || guardianError || guardianMessage) && <section className="panel guardian-invitations-panel"><CardTitle eyebrow="Relasi wali · konfirmasi keluarga" title="Permintaan tautan profil" /><p className="guardian-panel-note">Profil baru terbuka setelah daycare mencatat pemeriksaan institusi dan akun wali mengonfirmasi. Tidak ada dokumen identitas yang diminta di aplikasi demo.</p>{guardianError && <div className="form-error" role="alert">{guardianError}</div>}{guardianMessage && <div className="guardian-status-message" role="status">{guardianMessage}</div>}{guardianInvitations.length ? <div className="guardian-invitation-list">{guardianInvitations.map((invitation) => <article className="guardian-invitation-card" key={invitation.child_id}><div><strong>{invitation.child_name}</strong><small>{invitation.organization_name} · relasi: {invitation.relationship}</small><small>Pemeriksaan daycare dicatat oleh {invitation.verifier_name || 'tim institusi'} · {invitation.verification_method}</small></div><div className="guardian-invitation-actions"><Button size="small" variant="outline" onClick={() => respondToGuardianInvitation(invitation, false)} disabled={guardianBusy}>Tolak</Button><Button size="small" onClick={() => respondToGuardianInvitation(invitation, true)} disabled={guardianBusy}>Konfirmasi</Button></div></article>)}</div> : <EmptyState icon="privacy" title="Belum ada permintaan relasi" detail="Jika daycare mengirim permintaan tautan, rincian dan pilihan konfirmasi akan tampil di sini." />}</section>}
      <div className="children-layout">
        <section className="panel child-directory">
          <div className="directory-toolbar"><div className="filter-tabs" role="group" aria-label="Filter kehadiran">{['Semua', 'Hadir', 'Izin', 'Sakit'].map((item) => <button key={item} className={attendanceFilter === item ? 'filter-active' : ''} onClick={() => setAttendanceFilter(item)}>{item}</button>)}</div><span className="subtle-count">{list.length} profil</span></div>
          <div className="child-list">{list.length ? list.map((child, index) => <button className={`child-list-row ${selected?.id === child.id ? 'child-selected' : ''}`} key={child.id} onClick={() => setSelectedId(child.id)}><span className={`child-avatar child-avatar-${index % 5}`}>{child.name.slice(-1)}</span><span className="child-row-copy"><strong>{child.name}</strong><small>{child.ageMonths ? `${child.ageMonths} bulan` : 'Usia belum dicatat'} · {child.room}</small></span><Pill tone={child.attendance === 'Hadir' ? 'sage' : 'neutral'}>{child.attendance}</Pill></button>) : <EmptyState title="Belum ada profil yang tersimpan" detail={isAdmin ? 'Buat profil roster daycare; relasi wali dapat ditautkan setelah akun keluarga tersedia dan pemeriksaan institusi dilakukan.' : role === 'parent' ? 'Profil anak akan terlihat setelah permintaan relasi wali dikonfirmasi.' : 'Tidak ada profil anak aktif yang terhubung ke tenant ini.'} action={isAdmin ? <Button size="small" onClick={onAddChild}>Tambah profil</Button> : null} />}</div>
        </section>
        {selected && <section className="panel child-profile-panel">
          <div className="profile-card-top gradient-sage"><span className="profile-avatar-large">{selected.name.slice(-1)}</span><div><Pill tone="sage">{isAdmin ? 'Roster operasional' : 'Profil anak contoh'}</Pill><h2>{selected.name}</h2><span>{selected.ageMonths ? `${selected.ageMonths} bulan` : 'Usia belum dicatat'} · {selected.room}</span></div>{!isAdmin && <button className="icon-button profile-menu" aria-label="Buka laporan" onClick={() => onGo('reports')}><Icon name="report" /></button>}</div>
          <div className="profile-body"><div className="profile-row"><span>Kehadiran hari ini</span><strong>{selected.checkOut && selected.checkOut !== 'Belum dicatat' ? `Sudah dijemput ${selected.checkOut}${selected.pickupPersonName ? ` · ${selected.pickupPersonName}` : ''}` : selected.attendance === 'Hadir' ? `Hadir sejak ${selected.checkIn}` : selected.attendance}</strong></div>{!isAdmin && <><div className="profile-row"><span>Catatan profil</span><strong>{selected.note}</strong></div><div className="profile-row"><span>Saran perkembangan</span><strong>{data.consents[selected.id] === true ? 'Ditampilkan di akun ini' : 'Disembunyikan di akun ini'}</strong></div></>}
            <div className="profile-actions">{canOperateAttendance && selected.attendance !== 'Hadir' && <><Button variant="soft" icon="calendar" onClick={recordCheckIn} disabled={pickupBusy}>Catat check-in</Button><Button variant="outline" icon="check" onClick={() => onMarkAttendance(selected.id, 'Izin')} disabled={pickupBusy || selected.attendance === 'Izin'}>{selected.attendance === 'Izin' ? 'Izin tercatat' : 'Tandai izin'}</Button></>}{isAdmin && <Button variant="outline" icon="activity" onClick={() => onEditChild(selected)}>Edit profil</Button>}{!isAdmin && <><Button variant="outline" icon="growth" onClick={() => onGo('development')}>Lihat tumbuh kembang</Button><Button variant="outline" icon="activity" onClick={() => onGo('activities')}>Buka catatan sesi</Button></>}</div>
            {canOperateAttendance && selected.attendance === 'Hadir' && (!selected.checkOut || selected.checkOut === 'Belum dicatat') && <div className="pickup-handover-form"><CardTitle eyebrow="Penjemputan langsung" title="Catat serah-terima pulang" /><p className="guardian-panel-note">Pilih nama yang telah diizinkan dan cocokkan orang yang hadir secara langsung. Pemeriksaan ini bukan verifikasi identitas independen; jangan simpan nomor atau foto dokumen.</p>{authorizedPickups.length ? <><label className="field"><span>Penjemput berizin</span><select value={selectedPickupId} onChange={(event) => setSelectedPickupId(event.target.value)}><option value="">Pilih penjemput</option>{authorizedPickups.map((pickup) => <option key={pickup.id} value={pickup.id}>{pickup.name} · {pickup.relationship}</option>)}</select></label><label className="guardian-confirm-check"><input type="checkbox" checked={pickupNameMatchConfirmed} onChange={(event) => setPickupNameMatchConfirmed(event.target.checked)} /><span>Saya telah mencocokkan orang yang hadir dengan daftar penjemput aktif secara langsung.</span></label><Button icon="check" onClick={recordCheckOut} disabled={!selectedPickupId || !pickupNameMatchConfirmed || pickupBusy}>{pickupBusy ? 'Menyimpan…' : 'Konfirmasi check-out'}</Button></> : <p className="guardian-empty-note">Belum ada penjemput aktif. Admin perlu mencatat konfirmasi orang tua di luar aplikasi sebelum check-out dapat dicatat.</p>}</div>}
            {pickupError && <div className="form-error" role="alert">{pickupError}</div>}{pickupMessage && <div className="guardian-status-message" role="status">{pickupMessage}</div>}
          </div>
          {isAdmin && <div className="guardian-admin-panel"><CardTitle eyebrow="Relasi keluarga · data minimum" title="Akses wali ke profil" /><p className="guardian-panel-note">Tautan memerlukan pemeriksaan institusi dan konfirmasi akun wali. Simpan hanya relasi; jangan masukkan nomor dokumen identitas, catatan kesehatan, atau jawaban KPSP.</p>{guardianError && <div className="form-error" role="alert">{guardianError}</div>}{guardianMessage && <div className="guardian-status-message" role="status">{guardianMessage}</div>}{guardianLinks.length ? <div className="guardian-link-list">{guardianLinks.map((link) => <article className="guardian-link-row" key={link.parent_user_id}><div><strong>{link.name}</strong><small>{link.email_hint} · {link.relationship}</small><small>{link.status === 'pending' ? 'Menunggu konfirmasi akun wali' : link.status === 'verified' ? 'Akses aktif · pemeriksaan institusi dan konfirmasi keluarga tercatat' : link.status === 'revoked' ? 'Tautan dicabut' : 'Permintaan ditolak'}</small></div><div className="guardian-link-actions"><Pill tone={link.status === 'verified' ? 'sage' : link.status === 'pending' ? 'gold' : 'neutral'}>{link.status}</Pill>{['pending', 'verified'].includes(link.status) && <Button size="small" variant="outline" disabled={guardianBusy} onClick={() => revokeGuardian(link)}>Cabut</Button>}</div></article>)}</div> : <p className="guardian-empty-note">Belum ada akun wali tertaut yang tercatat untuk profil ini.</p>}{guardianCandidates.length ? <form className="guardian-link-form" onSubmit={submitGuardianInvitation}><label className="field"><span>Akun wali di daycare yang sama</span><select value={selectedCandidate} onChange={(event) => setSelectedCandidate(event.target.value)} required>{guardianCandidates.map((candidate) => <option key={candidate.id} value={candidate.id}>{candidate.name} · {candidate.email_hint}</option>)}</select></label><label className="field"><span>Relasi</span><input value={guardianRelationship} onChange={(event) => setGuardianRelationship(event.target.value)} maxLength={40} required /></label><label className="field"><span>Metode pemeriksaan institusi</span><select value={verificationMethod} onChange={(event) => setVerificationMethod(event.target.value)}><option value="in_person">Konfirmasi langsung</option><option value="document_review">Dokumen diperiksa di luar aplikasi</option><option value="institution_record">Catatan institusi</option></select></label><label className="guardian-confirm-check"><input type="checkbox" checked={institutionCheckConfirmed} onChange={(event) => setInstitutionCheckConfirmed(event.target.checked)} /><span>Saya telah memeriksa relasi wali melalui prosedur daycare di luar aplikasi. Saya tidak menyimpan nomor/foto dokumen di sini.</span></label><Button type="submit" disabled={guardianBusy || !selectedCandidate || !institutionCheckConfirmed}>{guardianBusy ? 'Mengirim…' : 'Kirim permintaan konfirmasi'}</Button></form> : <p className="guardian-empty-note">Tidak ada akun keluarga aktif lain di daycare ini yang siap ditautkan.</p>}<details className="guardian-audit-details"><summary>Jejak tindakan relasi ({guardianAudit.length})</summary>{guardianAudit.length ? <ul>{guardianAudit.map((event, index) => <li key={`${event.created_at}-${index}`}><strong>{event.action}</strong><span>{event.parent_name} · oleh {event.actor_name} · {event.created_at}</span></li>)}</ul> : <small>Belum ada perubahan relasi yang tercatat.</small>}</details></div>}
          {canOperateAttendance && <div className="authorized-pickup-panel"><CardTitle eyebrow="Serah-terima · data minimum" title="Penjemput berizin" /><p className="guardian-panel-note">Admin mencatat nama setelah mengonfirmasi orang tua/wali di luar aplikasi. Daftar hanya memuat nama dan relasi; tidak menyimpan nomor telepon, nomor identitas, atau foto dokumen.</p>{authorizedPickups.length ? <div className="authorized-pickup-list">{authorizedPickups.map((pickup) => <article className="authorized-pickup-row" key={pickup.id}><div><strong>{pickup.name}</strong><small>{pickup.relationship}{isAdmin ? ` · konfirmasi ${pickup.parent_confirmation_method === 'in_person' ? 'langsung' : pickup.parent_confirmation_method === 'phone' ? 'telepon' : 'catatan tertulis di luar aplikasi'}` : ''}</small></div>{isAdmin && <Button size="small" variant="outline" disabled={pickupBusy} onClick={() => revokeAuthorizedPickup(pickup)}>Cabut izin</Button>}</article>)}</div> : <p className="guardian-empty-note">Belum ada penjemput aktif yang disahkan daycare.</p>}{isAdmin && <form className="authorized-pickup-form" onSubmit={submitAuthorizedPickup}><label className="field"><span>Nama penjemput</span><input value={pickupName} onChange={(event) => setPickupName(event.target.value)} maxLength={80} autoComplete="off" required /></label><label className="field"><span>Relasi dengan anak</span><input value={pickupRelationship} onChange={(event) => setPickupRelationship(event.target.value)} maxLength={40} placeholder="Contoh: kakek, bibi" required /></label><label className="field"><span>Cara konfirmasi orang tua/wali di luar aplikasi</span><select value={pickupConfirmationMethod} onChange={(event) => setPickupConfirmationMethod(event.target.value)}><option value="in_person">Konfirmasi langsung</option><option value="phone">Konfirmasi telepon</option><option value="offline_written_record">Catatan tertulis di luar aplikasi</option></select></label><label className="guardian-confirm-check"><input type="checkbox" checked={parentConfirmationRecorded} onChange={(event) => setParentConfirmationRecorded(event.target.checked)} /><span>Saya sudah mengonfirmasi izin ini kepada orang tua/wali di luar aplikasi.</span></label><Button type="submit" disabled={pickupBusy || !parentConfirmationRecorded}>{pickupBusy ? 'Menyimpan…' : 'Tambah penjemput berizin'}</Button></form>}{isAdmin && <details className="attendance-audit-details"><summary>Jejak kehadiran dan serah-terima ({attendanceEvents.length})</summary>{attendanceEvents.length ? <ul>{attendanceEvents.map((event) => <li key={event.id}><strong>{event.event_type === 'authorized_pickup_added' ? 'Penjemput ditambahkan' : event.event_type === 'authorized_pickup_revoked' ? 'Izin penjemput dicabut' : event.event_type === 'check_in' ? 'Check-in' : event.event_type === 'check_out' ? 'Check-out' : 'Status kehadiran dicatat'}</strong><span>{event.pickup_person_name ? `${event.pickup_person_name} · ` : ''}{event.status || ''}{event.pickup_name_match_confirmed ? ' · nama dicocokkan langsung' : ''}{event.actor_name ? ` · oleh ${event.actor_name}` : ''} · {new Intl.DateTimeFormat('id-ID', { dateStyle: 'short', timeStyle: 'short', timeZone: 'Asia/Jakarta' }).format(new Date(event.occurred_at))}</span></li>)}</ul> : <small>Belum ada peristiwa kehadiran atau perubahan izin yang tercatat.</small>}</details>}</div>}
          {!isAdmin && <div className="profile-note"><Icon name="privacy" size={16} /><span>Profil ini adalah contoh. Jangan masukkan identitas atau catatan kesehatan anak yang sebenarnya.</span></div>}
        </section>}
      </div>
    </>
  );
}

function ParentDevelopmentReport({ data, child, onGo }: LooseProps) {
  const sharedReviews = data.queue.filter((item) => item.childId === child?.id && item.reviewed && item.published);
  const sharedReports = (data.developmentReports || []).filter((item) => item.childId === child?.id && item.published);
  const ideas = data.consents[child?.id] === true ? sharedReviews.filter((item) => item.decision === 'Berikan kegiatan stimulasi umum') : [];
  const hasSharedResult = sharedReviews.length > 0 || sharedReports.length > 0;
  return <div className="parent-development-report">
    {sharedReports.map((report) => <section className="panel parent-doctor-summary quarterly-parent-report" key={report.id}><div className="parent-summary-top"><span className="summary-icon"><Icon name="report" size={18} /></span><Pill tone="sage" dot>Laporan ditinjau dokter</Pill><small>{report.periodStart} – {report.periodEnd}</small></div><h2>Ringkasan perkembangan tiga bulanan</h2><p>{report.summary}</p><div className="quarterly-shared-stats"><strong>{report.observationStats?.total_observations || 0} observasi tercatat</strong>{Object.entries(report.observationStats?.by_aspect || {}).map(([aspect, counts]: [string, any]) => <span key={aspect}>{aspect}: {counts.Teramati || 0} teramati · {counts['Belum teramati'] || 0} belum teramati · {counts['Belum ada kesempatan'] || 0} belum ada kesempatan</span>)}</div><div className="parent-summary-boundary"><Icon name="info" size={15} /><span>Jumlah catatan bukan ukuran kemampuan. Ringkasan ini ditinjau dokter; bukan diagnosis atau estimasi usia perkembangan.</span></div></section>)}
    {sharedReviews.map((item) => <section className="panel parent-doctor-summary" key={item.id}><div className="parent-summary-top"><span className="summary-icon"><Icon name="review" size={18} /></span><Pill tone="sage" dot>Sudah ditinjau dokter</Pill><small>{item.date}</small></div><h2>Ringkasan hasil KPSP</h2><p>{item.note}</p>{item.kpspResult?.result_code && <div className="parent-summary-kpsp"><span className={`review-kpsp-code review-kpsp-${item.kpspResult.result_code.toLowerCase()}`}>{item.kpspResult.result_code}</span><div><small>HASIL SKRINING KPSP · {item.kpspResult.yes_count}/{item.kpspResult.total_items} JAWABAN YA</small><strong>{item.kpspResult.result_label}</strong><p>Hasil skrining, bukan diagnosis. Penjelasan lebih lanjut dapat diberikan dokter saat konsultasi.</p></div></div>}<div className="parent-summary-boundary"><Icon name="info" size={15} /><span>Ringkasan ini bukan diagnosis. Hubungi dokter untuk penjelasan atau konsultasi.</span></div></section>)}
    {!hasSharedResult && <section className="panel parent-no-summary"><EmptyState icon="growth" title="Belum ada laporan dokter yang dibagikan" detail="Orang tua hanya melihat laporan tiga bulanan dan hasil KPSP setelah ditinjau serta diterbitkan dokter. Observasi internal dan jawaban mentah tidak ditampilkan." action={<Button variant="outline" onClick={() => onGo('messages')}>Tanya tim daycare</Button>} /></section>}
    <section className="parent-ideas-panel gradient-warm-light"><div><Pill tone="warm">Arahan kegiatan</Pill><h2>Saran dari tinjauan dokter</h2><p>Saran khusus hanya muncul jika dokter meninjau dan membagikannya. Sesuaikan kegiatan dengan usia, minat, dan kenyamanan anak.</p></div><div className="parent-idea-list">{ideas.length ? ideas.map((item) => <article key={item.id}><span className="parent-idea-icon"><Icon name="book" size={16} /></span><div><strong>{item.decision}</strong><small>{item.note}</small></div><Pill tone="sage">Dibagikan dokter</Pill></article>) : <p>Belum ada saran personal yang dibagikan untuk profil ini.</p>}</div></section>
    <div className="info-footnote"><Icon name="privacy" size={15} /><span>Akun keluarga tidak menampilkan skor domain, catatan internal, atau data milik anak lain.</span></div>
  </div>;
}

function QuarterlyReportPanel({ role, reports, observations, child, onCreate, onPublish }: LooseProps) {
  const isDoctor = role === 'doctor';
  const reportList = (reports || []).filter((report) => report.childId === child?.id);
  const now = Date.now();
  const currentStart = now - 90 * 24 * 60 * 60 * 1000;
  const previousStart = now - 180 * 24 * 60 * 60 * 1000;
  const childObservations = (observations || []).filter((item) => item.childId === child?.id && item.createdAt);
  const current = childObservations.filter((item) => { const time = Date.parse(item.createdAt); return Number.isFinite(time) && time >= currentStart && time <= now; });
  const previous = childObservations.filter((item) => { const time = Date.parse(item.createdAt); return Number.isFinite(time) && time >= previousStart && time < currentStart; });
  const countsFor = (list, aspect) => list.filter((item) => item.aspect === aspect);
  return <section className="panel quarterly-analytics-panel"><div className="quarterly-heading"><div><div className="eyebrow">Laporan tiga bulanan · 90 hari</div><h2>Ringkasan catatan individual</h2><p>{child?.name || 'Profil anak'} · hitungan catatan pengamatan, bukan skor perkembangan.</p></div><Button icon="report" onClick={onCreate}>Buat laporan 3 bulanan</Button></div>
    <div className="quarterly-domain-grid">{DEVELOPMENT_ASPECTS.map((aspect) => { const currentItems = countsFor(current, aspect.label); const previousItems = countsFor(previous, aspect.label); const observed = currentItems.filter((item) => item.result === 'Teramati').length; const notObserved = currentItems.filter((item) => item.result === 'Belum teramati').length; const noOpportunity = currentItems.filter((item) => item.result === 'Belum ada kesempatan').length; return <article className="quarterly-domain-card" key={aspect.id}><span>{aspect.label}</span><strong>{currentItems.length}</strong><small>catatan 90 hari terakhir · {previousItems.length} pada 90 hari sebelumnya</small><div>Teramati {observed} · Belum teramati {notObserved} · Belum ada kesempatan {noOpportunity}</div></article>; })}</div>
    <div className="quarterly-analytics-note"><Icon name="info" size={15} /><span>Perbandingan hanya menunjukkan frekuensi pencatatan. Sistem tidak menyimpulkan kemajuan, keterlambatan, atau usia perkembangan.</span></div>
    <div className="quarterly-report-list"><CardTitle eyebrow="Arsip dan alur tinjauan" title="Laporan untuk dibagikan" />{reportList.length ? reportList.map((report) => { const stats = report.observationStats || {}; return <article className="quarterly-report-row" key={report.id}><div className="quarterly-report-top"><Pill tone={report.published ? 'sage' : 'gold'} dot>{report.published ? 'Diterbitkan dokter' : isDoctor ? 'Menunggu tinjauan dokter' : 'Draf · menunggu dokter'}</Pill><small>{report.periodStart} – {report.periodEnd}</small></div><p>{report.summary}</p><small>{stats.total_observations || 0} observasi terhitung pada periode laporan.</small><div className="quarterly-report-actions">{isDoctor && !report.published && <Button size="small" icon="send" onClick={() => onPublish(report)}>Tinjau & bagikan</Button>}{report.published && <Pill tone="neutral">Terlihat oleh keluarga tertaut</Pill>}</div></article>; }) : <EmptyState icon="report" title="Belum ada laporan tiga bulanan" detail="Buat draf berdasarkan observasi yang tersimpan. Keluarga hanya akan melihatnya setelah dokter meninjau dan menerbitkan." action={<Button variant="outline" size="small" onClick={onCreate}>Buat draf laporan</Button>} />}</div>
  </section>;
}

function DevelopmentPage({ role, data, children, selectedId, setSelectedId, onGo, onNewObservation, onNewQuarterlyReport, onPublishQuarterlyReport, insightLoadState, insightLoadError, onRefreshInsights, onFeedback, onStartActivity }: LooseProps) {
  const child = children.find((entry) => entry.id === selectedId) || children[0];
  const selectedObservations = (data.observations || []).filter((item) => item.childId === child?.id);
  const selectedActivities = data.activities.filter((item) => item.childId === child?.id);
  const selectedAssessments = (data.assessments || []).filter((item) => item.childId === child?.id);
  const selectedReports = (data.developmentReports || []).filter((item) => item.childId === child?.id);
  const currentInsightMeta = data.insightMeta?.child_id === child?.id ? data.insightMeta : null;
  const currentInsights = currentInsightMeta ? (data.insights || []) : [];
  const evidence = [
    ...selectedObservations.map((item) => ({ key: item.id, title: item.milestone || `Pengamatan ${item.aspect}`, detail: `${item.aspect} · ${item.observer || 'Pengasuh'} · ${item.result}`, time: `${item.date} · ${item.time}`, icon: 'activity' })),
    ...selectedActivities.map((item) => ({ key: item.id, title: item.title, detail: `${item.source} · ${item.category} · ${item.shared ? 'dibagikan' : 'tidak dibagikan'}`, time: `${item.createdAt} · ${item.time}`, icon: 'book' })),
    ...selectedAssessments.map((item) => ({ key: item.id, title: `Pemeriksaan KPSP · ${item.screeningAgeMonths} bulan`, detail: item.published ? 'Ditinjau dan dibagikan dokter' : item.status === 'submitted' ? 'Menunggu tinjauan dokter' : 'Draft dokter', time: item.date, icon: 'clipboard' })),
  ].slice(0, 8);
  if (role === 'parent') {
    return <>
      <PageTitle eyebrow="Skrining & perkembangan anak · laporan keluarga" title="Laporan perkembangan anak" description="Ringkasan KPSP dan kegiatan yang telah ditinjau dokter." />
      <ParentDevelopmentReport data={data} child={child} onGo={onGo} />
    </>;
  }
  return <>
    <PageTitle eyebrow="Skrining & perkembangan anak · analitik per anak" title="Skrining, analitik, dan saran stimulasi" description="Satu halaman untuk melihat hasil KPSP, catatan pengamatan, serta ide kegiatan yang sesuai konteks anak." action={role === 'doctor' ? <Button icon="clipboard" onClick={() => onGo('kpsp')}>Input KPSP</Button> : <Button icon="plus" onClick={onNewObservation}>Catat pengamatan</Button>} />
    <div className="child-context-row"><span><Icon name="child" size={16} />Profil anak</span><select value={child?.id || ''} onChange={(event) => setSelectedId(event.target.value)} aria-label="Pilih profil anak">{children.map((entry) => <option value={entry.id} key={entry.id}>{entry.name} · {entry.ageMonths} bulan</option>)}</select><span className="context-divider" /><span><Icon name="calendar" size={16} />KPSP diinput dokter sesuai jadwal usia.</span></div>
    <section className="development-hero gradient-lilac"><div className="development-hero-copy"><Pill tone="plum" dot>{child?.name || 'Profil anak'} · {child?.ageMonths ?? '—'} bulan</Pill><h2>{selectedObservations.length ? 'Ringkasan berbasis catatan, tanpa skor perkembangan.' : 'Belum cukup catatan untuk ringkasan individual.'}</h2><p>Catatan diurutkan per aspek. Perubahan jumlah catatan tidak membuktikan kemajuan atau keterlambatan. Hasil KPSP tetap perlu tinjauan dokter.</p><div className="dev-hero-metrics"><div><strong>{selectedObservations.length}</strong><small>pengamatan tersimpan</small></div><span /><div><strong>{selectedAssessments.length}</strong><small>hasil KPSP yang boleh dilihat peran ini</small></div></div></div><div className="development-hero-visual"><div className="dev-chart-label"><span>CAKUPAN OBSERVASI</span><Pill tone="neutral">Data faktual</Pill></div><div className="development-aspect-list">{DEVELOPMENT_ASPECTS.map((aspect) => { const count = selectedObservations.filter((item) => item.aspect === aspect.label).length; return <div className="development-aspect-row" key={aspect.id}><span className={`aspect-status-mark aspect-status-${aspect.color}`}><Icon name={aspect.icon} size={15} /></span><strong>{aspect.label}</strong><span>{count} catatan</span></div>; })}</div><p className="dev-chart-caption">KPSP skrining, bukan diagnosis.</p></div></section>
    <div className="domain-grid">{DEVELOPMENT_ASPECTS.map((aspect) => { const rows = selectedObservations.filter((item) => item.aspect === aspect.label); const observed = rows.filter((item) => item.result === 'Teramati').length; const notObserved = rows.filter((item) => item.result === 'Belum teramati').length; const noOpportunity = rows.filter((item) => item.result === 'Belum ada kesempatan').length; return <article className={`domain-card domain-${aspect.color}`} key={aspect.id}><div className="domain-card-head"><span className={`domain-bullet bullet-${aspect.color}`}><Icon name={aspect.icon} size={17} /></span><Pill tone="neutral">{rows.length} catatan</Pill></div><h3>{aspect.label}</h3><div className="domain-score"><strong>{observed} teramati · {notObserved} belum</strong><span>{noOpportunity} belum ada kesempatan</span></div><div className="domain-evidence-state"><i className={rows.length ? 'evidence-state-present' : ''} />Jumlah catatan tersimpan; bukan skor.</div><div className="domain-card-foot"><span>Tanpa kesimpulan otomatis</span><button className="text-link" onClick={onNewObservation}>Catat observasi <Icon name="arrow" size={14} /></button></div></article>; })}</div>
    <section className="panel local-insights-panel"><CardTitle eyebrow="Insight lokal · tanpa API AI eksternal" title="Saran berbasis catatan pengamatan" action={<Pill tone={currentInsightMeta?.ml_demo_enabled ? 'plum' : 'gold'}>{currentInsightMeta?.ml_demo_enabled ? 'ML demo · data sintetis' : 'Aturan lokal · tanpa model klinis'}</Pill>} /><p>{currentInsightMeta?.method || 'Ringkasan memakai aturan lokal transparan. Model klinis tervalidasi tidak tersedia.'}</p><SyntheticDemoNotice insightMeta={currentInsightMeta} />{insightLoadState === 'ready' ? currentInsights.length ? <LocalInsightCards insights={currentInsights} role={role} /> : <EmptyState icon="spark" title="Belum ada hasil saran" detail="Insight berhasil dimuat, tetapi belum ada aspek yang dapat ditampilkan. Coba muat ulang atau periksa catatan." action={<Button size="small" variant="outline" onClick={onRefreshInsights}>Muat ulang</Button>} /> : insightLoadState === 'error' ? <InsightLoadMessage status="error" error={insightLoadError} onRetry={onRefreshInsights} /> : insightLoadState === 'loading' ? <InsightLoadMessage status="loading" /> : <EmptyState icon="spark" title="Menunggu profil anak" detail="Pilih profil anak untuk memuat catatan dan saran." />}<div className="insight-estimate-note"><span><Pill tone="neutral">Estimasi perkembangan</Pill><strong>Belum dapat dihitung dengan aman</strong></span><p>{currentInsightMeta?.trend_estimate || 'Frekuensi catatan saja tidak cukup untuk mengestimasi perkembangan anak.'}</p></div><div className="quarterly-analytics-note"><Icon name="info" size={15} /><span>{currentInsightMeta?.clinical_boundary || 'Ide aktivitas bukan terapi/diagnosis. Tidak ada estimasi usia perkembangan klinis atau model klinis tervalidasi.'}</span></div></section>
    {insightLoadState === 'ready' && <PersonalizedStimulation data={currentInsightMeta} child={child} onFeedback={onFeedback} onStartActivity={onStartActivity} readOnly={role === 'doctor'} />}
    <QuarterlyReportPanel role={role} reports={selectedReports} observations={selectedObservations} child={child} onCreate={onNewQuarterlyReport} onPublish={onPublishQuarterlyReport} />
    <div className="dashboard-grid development-lower-grid"><section className="panel evidence-panel"><CardTitle eyebrow="Catatan tersimpan" title="Pengamatan, kegiatan, dan KPSP" />{evidence.length ? <div className="evidence-list">{evidence.map((item) => <div className="evidence-row" key={item.key}><span className="evidence-icon"><Icon name={item.icon} size={16} /></span><div><strong>{item.title}</strong><small>{item.detail}</small></div><time>{item.time}</time></div>)}</div> : <EmptyState icon="activity" title="Belum ada catatan untuk profil ini" detail="Observasi milestone dan KPSP yang tersimpan akan muncul di sini." action={role === 'caregiver' ? <Button variant="outline" size="small" onClick={onNewObservation}>Catat pengamatan</Button> : <Button variant="outline" size="small" onClick={() => onGo('kpsp')}>Buka formulir KPSP</Button>} />}<div className="evidence-footer"><Icon name="info" size={15} /><span>Orang tua dan pengasuh hanya menerima ringkasan KPSP setelah ditinjau dan diterbitkan dokter.</span></div></section><section className="panel review-gate-panel"><Pill tone="plum">Tinjauan dokter</Pill><h3>Laporan dibagikan hanya setelah ditinjau.</h3><p>Orang tua tidak melihat jawaban mentah KPSP atau observasi internal.</p>{role === 'doctor' ? <Button variant="outline" size="small" onClick={() => onGo('queue')}>Buka antrean KPSP</Button> : <Button variant="outline" size="small" onClick={() => onGo('reports')}>Lihat laporan</Button>}</section></div>
  </>;
}

function QueuePage({ data, search = '', onOpenReview }: LooseProps) {
  const [filter, setFilter] = useState('Menunggu');
  const reviewItems = data.queue.filter((item) => data.consents[item.childId] !== false);
  const query = search.trim().toLocaleLowerCase('id-ID');
  const filtered = reviewItems
    .filter((item) => filter === 'Semua' || (filter === 'Menunggu' ? !item.reviewed : item.reviewed))
    .filter((item) => {
      if (!query) return true;
      const childName = data.children.find((entry) => entry.id === item.childId)?.name || '';
      return `${childName} ${item.domain} ${item.reason}`.toLocaleLowerCase('id-ID').includes(query);
    });
  const waitingCount = reviewItems.filter((item) => !item.reviewed).length;
  const submittedCount = reviewItems.filter((item) => item.assessmentId && !item.reviewed).length;
  const draftCount = data.assessments.filter((item) => item.status === 'draft').length;
  return (
    <>
      <PageTitle eyebrow="Ruang dokter" title="Hasil pemeriksaan untuk ditinjau" description="KPSP adalah skrining, bukan diagnosis. Dokter meninjau hasil dan menulis ringkasan sebelum membagikannya kepada keluarga." action={<Pill tone="plum" dot>Tinjauan dokter</Pill>} />
      <div className="queue-summary-strip gradient-lilac"><div><span className="summary-icon"><Icon name="review" size={20} /></span><span><strong>{waitingCount} hasil menunggu</strong><small>Perlu dibaca dokter.</small></span></div><div><span className="summary-icon summary-icon-warm"><Icon name="clipboard" size={20} /></span><span><strong>{submittedCount} KPSP menunggu</strong><small>{draftCount} jawaban sementara belum dikirim.</small></span></div><div className="queue-summary-note"><Icon name="info" size={16} /><span>Hasil yang belum ditinjau tidak terlihat oleh keluarga.</span></div></div>
      <section className="panel queue-panel"><div className="queue-toolbar"><CardTitle eyebrow="Daftar tinjauan" title="Pemeriksaan yang dikirim" /><div className="filter-tabs" role="group" aria-label="Filter status tinjauan">{['Menunggu', 'Sudah ditinjau', 'Semua'].map((item) => <button key={item} className={filter === item ? 'filter-active' : ''} onClick={() => setFilter(item)}>{item}</button>)}</div></div>
        {filtered.length ? <div className="queue-list">{filtered.map((item) => {
          const child = data.children.find((entry) => entry.id === item.childId);
          const score = item.kpspResult;
          return <button className={`queue-row full-queue-row ${item.reviewed ? 'queue-reviewed' : ''}`} key={item.id} onClick={() => onOpenReview(item)}><span className={`queue-priority ${item.reviewed ? 'priority-reviewed' : ''}`}><Icon name={item.reviewed ? 'check' : 'review'} size={17} /></span><span className="queue-row-main"><strong>{child?.name || 'Profil anak'} <span>· {item.domain}</span></strong><small>{score ? `${score.result_label} · ${score.yes_count}/${score.total_items} jawaban Ya. Hasil skrining, bukan diagnosis.` : 'Hasil menunggu tinjauan dokter.'}</small><small className="queue-meta">Usia anak {item.actualAgeMonths ?? item.ageMonths} bulan · {item.date}</small></span><span className="queue-row-end"><Pill tone={item.reviewed ? 'sage' : 'plum'}>{item.reviewed ? 'Sudah ditinjau' : 'Menunggu'}</Pill><Icon name="chevron" size={17} /></span></button>;
        })}</div> : <EmptyState icon="check" title={query ? 'Tidak ada hasil yang cocok' : 'Belum ada hasil untuk ditinjau'} detail={query ? 'Ubah kata kunci atau pilih tampilan lain.' : 'Hasil KPSP yang dikirim akan muncul di sini.'} />}
      </section>
      <div className="info-footnote"><Icon name="privacy" size={16} /><span>Hasil skrining tidak memastikan kondisi anak. Penjelasan dan tindak lanjut ditentukan dokter.</span></div>
    </>
  );
}

function SensorHistoryChart({ readings = [] }: { readings: DashboardRecord[] }): React.JSX.Element {
  const coordinates = (values: number[]) => {
    if (!values.length) return [];
    const min = Math.min(...values);
    const max = Math.max(...values);
    const range = max - min || 1;
    return values.map((value, index) => ({ x: values.length === 1 ? 150 : 12 + (index / (values.length - 1)) * 276, y: 92 - ((value - min) / range) * 62 }));
  };
  const temperatures = coordinates(readings.map((item) => Number(item.temperature)));
  const humidities = coordinates(readings.map((item) => Number(item.humidity)));
  const pointString = (points: Array<{ x: number; y: number }>) => points.map((point) => `${point.x},${point.y}`).join(' ');
  return <svg className="sensor-history-chart" viewBox="0 0 300 110" role="img" aria-label="Riwayat suhu dan kelembapan yang dikirim sensor">
    {[24, 55, 86].map((y) => <line key={y} x1="8" x2="292" y1={y} y2={y} stroke="#dfe7df" strokeDasharray="3 5" />)}
    {temperatures.length > 0 && <><polyline points={pointString(temperatures)} fill="none" stroke="#3e8067" strokeWidth="3" strokeLinecap="round" strokeLinejoin="round" />{temperatures.map((point, index) => <circle key={`t-${index}`} cx={point.x} cy={point.y} r={index === temperatures.length - 1 ? 3.4 : 2.3} fill="#3e8067" />)}</>}
    {humidities.length > 0 && <><polyline points={pointString(humidities)} fill="none" stroke="#8b6aab" strokeWidth="2.5" strokeDasharray="5 4" strokeLinecap="round" strokeLinejoin="round" />{humidities.map((point, index) => <circle key={`h-${index}`} cx={point.x} cy={point.y} r={index === humidities.length - 1 ? 3.2 : 2} fill="#8b6aab" />)}</>}
  </svg>;
}

function SensorPage({ data, role }: LooseProps) {
  const sensor = data.sensor || {};
  const [deviceId, setDeviceId] = useState('');
  const [roomId, setRoomId] = useState('');
  const [registrationError, setRegistrationError] = useState('');
  const [registrationBusy, setRegistrationBusy] = useState(false);
  const [oneTimeSensorKey, setOneTimeSensorKey] = useState('');
  const hasReading = Boolean(sensor.connected && Number.isFinite(sensor.temperature) && Number.isFinite(sensor.humidity));
  const statusLabel = sensor.fresh ? 'Data langsung' : hasReading ? 'Pembacaan terakhir' : 'Menunggu perangkat';
  const registerDevice = async (event) => {
    event.preventDefault();
    setRegistrationError('');
    setOneTimeSensorKey('');
    setRegistrationBusy(true);
    try {
      const response = await apiPost('sensors/devices', { device_id: deviceId.trim(), room_id: roomId.trim() });
      setOneTimeSensorKey(response.sensor_key);
      setDeviceId('');
      setRoomId('');
    } catch (cause) {
      setRegistrationError(cause instanceof ApiError ? cause.message : 'Perangkat belum dapat didaftarkan.');
    } finally {
      setRegistrationBusy(false);
    }
  };
  const readings = sensor.readings || [];
  return (
    <>
      <PageTitle eyebrow="SmartDayCare AI · kondisi ruang" title="Suhu dan kelembapan daycare" description="Nilai hanya berasal dari pembacaan perangkat tersimpan. Jika alat belum mengirim data, angka tidak akan diperkirakan." action={<Pill tone={sensor.fresh ? 'sage' : hasReading ? 'gold' : 'neutral'} dot>{statusLabel}</Pill>} />
      {role === 'admin' && <section className="panel sensor-device-registration"><CardTitle eyebrow="Provisioning tenant" title="Daftarkan perangkat sensor" /><p className="page-description">Setiap kunci terikat ke satu daycare dan ruang, disimpan sebagai hash, lalu hanya ditampilkan sekali. Kirimkan melalui kanal aman ke perangkat.</p><form className="form-grid" onSubmit={registerDevice}><label className="field"><span>ID perangkat unik</span><input value={deviceId} onChange={(event) => setDeviceId(event.target.value)} maxLength={80} required /></label><label className="field"><span>Ruang</span><input value={roomId} onChange={(event) => setRoomId(event.target.value)} maxLength={80} required /></label><div className="field-full"><Button type="submit" icon="plus" disabled={registrationBusy}>{registrationBusy ? 'Mendaftarkan…' : 'Daftarkan perangkat'}</Button></div></form>{registrationError && <p className="form-error" role="alert">{registrationError}</p>}{oneTimeSensorKey && <div className="sensor-key-once" role="status"><strong>Kunci sensor — tampilkan dan salin sekarang</strong><code>{oneTimeSensorKey}</code><small>Kunci tidak akan disimpan ulang atau ditampilkan kembali. Jangan kirim lewat chat publik.</small></div>}</section>}
      <section className={`sensor-hero ${hasReading ? 'gradient-cool' : 'sensor-offline'}`}> 
        <div className="sensor-hero-main">
          <div className="sensor-hero-top"><span className="sensor-large-icon"><Icon name="sensor" size={22} /></span><Pill tone={sensor.fresh ? 'sage' : hasReading ? 'gold' : 'neutral'} dot>{statusLabel}</Pill></div>
          <h2>{hasReading ? `${sensor.roomId || 'Ruang daycare'} · pembacaan terbaru` : 'Belum ada pembacaan'}</h2>
          <p>Data berasal dari sensor ruang, bukan kamera atau pengukuran kondisi anak. Pembacaan usang tetap ditandai.</p>
          <div className="sensor-reading-grid">
            <div className="sensor-reading"><span><Icon name="sun" size={16} />Suhu ruang</span><strong>{hasReading ? `${sensor.temperature.toFixed(1)}°C` : '--'}</strong><small>{hasReading ? `Diukur ${sensor.updatedAt || 'waktu tidak tersedia'}` : 'Belum tersedia'}</small></div>
            <div className="sensor-reading"><span><Icon name="drop" size={16} />Kelembapan</span><strong>{hasReading ? `${sensor.humidity.toFixed(1)}%` : '--'}</strong><small>{hasReading ? sensor.fresh ? 'Dikirim dalam 15 menit terakhir' : 'Data tidak diperbarui dalam 15 menit' : 'Belum tersedia'}</small></div>
          </div>
          <div className="sensor-actions"><span>{hasReading ? `Perangkat ${sensor.deviceId || 'sensor'} · ruang ${sensor.roomId || 'belum diberi nama'}` : 'Menunggu perangkat sensor mengirim pembacaan pertama.'}</span></div>
        </div>
        <div className="sensor-hero-chart">
          <div className="chart-header"><div><small>Riwayat sensor</small><strong>{hasReading && readings.length ? `${readings.length} pembacaan terakhir` : 'Belum tersedia'}</strong></div><Pill tone="neutral">{sensor.roomId || 'Ruang daycare'}</Pill></div>
          {hasReading && readings.length ? <><SensorHistoryChart readings={readings} /><div className="chart-axis"><span>{readings.length > 1 ? 'Lebih lama' : 'Satu pembacaan'}</span><span>Terbaru</span></div><div className="chart-legend"><span><i className="legend-dot legend-temp" />suhu (skala tren)</span><span><i className="legend-dot legend-hum" />kelembapan (skala tren)</span></div></> : <EmptyState icon="sensor" title="Belum ada data dari alat" detail="Riwayat akan tampil setelah perangkat mengirim pembacaan yang terautentikasi." />}
        </div>
      </section>
      <div className="dashboard-grid sensor-grid">
        <section className="panel"><CardTitle eyebrow="Status perangkat" title={sensor.fresh ? 'Data sensor masih baru' : hasReading ? 'Pembacaan perlu diperbarui' : 'Menunggu sensor'} /><EmptyState icon={sensor.fresh ? 'check' : 'sensor'} title={sensor.fresh ? 'Perangkat mengirim data' : hasReading ? 'Belum ada pembaruan sensor' : 'Belum ada data yang perlu diperiksa'} detail={sensor.fresh ? 'Waktu, suhu, dan kelembapan tercatat dari pembacaan perangkat.' : hasReading ? `Data terakhir diukur ${sensor.updatedAt || 'pada waktu yang tidak tersedia'}. Periksa koneksi alat.` : 'Tidak ada nilai contoh yang ditampilkan; panel akan terisi setelah sensor terhubung.'} /></section>
        <section className="panel baseline-panel"><CardTitle eyebrow="Informasi yang dicatat" title="Sumber kondisi ruang" /><div className="baseline-list"><div><span className="baseline-icon"><Icon name="sun" size={17} /></span><span><strong>Suhu ruang</strong><small>Angka dari alat pengukur yang terhubung.</small></span></div><div><span className="baseline-icon"><Icon name="drop" size={17} /></span><span><strong>Kelembapan</strong><small>Dicatat bersama waktu pengukuran.</small></span></div><div><span className="baseline-icon"><Icon name="clock" size={17} /></span><span><strong>Waktu pembacaan</strong><small>Menunjukkan kapan data terakhir diterima.</small></span></div></div></section>
      </div>
      <section className="panel device-health-panel"><CardTitle eyebrow="Sumber informasi" title={hasReading ? `Sensor ${sensor.deviceId || ''}` : 'Menunggu perangkat sensor'} action={<Pill tone={sensor.fresh ? 'sage' : 'neutral'}>{sensor.fresh ? 'Aktif' : hasReading ? 'Perlu diperiksa' : 'Belum terhubung'}</Pill>} /><div className="device-info-grid"><div><small>Lokasi</small><strong>{sensor.roomId || 'Belum ditentukan'}</strong></div><div><small>Data terakhir</small><strong>{sensor.updatedAt || 'Belum tersedia'}</strong></div><div><small>Jenis pengukuran</small><strong>Suhu dan kelembapan</strong></div><div><small>Status</small><strong>{sensor.fresh ? 'Diperbarui ≤15 menit' : hasReading ? 'Data lama' : 'Belum terhubung'}</strong></div></div><div className="device-note"><Icon name="info" size={16} /><span>Setiap perangkat harus didaftarkan pada satu daycare melalui endpoint admin POST /api/sensors/devices. Kunci unik dikembalikan sekali; pembacaan dikirim ke POST /api/sensors/readings memakai X-Sensor-Key. Kunci lama global tidak digunakan.</span></div></section>
    </>
  );
}

function RecommendationsPage({ role, data, children, selectedId, setSelectedId, onStartActivity, onNewObservation, onGo, insightLoadState, insightLoadError, insightStatusChildId, onRefreshInsights, onFeedback }: LooseProps) {
  const isParent = role === 'parent';
  const child = children.find((entry) => entry.id === selectedId) || children[0];
  const currentInsightMeta = !isParent && data.insightMeta?.child_id === child?.id ? data.insightMeta : null;
  const currentInsights = currentInsightMeta ? (data.insights || []) : [];
  const currentLoadState = insightStatusChildId === child?.id ? insightLoadState : child ? 'loading' : 'idle';
  const currentLoadError = insightStatusChildId === child?.id ? insightLoadError : '';
  const visibleIds = new Set(children.map((entry) => entry.id));
  const hasEnabledSuggestions = children.some((entry) => data.consents[entry.id] === true);
  const reviewedSuggestions = data.queue.filter((item) => item.reviewed && item.published && item.decision === 'Berikan kegiatan stimulasi umum');
  const published = isParent
    ? reviewedSuggestions.filter((item) => visibleIds.has(item.childId) && data.consents[item.childId] === true)
    : role === 'doctor' ? reviewedSuggestions : [];
  const description = isParent
    ? 'Saran khusus hanya muncul setelah dokter meninjau dan membagikannya. Orang tua tidak melihat observasi internal atau jawaban KPSP mentah.'
    : role === 'doctor'
      ? 'Tinjau bukti yang tercatat dan gunakan panduan lokal sebagai bahan kerja, bukan keputusan otomatis.'
      : 'Saran lokal kini memakai hitungan observasi faktual. Catatan kosong memberi ide umum dan menjelaskan data apa yang perlu dicatat.';
  return <>
    <PageTitle
      eyebrow={isParent ? 'Untuk keluarga' : 'Insight lokal · aturan transparan'}
      title={isParent ? 'Ide kegiatan untuk di rumah' : 'Saran untuk pengasuh dan dokter'}
      description={description}
      action={role === 'doctor'
        ? <Button variant="outline" onClick={() => onGo('queue')}>Buka hasil tinjauan</Button>
        : role === 'caregiver' ? <Button icon="plus" onClick={onNewObservation}>Catat observasi</Button> : null}
    />
    {!isParent && <div className="child-context-row"><span><Icon name="child" size={16} />Profil anak</span><select value={child?.id || ''} onChange={(event) => setSelectedId(event.target.value)} aria-label="Pilih profil anak untuk saran">{children.map((entry) => <option value={entry.id} key={entry.id}>{entry.name} · {entry.ageMonths} bulan</option>)}</select><span className="context-divider" /><span><Icon name="calendar" size={16} />Rentang data: {currentInsightMeta?.period_start || '90 hari terakhir'}</span></div>}
    {!isParent && <section className="panel local-insights-panel recommendation-insights-panel">
      <CardTitle eyebrow={role === 'doctor' ? 'Bukti observasi · tinjauan klinis tetap oleh dokter' : 'Langkah praktis · untuk sesi pengasuh'} title="Saran lokal berdasarkan catatan yang ada" action={<Pill tone={currentInsightMeta?.ml_demo_enabled ? 'plum' : 'gold'}>{currentInsightMeta?.ml_demo_enabled ? `ML demo · ${currentInsightMeta.ml_demo_training_examples} skenario sintetis` : `${currentInsightMeta?.engine || 'Aturan lokal'} · tanpa model klinis`}</Pill>} />
      <p>{currentInsightMeta?.method || 'Sistem memakai aturan lokal deterministik, bukan API AI eksternal. Jika belum ada observasi, ide di bawah diberi label umum dan belum personal.'}</p>
      <SyntheticDemoNotice insightMeta={currentInsightMeta} />
      {currentLoadState === 'ready'
        ? currentInsights.length ? <LocalInsightCards insights={currentInsights} role={role} /> : <EmptyState icon="spark" title="Belum ada saran yang dapat ditampilkan" detail="Insight berhasil dimuat tetapi tidak berisi aspek. Coba muat ulang atau buka analitik perkembangan." action={<Button size="small" variant="outline" onClick={onRefreshInsights}>Muat ulang</Button>} />
        : currentLoadState === 'error' ? <InsightLoadMessage status="error" error={currentLoadError} onRetry={onRefreshInsights} />
          : currentLoadState === 'loading' ? <InsightLoadMessage status="loading" />
            : <EmptyState icon="child" title="Pilih profil anak" detail="Pilih profil untuk memuat catatan dan saran lokal." />}
      <div className="quarterly-analytics-note"><Icon name="info" size={15} /><span>{currentInsightMeta?.clinical_boundary || 'Saran bukan diagnosis atau skrining. Hitungan catatan bukan ukuran kemampuan; bila ada kekhawatiran, tindak lanjut ditentukan dokter.'}</span></div>
    </section>}
    {!isParent && currentLoadState === 'ready' && <PersonalizedStimulation data={currentInsightMeta} child={child} onFeedback={onFeedback} onStartActivity={onStartActivity} readOnly={role === 'doctor'} />}
    {(isParent || role === 'doctor') && <section className="panel recommendation-list-panel">
      <CardTitle eyebrow={isParent ? 'Tinjauan dokter yang dibagikan' : 'Rekomendasi tinjauan yang sudah diterbitkan'} title={isParent ? 'Saran yang dibagikan dokter' : 'Saran dokter untuk keluarga'} />
      {published.length ? <div className="recommendation-grid">{published.map((item) => <article className="recommendation-card" key={item.id}>
        <div className="rec-card-top"><span className="domain-pill">{item.domain}</span><Pill tone="sage">Dibagikan dokter</Pill></div>
        <h3>{item.decision}</h3><p>{item.note}</p>
        <div className="rec-card-footer"><span>Dibagikan {item.date}</span>{role === 'caregiver' ? <Button size="small" variant="outline" onClick={() => onStartActivity(item.decision)}>Catat kegiatan</Button> : <Pill tone="neutral">Saran umum</Pill>}</div>
      </article>)}</div> : <EmptyState icon="book" title="Belum ada saran dokter yang dibagikan" detail={isParent ? (hasEnabledSuggestions ? 'Saran akan muncul setelah dokter meninjau dan membagikannya.' : 'Aktifkan tampilan saran di bagian Izin & data saya untuk membaca saran dokter.') : 'Saran terbit akan muncul di sini setelah dokter meninjau dan membagikan ringkasan.'} />}
    </section>}
    <section className="notice-strip"><Icon name="info" size={18} /><div><strong>Saran ini bukan diagnosis, terapi, atau skrining.</strong><span>Ikuti kenyamanan anak. Hasil dan tindak lanjut klinis hanya ditentukan dokter setelah meninjau informasi yang relevan.</span></div></section>
  </>;
}

function MessagesPage({ role, data, children, onAnnounce, onReminder, onSendDirectMessage, onOpenNotification, onMarkNotificationRead, onCompleteReminder, onRequestBrowserNotifications, notificationPermission, requestedChildId, requestedContactId, onTargetConsumed }: LooseProps) {
  const isParent = role === 'parent';
  const linkedIds = new Set((data.linkedChildIds || []).map(String));
  const availableChildren = isParent
    ? children
    : children.filter((child) => linkedIds.has(String(child.id)));
  const [selectedChildId, setSelectedChildId] = useState('');
  const childKey = availableChildren.map((child) => child.id).join('|');
  const activeChildId = availableChildren.some((child) => child.id === selectedChildId)
    ? selectedChildId
    : availableChildren[0]?.id || '';
  const activeChild = availableChildren.find((child) => child.id === activeChildId);
  const [view, setView] = useState('conversation');
  const [contacts, setContacts] = useState([]);
  const [selectedContactId, setSelectedContactId] = useState('');
  const [contactsError, setContactsError] = useState('');
  const [reply, setReply] = useState('');
  const [replyError, setReplyError] = useState('');
  const [sendingReply, setSendingReply] = useState(false);
  const threadEndRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    if (requestedChildId && availableChildren.some((child) => child.id === requestedChildId)) {
      setSelectedChildId(requestedChildId);
    }
  }, [requestedChildId, childKey]);

  useEffect(() => {
    let active = true;
    setContacts([]);
    setSelectedContactId('');
    setContactsError('');
    if (!activeChildId) return () => { active = false; };
    apiGet(`messages/contacts?child_id=${encodeURIComponent(activeChildId)}`)
      .then((payload) => {
        if (!active) return;
        const nextContacts = payload.contacts || [];
        setContacts(nextContacts);
        setSelectedContactId((current) => nextContacts.some((contact) => contact.id === current) ? current : (nextContacts[0]?.id || ''));
      })
      .catch((cause) => {
        if (!active) return;
        setContactsError(cause instanceof ApiError ? cause.message : 'Kontak belum dapat dimuat. Coba lagi.');
      });
    return () => { active = false; };
  }, [activeChildId, role]);

  useEffect(() => {
    if (!requestedContactId || !contacts.length || (requestedChildId && activeChildId !== requestedChildId)) return;
    if (contacts.some((contact) => contact.id === requestedContactId)) {
      setSelectedContactId(requestedContactId);
      setView('conversation');
      onTargetConsumed?.();
    }
  }, [requestedContactId, requestedChildId, activeChildId, contacts, onTargetConsumed]);

  const selectedContact = contacts.find((contact) => contact.id === selectedContactId);
  const visibleIds = new Set(children.map((child) => child.id));
  const visibleNotifications = (data.notifications || []).filter((item) => !isParent || item.childId == null || visibleIds.has(item.childId));
  const unreadNotifications = visibleNotifications.filter((item) => !item.readAt).length;
  const categoryLabel = (category: string) => ({ photo: 'Foto kegiatan', activity: 'Catatan kegiatan', message: 'Pesan', reminder: 'Pengingat' }[category] || 'Pemberitahuan');
  const categoryEmoji = (category: string) => ({ photo: '📷', activity: '🌱', message: '💬', reminder: '⏰' }[category] || '🔔');
  const displayTime = (value: string) => value ? new Intl.DateTimeFormat('id-ID', { day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit', timeZone: 'Asia/Jakarta' }).format(new Date(value)) : 'Waktu tidak tersedia';
  const threadMessages = data.messages.filter((message) => {
    if (!activeChildId || !selectedContact) return false;
    if (message.childId !== activeChildId && message.childId !== 'all') return false;
    if (message.isDirect) return message.senderId === selectedContact.id || message.recipientId === selectedContact.id;
    const legacyFamilyThread = (role === 'parent' && selectedContact.role === 'caregiver')
      || (role === 'caregiver' && selectedContact.role === 'parent');
    return legacyFamilyThread;
  }).slice().sort((a, b) => {
    const first = Date.parse(a.createdAt || '') || 0;
    const second = Date.parse(b.createdAt || '') || 0;
    return first - second;
  });

  useEffect(() => {
    threadEndRef.current?.scrollIntoView({ behavior: 'smooth', block: 'end' });
  }, [threadMessages.length, selectedContactId, activeChildId]);

  const submitReply = async (event) => {
    event.preventDefault();
    if (!reply.trim() || sendingReply || !activeChildId || !selectedContactId) return;
    setSendingReply(true);
    setReplyError('');
    const sent = await onSendDirectMessage({ childId: activeChildId, recipientId: selectedContactId, text: reply.trim() });
    if (sent) setReply('');
    else setReplyError('Pesan belum tersimpan. Periksa sambungan dan kontak, lalu coba lagi.');
    setSendingReply(false);
  };

  const roleLabel = (value: string) => ({ parent: 'Orang tua', caregiver: 'Pengasuh', doctor: 'Dokter' }[value] || 'Tim Rumah Kecilku');
  const currentUserOwnsMessage = (message) => message.isDirect
    ? message.senderId !== selectedContact?.id
    : message.role === role;
  const childName = activeChild?.name || 'profil anak terhubung';

  return (
    <>
      <PageTitle
        eyebrow={isParent ? 'Komunikasi & kabar daycare' : 'Komunikasi lintas peran'}
        title={isParent ? 'Pesan untuk tim anak' : 'Pesan dan kontak'}
        description="Pilih profil dan orang yang dituju. Pesan, kabar kegiatan yang dibagikan, dan pembaruan penting tersimpan dalam percakapan serta pemberitahuan."
        action={role === 'caregiver' && <div className="message-title-actions"><Button variant="outline" icon="clock" onClick={onReminder}>Buat pengingat</Button><Button icon="plus" onClick={onAnnounce}>Tulis pengumuman</Button></div>}
      />
      <div className="message-center-tabs" role="tablist" aria-label="Pusat komunikasi">
        <button role="tab" aria-selected={view === 'conversation'} className={view === 'conversation' ? 'message-center-tab active' : 'message-center-tab'} onClick={() => setView('conversation')}>💬 Percakapan</button>
        <button role="tab" aria-selected={view === 'notifications'} className={view === 'notifications' ? 'message-center-tab active' : 'message-center-tab'} onClick={() => setView('notifications')}>🔔 Pemberitahuan <span>{unreadNotifications}</span></button>
      </div>
      <div className="messages-layout">
        {view === 'conversation' ? <div className="conversation-workspace">
          <aside className="panel chat-contacts-panel">
            {availableChildren.length > 1 && <label className="field chat-child-field"><span>Profil anak</span><select value={activeChildId} onChange={(event) => setSelectedChildId(event.target.value)}>{availableChildren.map((child) => <option key={child.id} value={child.id}>{child.name}</option>)}</select></label>}
            <div className="chat-contacts-heading"><Pill tone="plum" dot>Kontak terhubung</Pill><h2>Siapa yang ingin dihubungi?</h2><p>Kontak ditampilkan berdasarkan profil anak yang dipilih.</p></div>
            {contactsError && <div className="form-error" role="status">{contactsError}</div>}
            {contacts.length ? <div className="chat-contact-list">{contacts.map((contact) => <button key={contact.id} type="button" className={`chat-contact ${selectedContactId === contact.id ? 'chat-contact-active' : ''}`} onClick={() => setSelectedContactId(contact.id)} aria-pressed={selectedContactId === contact.id}><span className={`chat-contact-avatar contact-${contact.role}`}>{contact.name?.trim()?.charAt(0)?.toUpperCase() || 'R'}</span><span className="chat-contact-copy"><strong>{contact.name}</strong><small>{roleLabel(contact.role)}</small></span><Icon name="chevron" size={16} /></button>)}</div> : <EmptyState icon="message" title={activeChildId ? 'Belum ada kontak terhubung' : 'Belum ada profil terhubung'} detail={activeChildId ? 'Minta daycare menautkan keluarga dan tim pada profil ini.' : 'Pesan akan tersedia setelah profil anak terhubung.'} />}
            {childKey && availableChildren.length === 1 && <small className="chat-child-caption">Profil: <strong>{childName}</strong></small>}
          </aside>
          <section className="panel messages-panel">
            <div className="messages-panel-head"><div><Pill tone="neutral" dot>Ruang percakapan</Pill><h2>{selectedContact ? selectedContact.name : 'Pilih kontak untuk mulai'}</h2>{selectedContact && <small>{roleLabel(selectedContact.role)} · {childName}</small>}</div><span className="messages-date">{shortDateLabel}</span></div>
            <div className="message-thread" aria-live="polite">
              {threadMessages.length ? threadMessages.map((message) => {
                const ownMessage = currentUserOwnsMessage(message);
                const eventMessage = message.isDirect && message.kind !== 'Pesan langsung';
                return <article className={`chat-message ${ownMessage ? 'chat-message-self' : ''} ${eventMessage ? 'chat-message-event' : ''}`} key={message.id}>
                  <span className={`chat-avatar chat-avatar-${message.role}`}>{message.author?.trim()?.charAt(0)?.toUpperCase() || 'R'}</span>
                  <div className="chat-bubble-wrap"><div className="chat-meta"><strong>{ownMessage ? 'Anda' : message.author}</strong><span>{message.createdAt ? displayTime(message.createdAt) : message.time}</span><Pill tone={eventMessage ? 'plum' : message.kind === 'Pengumuman' ? 'warm' : 'neutral'}>{message.kind}</Pill></div>
                    <div className="chat-bubble"><p>{message.text}</p>{eventMessage && <small>Notifikasi otomatis · {childName}</small>}{message.childId === 'all' && <small>Untuk keluarga yang terhubung</small>}</div>
                  </div>
                </article>;
              }) : <EmptyState icon="message" title={selectedContact ? 'Belum ada pesan di percakapan ini' : 'Pilih kontak terlebih dahulu'} detail={selectedContact ? 'Kirim pesan pertama, atau tunggu kabar kegiatan dan pembaruan otomatis yang relevan.' : 'Pilih kontak dari daftar untuk melihat atau mengirim pesan.'} />}
              <div ref={threadEndRef} />
            </div>
            {selectedContact ? <form className="reply-composer" onSubmit={submitReply}><label className="sr-only" htmlFor="chat-message-input">Tulis pesan ke {selectedContact.name}</label><textarea id="chat-message-input" value={reply} onChange={(event) => setReply(event.target.value)} placeholder={`Tulis pesan untuk ${selectedContact.name}…`} maxLength={2000} rows={2} /><Button type="submit" icon="send" disabled={!reply.trim() || sendingReply}>{sendingReply ? 'Mengirim…' : 'Kirim'}</Button>{replyError && <span className="form-error" role="alert">{replyError}</span>}</form> : <div className="messages-footer-note"><Icon name="info" size={15} /><span>Pilih kontak terhubung untuk mengirim pesan langsung.</span></div>}
            <div className="messages-footer-note"><Icon name="info" size={15} /><span>Notifikasi chat tersimpan dan diperbarui otomatis saat aplikasi terbuka. Push browser saat aplikasi tertutup belum tersedia.</span></div>
          </section>
        </div> : <section className="panel notifications-center-panel"><div className="notification-center-heading"><div><Pill tone="plum" dot>Pemberitahuan tersimpan</Pill><h2>{unreadNotifications ? `${unreadNotifications} belum dibaca` : 'Semua kabar sudah diperiksa'}</h2><small>Daftar diperbarui otomatis saat aplikasi terbuka.</small></div><Button variant={notificationPermission === 'granted' ? 'soft' : 'outline'} size="small" icon="bell" onClick={onRequestBrowserNotifications}>{notificationPermission === 'granted' ? 'Notifikasi browser aktif' : notificationPermission === 'denied' ? 'Izin browser diblokir' : 'Aktifkan notifikasi browser'}</Button></div>
          <div className="notification-delivery-note"><Icon name="info" size={16} /><span>Pemberitahuan dalam aplikasi tersimpan di server dan dipolling saat aplikasi terbuka. Pop-up browser perlu izin; push saat aplikasi tertutup belum dikonfigurasi.</span></div>
          {visibleNotifications.length ? <div className="notification-center-list">{visibleNotifications.map((item) => <article className={`notification-card ${item.readAt ? 'notification-card-read' : 'notification-card-unread'}`} key={item.id}><span className={`notification-card-icon notification-icon-${item.category}`}>{categoryEmoji(item.category)}</span><div className="notification-card-copy"><div className="notification-card-meta"><Pill tone={item.category === 'reminder' ? 'gold' : item.category === 'photo' ? 'plum' : 'sage'}>{categoryLabel(item.category)}</Pill><small>{displayTime(item.createdAt)}</small></div><h3>{item.title}</h3><p>{item.body}</p>{item.dueAt && <small className="notification-due">Jadwal: {displayTime(item.dueAt)}</small>}{item.completedAt && <Pill tone="sage">Selesai</Pill>}
              <div className="notification-card-actions"><button type="button" className="text-link" onClick={() => onOpenNotification(item)}>{item.title === 'Feedback aktivitas baru' ? 'Buka saran stimulasi' : item.category === 'photo' || item.category === 'activity' ? 'Buka catatan' : item.category === 'message' ? 'Buka percakapan' : 'Buka pusat pesan'} <Icon name="arrow" size={14} /></button>{!item.readAt && <button type="button" className="text-link" onClick={() => onMarkNotificationRead(item)}>Tandai dibaca</button>}{item.category === 'reminder' && !item.completedAt && role !== 'doctor' && <button type="button" className="text-link reminder-complete-link" onClick={() => onCompleteReminder(item)}>Tandai selesai</button>}</div>
            </div></article>)}</div> : <EmptyState icon="bell" title="Belum ada pemberitahuan tersimpan" detail={isParent ? 'Kabar kegiatan yang dibagikan, pesan, dan pengingat keluarga akan muncul di sini.' : 'Pesan baru, kegiatan terkait profil, dan pengingat akan muncul di sini.'} />}
        </section>}
      </div>
    </>
  );
}
function ReportsPage({ role, data, children }: LooseProps) {
  const isParent = role === 'parent';
  const [tab, setTab] = useState('Harian');
  const visibleIds = children.map((child) => child.id);
  const activities = data.activities.filter((item) => visibleIds.includes(item.childId) && (!isParent || item.shared));
  const todayActivities = activities.filter((item) => item.createdAt === shortDateLabel);
  const assessments = role === 'doctor' ? data.queue : isParent ? data.queue.filter((item) => visibleIds.includes(item.childId) && item.reviewed && item.published) : [];
  const rows = activities.map((item) => ({ Tanggal: item.createdAt, Waktu: item.time, Profil: data.children.find((child) => child.id === item.childId)?.name || 'Profil anak', Kategori: item.category, Kegiatan: item.title, Sumber: item.source, Dibagikan: item.shared ? 'Ya' : 'Tidak' }));
  const exportCsv = () => {
    const headers = Object.keys(rows[0] || { Tanggal: '', Waktu: '', Profil: '', Kategori: '', Kegiatan: '', Sumber: '', Dibagikan: '' });
    const csv = [headers.join(','), ...rows.map((row) => headers.map((header) => `"${String(row[header] || '').replaceAll('"', '""')}"`).join(','))].join('\n');
    const blob = new Blob([`\uFEFF${csv}`], { type: 'text/csv;charset=utf-8' });
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a'); link.href = url; link.download = 'rumah-kecilku-laporan-aktivitas.csv'; link.click(); URL.revokeObjectURL(url);
  };
  return (
    <>
      <PageTitle eyebrow={isParent ? 'Untuk keluarga' : role === 'doctor' ? 'Ringkasan tinjauan' : 'Catatan daycare'} title={isParent ? 'Laporan anak' : role === 'doctor' ? 'Laporan perkembangan' : 'Ringkasan kegiatan'} description={isParent ? 'Lihat catatan yang dibagikan untuk profil anak yang terhubung. Hasil KPSP hanya muncul setelah dokter membagikannya.' : 'Pilih bagian untuk melihat kegiatan, hasil yang telah ditinjau, atau riwayat tindakan.'} action={<div className="report-actions"><Button variant="outline" icon="download" onClick={exportCsv}>Unduh laporan</Button><Button icon="report" onClick={() => window.print()}>Cetak laporan</Button></div>} />
      <div className="report-tabs" role="tablist" aria-label="Jenis laporan">{['Harian', 'Perkembangan', 'Aktivitas', 'Jejak data'].map((item) => <button role="tab" aria-selected={tab === item} className={tab === item ? 'report-tab-active' : ''} key={item} onClick={() => setTab(item)}>{item}</button>)}</div>
      <section className="report-cover gradient-paper"><div className="report-cover-mark"><span>RK</span></div><div><Pill tone="warm">{isParent ? 'Ringkasan keluarga' : role === 'doctor' ? 'Ringkasan dokter' : 'Catatan daycare'}</Pill><h2>{tab === 'Harian' ? `Kegiatan tersimpan, ${shortDateLabel}` : tab === 'Perkembangan' ? 'Hasil perkembangan yang dibagikan' : tab === 'Aktivitas' ? 'Riwayat kegiatan per sesi' : 'Riwayat tindakan di akun ini'}</h2><p>Disusun dari catatan yang tersimpan. Waktu dan asal catatan tetap ditampilkan.</p></div><div className="report-cover-side"><span>AKUN</span><strong>{ROLE_LABELS[role]}</strong><small>Versi uji</small></div></section>
      {tab === 'Harian' && <div className="dashboard-grid report-grid"><section className="panel"><CardTitle eyebrow="Aktivitas tercatat hari ini" title={`${todayActivities.length} catatan sesi`} /><div className="report-timeline">{todayActivities.slice(0, 5).map((item) => <div className="report-timeline-row" key={item.id}><time>{item.time}</time><i /><div><strong>{item.title}</strong><small>{data.children.find((child) => child.id === item.childId)?.name} · {item.category} · sumber: {item.source}</small></div></div>)}</div>{!todayActivities.length && <EmptyState title="Belum ada catatan hari ini" detail="Catatan yang tersimpan hari ini akan tampil di sini." />}</section><section className="panel report-summary-card"><CardTitle eyebrow="Ringkasan sumber" title="Transparansi catatan" /><div className="report-summary-stat"><strong>{todayActivities.length}</strong><span>aktivitas hari ini</span></div><div className="report-summary-row"><span>Data yang tampil</span><strong>Catatan tersimpan</strong></div><div className="report-summary-row"><span>Hasil dokter dibagikan</span><strong>{assessments.filter((item) => item.published).length}</strong></div><p>Ringkasan ini tidak menambahkan interpretasi klinis otomatis.</p></section></div>}
      {tab === 'Perkembangan' && <section className="panel report-development"><CardTitle eyebrow="Perkembangan" title="Ringkasan dokter" /><div className="report-status-card"><span className="status-status-icon"><Icon name="review" size={18} /></span><div><strong>{isParent ? (assessments.length ? 'Ada ringkasan yang telah dibagikan' : 'Belum ada ringkasan dokter yang dibagikan') : role === 'doctor' ? `${assessments.filter((item) => item.reviewed).length} hasil sudah ditinjau` : 'Belum ada ringkasan dokter'}</strong><small>{isParent ? 'Keluarga hanya dapat melihat ringkasan setelah dokter meninjau dan membagikannya. Jawaban KPSP tidak ditampilkan.' : 'Hasil KPSP adalah skrining, bukan diagnosis. Tidak ada penilaian perkembangan otomatis.'}</small></div>{isParent ? <Pill tone={assessments.length ? 'sage' : 'neutral'}>{assessments.length ? 'Dibagikan' : 'Belum tersedia'}</Pill> : <Pill tone="neutral">Tinjauan dokter</Pill>}</div><div className="report-caveat"><Icon name="info" size={16} /><span>{isParent ? 'Jika membutuhkan penjelasan, kirim pesan kepada tim daycare.' : 'Dokter menentukan penjelasan dan tindak lanjut setelah membaca hasil.'}</span></div>{isParent && assessments.filter((item) => item.reviewed && item.published).map((item) => <article className="report-published-summary" key={item.id}><span className="eyebrow">DITINJAU DAN DIBAGIKAN DOKTER · {item.date}</span><h3>{item.domain}</h3><p>{item.note}</p>{item.kpspResult?.result_code && <strong>{item.kpspResult.result_label} · {item.kpspResult.yes_count}/{item.kpspResult.total_items} jawaban Ya</strong>}</article>)}</section>}
      {tab === 'Aktivitas' && <section className="panel table-panel"><div className="table-scroll"><table className="data-table"><thead><tr><th>TANGGAL</th><th>WAKTU</th><th>PROFIL</th><th>SESI</th><th>SUMBER</th><th>DIBAGIKAN</th></tr></thead><tbody>{activities.map((item) => <tr key={item.id}><td>{item.createdAt}</td><td>{item.time}</td><td>{data.children.find((child) => child.id === item.childId)?.name}</td><td>{item.title}</td><td>{item.source}</td><td><Pill tone={item.shared ? 'sage' : 'neutral'}>{item.shared ? 'Ya' : 'Tidak'}</Pill></td></tr>)}</tbody></table></div>{!activities.length && <EmptyState title="Riwayat kosong" detail="Tidak ada data untuk periode ini." />}</section>}
      {tab === 'Jejak data' && <section className="panel audit-panel"><CardTitle eyebrow="Riwayat akun" title="Perubahan pada akun ini" /><div className="table-scroll"><table className="data-table"><thead><tr><th>WAKTU</th><th>PERUBAHAN</th><th>AKUN</th><th>CATATAN</th></tr></thead><tbody>{data.audit.filter((item) => isParent ? visibleIds.includes(item.childId) : true).map((item) => <tr key={item.id}><td>{item.time}</td><td>{item.event}</td><td>{item.actor}</td><td>{item.source}</td></tr>)}</tbody></table></div>{!data.audit.length && <EmptyState title="Belum ada perubahan" detail="Tindakan pada akun ini akan tercatat di sini." />}<div className="report-caveat"><Icon name="privacy" size={16} /><span>Riwayat ini disimpan di browser dan bukan catatan resmi.</span></div></section>}
    </>
  );
}

function PrivacyPage({ role, data, child, onToggleConsent, onReset }: LooseProps) {
  const isParent = role === 'parent';
  const showSuggestions = Boolean(child && data.consents[child.id] === true);
  const accessRows = [
    ['Kegiatan', 'Catatan yang dibagikan untuk anak tertaut', 'Mencatat; memilih kegiatan yang dibagikan', 'Melihat catatan untuk tinjauan'],
    ['Hasil KPSP', 'Ringkasan setelah dokter membagikan', 'Tidak membuka jawaban KPSP', 'Mengisi, meninjau, dan membagikan'],
    ['Pesan', 'Membaca dan membalas pesan keluarga', 'Mengirim pesan ke keluarga tertaut', 'Tidak tersedia'],
    ['Kehadiran & pengamatan', 'Tidak ditampilkan', 'Mencatat untuk tim', 'Membaca pengamatan'],
    ['Suhu & kelembapan', 'Tidak ditampilkan', 'Melihat status ruang', 'Melihat status ruang'],
  ];
  return (
    <>
      <PageTitle eyebrow="Data dan akses" title={isParent ? 'Data keluarga' : 'Data dan akses akun'} description={isParent ? 'Lihat data apa yang ditampilkan kepada keluarga dan atur tampilan saran.' : 'Akun berbeda memiliki tampilan berbeda. Gunakan profil anak contoh saja; ruang ini belum untuk data nyata.'} action={!isParent && <Button variant="outline" icon="refresh" onClick={onReset}>Reset tampilan akun ini</Button>} />
      {isParent ? <div className="privacy-parent-layout">
        <section className="panel consent-main-card"><div className="consent-illustration gradient-sage"><span className="consent-big-icon"><Icon name="privacy" size={30} /></span><div className="consent-stamp"><span>DATA</span><strong>ANAK</strong></div></div><div className="consent-main-copy"><Pill tone={showSuggestions ? 'sage' : 'gold'} dot>{showSuggestions ? 'Saran ditampilkan' : 'Saran disembunyikan'}</Pill><h2>Atur tampilan saran perkembangan.</h2><p>Tombol ini hanya menyembunyikan atau menampilkan saran pada akun ini. Ini bukan formulir persetujuan resmi untuk penggunaan data.</p><button className={`switch-row large-switch ${showSuggestions ? 'switch-on' : ''}`} onClick={() => child && onToggleConsent(child.id)} aria-pressed={showSuggestions}><span className="switch-track"><i /></span><span>{showSuggestions ? 'Sembunyikan saran' : 'Tampilkan saran'}</span></button><div className="consent-checklist"><div><Icon name="check" size={15} /><span>Catatan kegiatan hanya muncul bila dibagikan pengasuh.</span></div><div><Icon name="check" size={15} /><span>Hasil KPSP hanya muncul setelah ditinjau dan dibagikan dokter.</span></div><div><Icon name="check" size={15} /><span>Hasil skrining bukan diagnosis.</span></div></div></div></section>
        <section className="panel privacy-help"><CardTitle eyebrow="Informasi keluarga" title="Apa yang dapat dilihat?" /><p>Akun keluarga hanya menampilkan catatan yang dibagikan untuk profil anak yang terhubung. Jawaban mentah KPSP dan catatan internal pengasuh tidak ditampilkan.</p><div className="privacy-help-row"><Icon name="message" size={17} /><span>Gunakan pesan untuk bertanya kepada tim daycare.</span></div><div className="privacy-caution"><strong>Profil anak yang terlihat adalah contoh.</strong><span>Jangan masukkan nama lengkap, tanggal lahir, atau catatan kesehatan anak yang sebenarnya.</span></div></section>
      </div> : <>
        <section className="panel access-matrix-panel"><CardTitle eyebrow="Akses sesuai tugas" title="Yang dapat dilihat setiap akun" action={<Pill tone="neutral">3 jenis akun</Pill>} /><div className="table-scroll"><table className="data-table access-table"><thead><tr><th>JENIS DATA</th><th>ORANG TUA</th><th>PENGASUH</th><th>DOKTER</th></tr></thead><tbody>{accessRows.map((row) => <tr key={`access-row-${row[0]}`}>{row.map((cell, index) => { const cellKey = `access-cell-${row[0]}-${index}`; return index === 0 ? <th scope="row" key={cellKey}>{cell}</th> : <td key={cellKey}>{cell}</td>; })}</tr>)}</tbody></table></div><div className="matrix-footnote"><Icon name="info" size={15} />Catatan kegiatan, kehadiran, pengamatan, pesan, dan KPSP yang dikirim tersimpan bersama akun uji. {data.sensor?.connected ? `Sensor terakhir ${data.sensor.roomId || 'ruang daycare'} diperbarui ${data.sensor.updatedAt || 'tanpa waktu'}.` : 'Sensor belum mengirim pembacaan ke backend.'}</div></section>
        <div className="dashboard-grid privacy-lower-grid"><section className="panel audit-panel"><CardTitle eyebrow="Di akun ini" title="Riwayat tindakan pada browser" />{data.audit.length ? <div className="audit-timeline">{data.audit.slice(0, 5).map((item) => <div className="audit-item" key={item.id}><span className="audit-dot" /><div><strong>{item.event}</strong><small>{data.children.find((childItem) => childItem.id === item.childId)?.name || 'Rumah Kecilku'} · {item.actor}</small><small>{item.time} · {item.source}</small></div></div>)}</div> : <EmptyState title="Belum ada tindakan" detail="Perubahan yang Anda buat pada akun ini akan terlihat di sini." />}<div className="report-caveat"><Icon name="privacy" size={16} /><span>Riwayat ini tersimpan di browser dan bukan catatan audit resmi.</span></div></section><section className="panel security-notes"><Pill tone="plum">Belum siap untuk data nyata</Pill><h3>Yang masih perlu disiapkan</h3><ul><li>Penyimpanan aman, pemulihan akun, cadangan, dan cara menghapus data.</li><li>Pengelolaan izin keluarga dan pemisahan data antar-daycare.</li><li>Alat suhu dan kelembapan yang benar-benar terhubung.</li><li>Peninjauan dan pengujian klinis sebelum hasil apa pun digunakan.</li></ul><p>Hanya ide aktivitas umum dari model demo berdata sintetis yang tersedia; tidak ada penilaian atau prediksi perkembangan otomatis dan model belum divalidasi klinis.</p></section></div>
      </>}
      <section className="panel role-boundary-panel"><div className="boundary-icon"><Icon name="privacy" size={18} /></div><div><strong>Jangan gunakan data anak nyata pada versi uji ini.</strong><span>Akun demo berbagi tempat penyimpanan uji yang sama. Akses beberapa catatan sudah dibatasi, tetapi pemisahan data untuk banyak daycare belum tersedia.</span></div></section>
    </>
  );
}

function ModalActivityForm({ children, linkedChildIds = [], initialChildId, initialTitle, meals = [], onSave, onClose }: LooseProps) {
  const [childId, setChildId] = useState(initialChildId || children[0]?.id || 'a');
  const [logAllChildren, setLogAllChildren] = useState(true);
  const [specialCase, setSpecialCase] = useState(false);
  const [category, setCategory] = useState('Stimulasi');
  const [title, setTitle] = useState(initialTitle || '');
  const [mealSelections, setMealSelections] = useState([{ mealId: '', servings: '1' }]);
  const [session, setSession] = useState('Pagi');
  const [time, setTime] = useState(() => new Intl.DateTimeFormat('en-GB', { hour: '2-digit', minute: '2-digit', hourCycle: 'h23', timeZone: 'Asia/Jakarta' }).format(new Date()));
  const [durationMinutes, setDurationMinutes] = useState('');
  const [waterMl, setWaterMl] = useState('');
  const [mood, setMood] = useState('');
  const [participation, setParticipation] = useState('');
  const [note, setNote] = useState('');
  const [mediaDataUrl, setMediaDataUrl] = useState('');
  const [mediaName, setMediaName] = useState('');
  const [mediaType, setMediaType] = useState('');
  const [mediaConsentConfirmed, setMediaConsentConfirmed] = useState(false);
  const [shared, setShared] = useState(false);
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  const canShare = !logAllChildren && linkedChildIds.includes(childId);
  const selectedMeals = mealSelections.map((selection) => ({
    ...selection,
    meal: meals.find((meal) => meal.id === selection.mealId),
    servings: Number(selection.servings) || 0,
  })).filter((selection) => selection.meal && selection.servings > 0);
  const mealTotals = selectedMeals.reduce((total, selection) => {
    total.energyKcal += selection.meal.energyKcal * selection.servings;
    total.proteinG += selection.meal.proteinG * selection.servings;
    total.carbohydrateG += selection.meal.carbohydrateG * selection.servings;
    total.fatG += selection.meal.fatG * selection.servings;
    total.fiberG += selection.meal.fiberG * selection.servings;
    total.grams += selection.meal.servingGrams * selection.servings;
    return total;
  }, { energyKcal: 0, proteinG: 0, carbohydrateG: 0, fatG: 0, fiberG: 0, grams: 0 });
  const canUseMealCatalog = false;
  const updateMealSelection = (index: number, patch: { mealId?: string; servings?: string }) => {
    const next = mealSelections.map((selection, rowIndex) => rowIndex === index ? { ...selection, ...patch } : selection);
    setMealSelections(next);
    const names = next.map((selection) => meals.find((meal) => meal.id === selection.mealId)?.name).filter(Boolean);
    if (names.length) setTitle(names.join(' + '));
  };
  const removeMealSelection = (index: number) => {
    const next = mealSelections.filter((_, rowIndex) => rowIndex !== index);
    setMealSelections(next);
    const names = next.map((selection) => meals.find((meal) => meal.id === selection.mealId)?.name).filter(Boolean);
    if (names.length) setTitle(names.join(' + '));
  };
  useEffect(() => { if (!canShare) setShared(false); }, [canShare]);

  const applyQuickActivity = (nextCategory: string, defaultTitle: string) => {
    setCategory(nextCategory);
    setTitle(defaultTitle);
    if (nextCategory !== 'Makan & minum') setMealSelections([{ mealId: '', servings: '1' }]);
  };

  const handleMedia = (file) => {
    setError('');
    setMediaDataUrl('');
    setMediaName('');
    setMediaType('');
    setMediaConsentConfirmed(false);
    if (!file) return;
    if (!['image/jpeg', 'image/png', 'image/webp', 'video/mp4', 'video/webm', 'video/quicktime'].includes(file.type)) { setError('Pilih foto JPEG/PNG/WebP atau video MP4/WebM/MOV.'); return; }
    if (file.size > 300 * 1024 * 1024) { setError('Ukuran foto atau video maksimal 300 MB.'); return; }
    const reader = new FileReader();
    reader.onload = () => {
      if (typeof reader.result === 'string') { setMediaDataUrl(reader.result); setMediaName(file.name); setMediaType(file.type); }
      else setError('Media tidak dapat dibaca. Pilih berkas lain.');
    };
    reader.onerror = () => setError('Media tidak dapat dibaca. Pilih berkas lain.');
    reader.readAsDataURL(file);
  };

  const submit = async (event) => {
    event.preventDefault();
    if (busy) return;
    if (!title.trim() || !note.trim()) { setError('Isi nama kegiatan dan catatan faktual sebelum menyimpan.'); return; }
    if (canUseMealCatalog && !selectedMeals.length) { setError('Pilih setidaknya satu bahan dari katalog agar nilai gizi dapat dihitung.'); return; }
    if (mediaDataUrl && !mediaConsentConfirmed) { setError('Konfirmasi privasi media sebelum menyimpan.'); return; }
    setBusy(true);
    setError('');
    try {
      await onSave({
        childId, childIds: specialCase || !logAllChildren ? [childId] : children.map((child) => child.id), category, title: title.trim(), session, time, note: note.trim(), shared,
        mealItems: selectedMeals.map((selection) => ({ mealId: selection.mealId, servings: selection.servings })), 
        durationMinutes: durationMinutes ? Number(durationMinutes) : null,
        waterMl: waterMl ? Number(waterMl) : null,
        mood: mood || null, participation: participation || null,
        mediaDataUrl: mediaDataUrl || null, mediaConsentConfirmed, specialCase,
      });
    } finally { setBusy(false); }
  };
  return <ModalShell title="Catat kegiatan harian" subtitle="Isi konteks kegiatan yang sudah berlangsung. Catatan dan foto tidak membuat penilaian perkembangan otomatis." onClose={onClose} width="wide">
    <form className="modal-form" onSubmit={submit}>
      <div className="quick-log-strip" role="group" aria-label="Pilih alur pencatatan cepat"><span>Catat cepat</span>{[['🍽️', 'Makan & minum', 'Makan & minum'], ['💤', 'Tidur', 'Tidur'], ['🧩', 'Bermain', 'Bermain'], ['📚', 'Stimulasi', 'Stimulasi'], ['⚠️', 'Kejadian khusus', 'Kejadian']].map(([emoji, label, nextCategory]) => <button type="button" key={label} className={category === nextCategory ? 'quick-log-active' : ''} onClick={() => applyQuickActivity(nextCategory, label)}><span>{emoji}</span>{label}</button>)}</div>
      <section className="activity-target-panel field-full"><strong>Siapa yang dicatat?</strong><label className="quick-choice"><input type="checkbox" checked={logAllChildren && !specialCase} onChange={(event) => { setLogAllChildren(event.target.checked); if (event.target.checked) setSpecialCase(false); }} /> Semua anak yang hadir</label><label className="quick-choice"><input type="checkbox" checked={specialCase} onChange={(event) => { setSpecialCase(event.target.checked); if (event.target.checked) { setLogAllChildren(false); setCategory('Kejadian'); setTitle('Catatan khusus anak'); } }} /> Kasus khusus satu anak (mood kurang baik, sakit, atau kejadian)</label>{(specialCase || !logAllChildren) && <label className="field"><span>Pilih anak</span><select value={childId} onChange={(event) => setChildId(event.target.value)}>{children.map((child) => <option key={child.id} value={child.id}>{child.name} · {child.ageMonths} bulan</option>)}</select></label>}{logAllChildren && !specialCase && <small>Kegiatan umum akan dibuat otomatis untuk semua anak dalam satu kali simpan.</small>}</section>
      <div className="form-grid">
        <label className="field"><span>Kategori sesi</span><select value={category} onChange={(event) => { setCategory(event.target.value); if (event.target.value !== 'Makan & minum') setMealSelections([{ mealId: '', servings: '1' }]); }}>{['Makan & minum', 'Tidur', 'Stimulasi', 'Bermain', 'Belajar', 'Kejadian'].map((item) => <option key={item}>{item}</option>)}</select></label>
        {canUseMealCatalog && <section className="meal-builder field-full"><div className="meal-builder-heading"><div><strong>Pilih bahan yang disajikan</strong><small>Tambahkan beberapa pilihan, misalnya nasi + sayur. Nilai dijumlahkan dari porsi katalog.</small></div><Pill tone="sage">{meals.length} pilihan</Pill></div><div className="meal-selection-list">{mealSelections.map((selection, index) => <div className="meal-selection-row" key={`meal-${index}`}><label className="field"><span>{index === 0 ? 'Pilih menu bergizi' : `Bahan tambahan ${index + 1}`}</span><select value={selection.mealId} aria-label={index === 0 ? 'Pilih menu bergizi' : `Pilih bahan tambahan ${index + 1}`} onChange={(event) => updateMealSelection(index, { mealId: event.target.value })}><option value="">Pilih dari katalog dokter</option>{meals.map((meal) => <option value={meal.id} key={meal.id} disabled={mealSelections.some((other, otherIndex) => otherIndex !== index && other.mealId === meal.id)}>{meal.name} · {meal.energyKcal} kkal / {meal.servingLabel}</option>)}</select></label><label className="field meal-quantity-field"><span>Jumlah porsi</span><input aria-label={`Jumlah porsi bahan ${index + 1}`} type="number" min="0.25" max="5" step="0.25" value={selection.servings} onChange={(event) => updateMealSelection(index, { servings: event.target.value })} /></label>{mealSelections.length > 1 && <button type="button" className="icon-button meal-remove-button" aria-label={`Hapus bahan ${index + 1}`} onClick={() => removeMealSelection(index)}><Icon name="close" size={15} /></button>}</div>)}</div><div className="meal-builder-actions"><button type="button" className="text-link" onClick={() => setMealSelections((current) => current.length < 8 ? [...current, { mealId: '', servings: '1' }] : current)} disabled={mealSelections.length >= 8}>＋ Tambah bahan</button><span>Contoh porsi total: {mealTotals.grams.toLocaleString('id-ID', { maximumFractionDigits: 1 })} g</span></div><div className="field meal-selected-summary"><span>Perkiraan total gizi dari pilihan di atas</span>{selectedMeals.length ? <small>{mealTotals.energyKcal.toFixed(1)} kkal · protein {mealTotals.proteinG.toFixed(2)} g · karbohidrat {mealTotals.carbohydrateG.toFixed(2)} g · lemak {mealTotals.fatG.toFixed(2)} g · serat {mealTotals.fiberG.toFixed(2)} g</small> : <small>Pilih satu atau beberapa bahan untuk melihat perhitungan per porsi.</small>}</div><div className="meal-builder-note"><Icon name="info" size={14} />Tidak menghitung minyak, saus, bumbu, atau perubahan akibat cara memasak yang tidak tercantum pada katalog.</div></section>}
        <label className="field"><span>Nama kegiatan</span><input value={title} onChange={(event) => setTitle(event.target.value)} placeholder={category === 'Makan & minum' ? 'Contoh: makan siang dan minum' : 'Contoh: membaca bersama'} /></label>
        <label className="field"><span>Waktu selesai</span><input type="time" value={time} onChange={(event) => setTime(event.target.value)} /></label>
        <label className="field"><span>Sesi</span><select value={session} onChange={(event) => setSession(event.target.value)}>{['Pagi', 'Siang', 'Sore'].map((item) => <option key={item}>{item}</option>)}</select></label>
        <label className="field"><span>Durasi (menit, opsional)</span><input type="number" min="1" max="720" step="1" value={durationMinutes} onChange={(event) => setDurationMinutes(event.target.value)} placeholder={category === 'Tidur' ? 'Lama istirahat' : '—'} /></label>
        {category === 'Makan & minum' && <label className="field"><span>Jumlah minum (ml, opsional)</span><input type="number" min="0" max="3000" step="10" value={waterMl} onChange={(event) => setWaterMl(event.target.value)} placeholder="Misalnya 120" /></label>}
        <div className="field field-full mood-field"><span>Suasana hati (opsional)</span><div className="emoji-choice-row" role="group" aria-label="Suasana hati (opsional)">{[{ value: 'Senang', emoji: '😊', label: 'Senang' }, { value: 'Tenang', emoji: '😌', label: 'Tenang' }, { value: 'Membutuhkan dukungan', emoji: '🥺', label: 'Butuh dukungan' }, { value: '', emoji: '😐', label: 'Belum dicatat' }].map((item) => <button type="button" key={item.label} className={mood === item.value && (item.value || !mood) ? 'emoji-choice emoji-choice-active' : 'emoji-choice'} aria-pressed={mood === item.value && Boolean(item.value || !mood)} onClick={() => setMood(item.value)}><span>{item.emoji}</span><small>{item.label}</small></button>)}</div><small className="field-helper">Pilih hanya suasana yang benar-benar diamati saat kegiatan.</small></div>
        <div className="field field-full participation-field"><span>Partisipasi (opsional)</span><div className="quick-choice-row" role="group" aria-label="Partisipasi dalam kegiatan">{[{ value: 'Mandiri', label: 'Mandiri' }, { value: 'Dengan dukungan', label: 'Dengan dukungan' }, { value: 'Mengamati', label: 'Mengamati' }, { value: '', label: 'Belum dicatat' }].map((item) => <button type="button" key={item.label} className={participation === item.value && (item.value || !participation) ? 'quick-choice quick-choice-active' : 'quick-choice'} aria-pressed={participation === item.value && Boolean(item.value || !participation)} onClick={() => setParticipation(item.value)}>{item.label}</button>)}</div></div>
      </div>
      <label className="field"><span>Catatan faktual (wajib)</span><textarea rows={3} value={note} onChange={(event) => setNote(event.target.value)} placeholder="Tulis apa yang disajikan/dilakukan dan respons yang benar-benar terlihat; hindari label atau kesimpulan klinis." /></label>
      <section className="photo-upload-panel"><label className="field"><span>Foto atau video kegiatan (opsional, maks. 300 MB)</span><input type="file" accept="image/jpeg,image/png,image/webp,video/mp4,video/webm,video/quicktime" onChange={(event) => handleMedia(event.target.files?.[0])} /></label><p>Media mengikuti hak akses catatan dan hanya dibagikan jika Anda memilih berbagi. Pada versi uji, gunakan media dummy/ilustrasi.</p>{mediaDataUrl && <div className="photo-upload-preview">{mediaType.startsWith('video/') ? <video src={mediaDataUrl} controls aria-label="Pratinjau video kegiatan" /> : <img src={mediaDataUrl} alt="Pratinjau foto kegiatan" />}<span>{mediaName}</span><button type="button" className="text-link" onClick={() => { setMediaDataUrl(''); setMediaName(''); setMediaType(''); setMediaConsentConfirmed(false); }}>Hapus media</button></div>}{mediaDataUrl && <label className="photo-consent"><input type="checkbox" checked={mediaConsentConfirmed} onChange={(event) => setMediaConsentConfirmed(event.target.checked)} /><span>Saya memahami bahwa media adalah data sensitif dan hanya memakai gambar/video dummy pada versi uji.</span></label>}</section>
      <label className={`share-checkbox ${!canShare ? 'share-checkbox-disabled' : ''}`}><input type="checkbox" checked={shared} disabled={!canShare} onChange={(event) => setShared(event.target.checked)} /><span className="share-checkbox-copy"><strong>Bagikan catatan ini ke keluarga</strong><small>{canShare ? 'Foto dan kabar mengikuti status berbagi; hasil perkembangan tidak ikut terkirim.' : 'Belum ada akun keluarga yang terhubung ke profil ini.'}</small></span></label>
      {error && <div className="form-error" role="alert">{error}</div>}
      <div className="modal-actions"><Button variant="outline" onClick={onClose} disabled={busy}>Batal</Button><Button type="submit" icon="check" disabled={busy}>{busy ? 'Menyimpan catatan…' : 'Simpan catatan kegiatan'}</Button></div>
    </form>
  </ModalShell>;
}

function ModalObservationForm({ children, initialChildId, onSave, onClose }: LooseProps) {
  const [childId, setChildId] = useState(initialChildId || children[0]?.id || 'a');
  const [aspect, setAspect] = useState('Motorik kasar');
  const [milestone, setMilestone] = useState('');
  const [reference, setReference] = useState('');
  const [result, setResult] = useState('Teramati');
  const [context, setContext] = useState('');
  const [note, setNote] = useState('');
  const [error, setError] = useState('');
  const submit = (event) => {
    event.preventDefault();
    if (!context.trim() || !note.trim()) { setError('Isi konteks kegiatan dan perilaku yang benar-benar terlihat.'); return; }
    onSave({ childId, aspect, milestone: milestone.trim(), reference: reference.trim(), result, context: context.trim(), note: note.trim(), time: new Intl.DateTimeFormat('en-GB', { hour: '2-digit', minute: '2-digit', hourCycle: 'h23', timeZone: 'Asia/Jakarta' }).format(new Date()) });
  };
  return <ModalShell title="Catat pengamatan perkembangan" subtitle="Tuliskan perilaku yang benar-benar terlihat. Jangan menyimpulkan kemampuan atau keterlambatan dari satu catatan." onClose={onClose} width="wide">
    <div className="alert-panel alert-coral"><span className="alert-icon"><Icon name="info" size={18} /></span><div><strong>Belum ada daftar pengamatan khusus yang disiapkan.</strong><p>Catatan ini hanya memuat kejadian yang terlihat; catatan tidak membuat penilaian otomatis.</p></div></div>
    <form className="modal-form" onSubmit={submit}>
      <div className="form-grid"><label className="field"><span>Profil anak</span><select value={childId} onChange={(event) => setChildId(event.target.value)}>{children.map((child) => <option key={child.id} value={child.id}>{child.name} · {child.ageMonths} bulan</option>)}</select></label><label className="field"><span>Aspek</span><select value={aspect} onChange={(event) => setAspect(event.target.value)}>{['Motorik kasar', 'Motorik halus', 'Bahasa', 'Sosial-emosional'].map((item) => <option key={item}>{item}</option>)}</select></label><label className="field field-full"><span>Milestone/perilaku sasaran (opsional)</span><input value={milestone} onChange={(event) => setMilestone(event.target.value)} placeholder="Tuliskan perilaku yang diamati, tanpa memberi label kemampuan" /></label><label className="field"><span>Sumber (opsional)</span><input value={reference} onChange={(event) => setReference(event.target.value)} placeholder="Nama buku atau panduan, jika ada" /></label><label className="field"><span>Hasil pengamatan</span><select value={result} onChange={(event) => setResult(event.target.value)}>{['Teramati', 'Belum teramati', 'Belum ada kesempatan'].map((item) => <option key={item}>{item}</option>)}</select></label><label className="field field-full"><span>Konteks/kesempatan</span><input value={context} onChange={(event) => setContext(event.target.value)} placeholder="Contoh: sesi membaca, permainan kelompok, suasana tenang" /></label></div>
      <label className="field"><span>Perilaku yang terlihat</span><textarea rows={3} value={note} onChange={(event) => setNote(event.target.value)} placeholder="Tuliskan kejadian spesifik, tanpa interpretasi atau label klinis." /></label>
      <div className="form-hint"><Icon name="privacy" size={15} />Pengamatan ini tidak memberi nilai atau diagnosis otomatis.</div>
      {error && <div className="form-error" role="alert">{error}</div>}
      <div className="modal-actions"><Button variant="outline" onClick={onClose}>Batal</Button><Button type="submit" icon="check">Simpan pengamatan</Button></div>
    </form>
  </ModalShell>;
}

function ModalQuarterlyReportForm({ children, initialChildId, onSave, onClose }: LooseProps) {
  const endDefault = todayIsoDate();
  const [childId, setChildId] = useState(initialChildId || children[0]?.id || 'a');
  const [periodStart, setPeriodStart] = useState(shiftIsoDateByMonths(endDefault, -3));
  const [periodEnd, setPeriodEnd] = useState(endDefault);
  const [summary, setSummary] = useState('');
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  const submit = async (event) => {
    event.preventDefault();
    if (busy) return;
    if (!summary.trim()) { setError('Tuliskan ringkasan faktual untuk laporan.'); return; }
    if (!periodStart || !periodEnd || periodStart > periodEnd) { setError('Periksa rentang tanggal laporan.'); return; }
    setBusy(true);
    setError('');
    try { await onSave({ childId, periodStart, periodEnd, summary: summary.trim() }); }
    finally { setBusy(false); }
  };
  return <ModalShell title="Buat draf laporan perkembangan 3 bulanan" subtitle="Draf memuat hitungan observasi pada periode yang dipilih dan ringkasan faktual. Dokter wajib meninjau sebelum keluarga dapat membacanya." onClose={onClose} width="wide">
    <form className="modal-form" onSubmit={submit}>
      <div className="form-grid"><label className="field"><span>Profil anak</span><select value={childId} onChange={(event) => setChildId(event.target.value)}>{children.map((child) => <option key={child.id} value={child.id}>{child.name} · {child.ageMonths} bulan</option>)}</select></label><label className="field"><span>Periode laporan</span><span className="quarterly-date-range"><input aria-label="Awal periode" type="date" value={periodStart} onChange={(event) => setPeriodStart(event.target.value)} /><span>sampai</span><input aria-label="Akhir periode" type="date" value={periodEnd} onChange={(event) => setPeriodEnd(event.target.value)} /></span></label><label className="field field-full"><span>Ringkasan faktual pengasuh</span><textarea rows={5} value={summary} onChange={(event) => setSummary(event.target.value)} placeholder="Tuliskan konteks dan pola kegiatan/observasi yang tercatat. Pisahkan fakta dari interpretasi; hindari diagnosis atau klaim usia perkembangan." required /></label></div>
      <div className="form-hint"><Icon name="privacy" size={15} />Draf hanya terlihat oleh pengasuh/dokter. Orang tua menerima ringkasan setelah dokter meninjau dan menerbitkannya.</div>
      {error && <div className="form-error" role="alert">{error}</div>}
      <div className="modal-actions"><Button variant="outline" onClick={onClose} disabled={busy}>Batal</Button><Button type="submit" icon="report" disabled={busy}>{busy ? 'Menyimpan draf…' : 'Simpan draf laporan'}</Button></div>
    </form>
  </ModalShell>;
}

function ModalChildForm({ onSave, onClose, isAdmin }: LooseProps) {
  const [name, setName] = useState('');
  const [birthDate, setBirthDate] = useState('');
  const [room, setRoom] = useState('');
  const screeningDate = todayIsoDate();
  const age = calculateAgeAt(birthDate, screeningDate);
  const validAge = age && age.roundedMonths >= 0 && age.roundedMonths <= 72;
  return <ModalShell title={isAdmin ? 'Tambah profil roster daycare' : 'Tambah profil anak contoh'} subtitle={isAdmin ? 'Mode demo: gunakan nama samaran. Profil tersimpan pada tenant; hubungan wali tetap perlu verifikasi institusional.' : 'Gunakan nama samaran. Profil ini hanya tersimpan pada akun saat ini.'} onClose={onClose}>
    <form className="modal-form" onSubmit={(event) => { event.preventDefault(); if (validAge) onSave({ name: name.trim(), ageMonths: age.roundedMonths, birthDate, room }); }}>
      
      <div className="form-grid"><label className="field"><span>Nama samaran</span><input value={name} onChange={(event) => setName(event.target.value)} required /></label><label className="field"><span>Tanggal lahir</span><input type="date" value={birthDate} max={screeningDate} onChange={(event) => setBirthDate(event.target.value)} required /></label><label className="field"><span>Usia saat ini</span><input value={age ? `${age.roundedMonths} bulan · ${age.remainderDays} hari` : 'Masukkan tanggal lahir'} readOnly /></label><label className="field"><span>Ruang</span><select value={room} onChange={(event) => setRoom(event.target.value)} required><option value="" disabled>Pilih ruang</option><option>Ruang Melati</option><option>Ruang Kenanga</option><option>Ruang Anggrek</option></select></label></div>
      {birthDate && !validAge && <div className="form-error" role="alert">Tanggal lahir harus berada dalam rentang usia KPSP 0–72 bulan.</div>}
      <div className="modal-actions"><Button variant="outline" onClick={onClose}>Batal</Button><Button type="submit" icon="plus" disabled={!validAge}>Simpan profil</Button></div>
    </form>
  </ModalShell>;
}

function ModalEditChildForm({ child, onSave, onClose }: LooseProps) {
  const [name, setName] = useState(child?.name || '');
  const [birthDate, setBirthDate] = useState(child?.birthDate || '');
  const [room, setRoom] = useState(child?.room || '');
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  const screeningDate = todayIsoDate();
  const age = calculateAgeAt(birthDate, screeningDate);
  const validAge = age && age.roundedMonths >= 0 && age.roundedMonths <= 72;
  const submit = async (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!child?.id || !name.trim() || !validAge) {
      setError('Lengkapi nama dan tanggal lahir yang valid terlebih dahulu.');
      return;
    }
    setBusy(true);
    setError('');
    const saved = await onSave({ id: child.id, name: name.trim(), birthDate, room: room.trim(), ageMonths: age.roundedMonths });
    if (!saved) setError('Perubahan belum tersimpan. Periksa akses admin dan coba lagi.');
    setBusy(false);
  };
  return <ModalShell title="Edit profil roster" subtitle="Perubahan dasar profil tersimpan di backend tenant ini. Jangan menambahkan catatan kesehatan atau data identitas yang tidak diperlukan." onClose={onClose}>
    <form className="modal-form" onSubmit={submit}>
      <div className="form-grid"><label className="field"><span>Nama profil</span><input value={name} onChange={(event) => setName(event.target.value)} maxLength={80} required /></label><label className="field"><span>Tanggal lahir</span><input type="date" value={birthDate} max={screeningDate} onChange={(event) => setBirthDate(event.target.value)} required /></label><label className="field"><span>Usia saat ini</span><input value={age ? `${age.roundedMonths} bulan · ${age.remainderDays} hari` : 'Masukkan tanggal lahir'} readOnly /></label><label className="field"><span>Ruang</span><input value={room} onChange={(event) => setRoom(event.target.value)} maxLength={80} placeholder="Belum ditentukan" /></label></div>
      {birthDate && !validAge && <div className="form-error" role="alert">Tanggal lahir harus berada dalam rentang usia KPSP 0–72 bulan.</div>}
      {error && <div className="form-error" role="alert">{error}</div>}
      <div className="form-hint"><Icon name="info" size={15} />Orang tua tidak memperoleh akses hanya karena profil diedit; relasi wali harus melalui pemeriksaan institusi dan konfirmasi akun keluarga.</div>
      <div className="modal-actions"><Button variant="outline" onClick={onClose} disabled={busy}>Batal</Button><Button type="submit" icon="check" disabled={!validAge || busy}>{busy ? 'Menyimpan…' : 'Simpan perubahan'}</Button></div>
    </form>
  </ModalShell>;
}

function ModalReminderForm({ children, initialChildId, onSave, onClose }: LooseProps) {
  const defaultDue = () => {
    const date = new Date(Date.now() + 60 * 60 * 1000);
    return new Date(date.getTime() - date.getTimezoneOffset() * 60000).toISOString().slice(0, 16);
  };
  const [childId, setChildId] = useState(initialChildId || children[0]?.id || '');
  const [audience, setAudience] = useState('family');
  const [title, setTitle] = useState('Pengingat dari daycare');
  const [body, setBody] = useState('');
  const [dueLocal, setDueLocal] = useState(defaultDue);
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  const submit = async (event) => {
    event.preventDefault();
    if (!childId || !title.trim() || !body.trim() || !dueLocal) { setError('Pilih profil, isi pesan, dan atur waktu pengingat.'); return; }
    if (new Date(dueLocal).getTime() < Date.now() - 30000) { setError('Waktu pengingat harus sekarang atau di masa mendatang.'); return; }
    setBusy(true);
    setError('');
    const saved = await onSave({ childId, audience, title: title.trim(), body: body.trim(), dueAt: new Date(dueLocal).toISOString() });
    if (!saved) setError('Pengingat belum tersimpan. Periksa akun keluarga tertaut lalu coba lagi.');
    setBusy(false);
  };
  return <ModalShell title="Buat pengingat tersimpan" subtitle="Pengingat muncul di pusat pemberitahuan penerima dan dapat ditandai selesai." onClose={onClose}>
    <form className="modal-form" onSubmit={submit}>
      <label className="field"><span>Profil anak</span><select value={childId} onChange={(event) => setChildId(event.target.value)} required>{children.map((child) => <option key={child.id} value={child.id}>{child.name}</option>)}</select></label>
      <label className="field"><span>Penerima</span><select value={audience} onChange={(event) => setAudience(event.target.value)}><option value="family">Keluarga yang terhubung</option><option value="self">Pengingat untuk saya (pengasuh)</option></select></label>
      <label className="field"><span>Judul pengingat</span><input value={title} maxLength={120} onChange={(event) => setTitle(event.target.value)} required /></label>
      <label className="field"><span>Waktu pengingat</span><input type="datetime-local" value={dueLocal} onChange={(event) => setDueLocal(event.target.value)} required /></label>
      <label className="field"><span>Isi pengingat</span><textarea rows={3} maxLength={500} value={body} onChange={(event) => setBody(event.target.value)} placeholder="Contoh: Mohon membawa botol minum berlabel pada sesi berikutnya." required /></label>
      <div className="form-hint"><Icon name="privacy" size={15} />Notifikasi keluarga hanya dikirim ke akun orang tua yang tertaut dengan profil pilihan. Pengingat tersimpan; push saat aplikasi tertutup belum tersedia.</div>
      {!children.length && <div className="form-error" role="status">Belum ada profil anak untuk pengingat.</div>}
      {error && <div className="form-error" role="alert">{error}</div>}
      <div className="modal-actions"><Button variant="outline" onClick={onClose} disabled={busy}>Batal</Button><Button type="submit" icon="clock" disabled={busy || !children.length}>{busy ? 'Menyimpan…' : 'Simpan pengingat'}</Button></div>
    </form>
  </ModalShell>;
}

function ModalAnnouncement({ children, onSave, onClose }: LooseProps) {
  const [target, setTarget] = useState('all');
  const [text, setText] = useState('');
  const [error, setError] = useState('');
  return <ModalShell title="Tulis pengumuman keluarga" subtitle="Pesan akan dikirim ke keluarga yang terhubung dengan profil yang dipilih." onClose={onClose}>
    <form className="modal-form" onSubmit={(event) => { event.preventDefault(); if (!text.trim()) { setError('Tulis isi pengumuman terlebih dahulu.'); return; } onSave({ target, text: text.trim() }); }}>
      <label className="field"><span>Penerima</span><select value={target} onChange={(event) => setTarget(event.target.value)}><option value="all">Semua keluarga tertaut</option>{children.map((child) => <option key={child.id} value={child.id}>{child.name}</option>)}</select></label>
      <label className="field"><span>Isi pengumuman</span><textarea rows={4} value={text} onChange={(event) => setText(event.target.value)} placeholder="Tulis informasi yang diperlukan keluarga, tanpa data anak lain." /></label>
      <div className="form-hint"><Icon name="info" size={15} />Hindari membagikan informasi pribadi atau data milik profil lain.</div>
      {!children.length && <div className="form-error" role="status">Belum ada akun keluarga yang terhubung untuk menerima pesan.</div>}
      {error && <div className="form-error" role="alert">{error}</div>}
      <div className="modal-actions"><Button variant="outline" onClick={onClose}>Batal</Button><Button type="submit" icon="send" disabled={!children.length}>Kirim pengumuman</Button></div>
    </form>
  </ModalShell>;
}

function ModalReview({ item, child, onSave, onPublish, onClose }: LooseProps) {
  const [decision, setDecision] = useState(item.decision || 'Kumpulkan observasi tambahan');
  const [note, setNote] = useState(item.note || '');
  const [error, setError] = useState('');
  const [saving, setSaving] = useState(false);
  const [publishing, setPublishing] = useState(false);
  const reviewed = item.reviewed;
  const submit = async (event) => {
    event.preventDefault();
    if (!note.trim()) { setError('Tuliskan catatan dokter sebelum menyimpan tinjauan.'); return; }
    setSaving(true);
    setError('');
    const saved = await onSave({ ...item, decision, note: note.trim() });
    if (!saved) setError('Tinjauan belum tersimpan. Coba lagi.');
    setSaving(false);
  };
  const publish = async () => {
    setPublishing(true);
    setError('');
    const saved = await onPublish(item);
    if (!saved) setError('Ringkasan belum dibagikan. Coba lagi.');
    setPublishing(false);
  };
  return <ModalShell title={`Tinjau hasil ${child?.name || 'profil anak'}`} subtitle={`KPSP · usia anak ${item.ageMonths} bulan`} onClose={onClose} width="wide">
    <div className="review-context-banner"><span className="review-context-icon"><Icon name="info" size={18} /></span><div><strong>{item.priority || (reviewed ? 'Sudah ditinjau' : 'Menunggu tinjauan')}</strong><p>{item.reason}</p></div><Pill tone={reviewed ? 'sage' : 'plum'}>{reviewed ? 'Sudah ditinjau' : 'Menunggu'}</Pill></div>
    <div className="review-evidence-grid"><div className="review-evidence-card"><small>PENGAMATAN</small><strong>{item.observationCount || 0}</strong><span>catatan yang tersedia</span></div><div className="review-evidence-card"><small>FORMULIR KPSP</small><strong>{item.kpspCount || 0}</strong><span>hasil yang dikirim</span></div><div className="review-evidence-card"><small>JAWABAN</small><strong>{item.evidenceCount || 0}</strong><span>jawaban untuk dibaca</span></div></div>
    <div className="review-evidence-note"><Icon name="privacy" size={16} /><span>KPSP adalah skrining, bukan diagnosis. Baca jawaban dan konteks sebelum menulis ringkasan.</span></div>
    {item.kpspResult?.result_code && <div className="review-kpsp-result"><span className={`review-kpsp-code review-kpsp-${item.kpspResult.result_code.toLowerCase()}`}>{item.kpspResult.result_code}</span><div><small>HASIL KPSP · {item.kpspResult.yes_count}/{item.kpspResult.total_items} JAWABAN YA</small><strong>{item.kpspResult.result_label}</strong><p>{Object.entries(item.kpspResult.no_by_domain || {}).map(([domain, count]) => `${domain}: ${count}`).join(' · ') || 'Tidak ada rincian tambahan pada jawaban Tidak.'}</p><em>Hasil skrining, bukan diagnosis. Tinjau konteks dan tindak lanjut sebelum membagikan ringkasan.</em></div></div>}
    {reviewed ? <div className="review-saved-panel"><Pill tone="sage" dot>Sudah ditinjau</Pill><h3>{item.decision}</h3><p>{item.note}</p>{item.published ? <><div className="inline-success"><Icon name="check" size={16} />Ringkasan sudah dibagikan kepada keluarga yang terhubung.</div><div className="modal-actions"><Button variant="outline" onClick={onClose}>Selesai</Button></div></> : <div className="publish-panel"><strong>Ringkasan belum dibagikan.</strong><small>Pastikan catatan jelas dan tidak menyebut diagnosis.</small><Button icon="send" onClick={publish} disabled={publishing}>{publishing ? 'Membagikan…' : 'Bagikan ringkasan kepada keluarga'}</Button></div>}{error && <div className="form-error" role="alert">{error}</div>}</div> : <form className="modal-form review-form" onSubmit={submit}><label className="field"><span>Arah tindak lanjut</span><select value={decision} onChange={(event) => setDecision(event.target.value)}>{['Kumpulkan observasi tambahan', 'Berikan kegiatan stimulasi umum', 'Jadwalkan konsultasi dengan keluarga', 'Tidak ada tindak lanjut saat ini'].map((itemOption) => <option key={itemOption}>{itemOption}</option>)}</select></label><label className="field"><span>Catatan dokter</span><textarea rows={3} value={note} onChange={(event) => setNote(event.target.value)} placeholder="Tuliskan hasil tinjauan dengan bahasa yang mudah dipahami. Jangan menulis diagnosis dari hasil skrining saja." /></label>{error && <div className="form-error" role="alert">{error}</div>}<div className="modal-actions"><Button variant="outline" onClick={onClose} disabled={saving}>Tutup</Button><Button type="submit" icon="check" disabled={saving}>{saving ? 'Menyimpan…' : 'Simpan tinjauan dokter'}</Button></div></form>}
  </ModalShell>;
}

function ActivityPhoto({ item, alt = 'Foto kegiatan tersimpan' }: LooseProps) {
  const [source, setSource] = useState('');
  const [failed, setFailed] = useState(false);
  useEffect(() => {
    let active = true;
    if (!item?.mediaAvailable && !item?.photoAvailable) { setSource(''); return () => { active = false; }; }
    apiGet(`activities/${encodeURIComponent(item.id)}/photo`).then((result) => {
      if (active) setSource(result.data_url || '');
    }).catch(() => { if (active) setFailed(true); });
    return () => { active = false; };
  }, [item?.id, item?.photoAvailable, item?.mediaAvailable]);
  if (!item?.mediaAvailable && !item?.photoAvailable) return null;
  if (failed) return <div className="activity-photo-fallback">Media tidak dapat dimuat untuk akun ini.</div>;
  return source ? <figure className="activity-photo-preview">{item.mediaContentType?.startsWith('video/') ? <video src={source} controls aria-label={alt} /> : <img src={source} alt={alt} />}<figcaption>Media privat · akses mengikuti hak catatan kegiatan</figcaption></figure> : <div className="activity-photo-fallback">Memuat media dengan sesi akun…</div>;
}

function ModalActivityDetail({ item, child, onClose }: LooseProps) {
  const nutrition = item.meal?.nutrition;
  return <ModalShell title={item.title} subtitle={`${child?.name || 'Profil anak'} · ${item.createdAt} · ${item.time}`} onClose={onClose}>
    <div className="detail-category-row"><Pill tone="warm">{item.category}</Pill><Pill tone={item.shared ? 'sage' : 'neutral'}>{item.shared ? 'Dibagikan ke keluarga' : 'Catatan internal'}</Pill></div>
    <ActivityPhoto item={item} alt={`Foto ilustrasi kegiatan: ${item.title}`} />
    {item.meal && <section className="meal-nutrition-snapshot"><strong>{item.meal.name}</strong><small>Gabungan terhitung · sekitar {item.meal.serving_grams} g</small>{item.meal.items?.length > 0 && <ul className="meal-snapshot-items">{item.meal.items.map((mealItem, index) => <li key={`${mealItem.id}-${index}`}>{mealItem.name} · {mealItem.servings} × {mealItem.serving_label} ({mealItem.total_grams} g)</li>)}</ul>}<div className="nutrition-chip-row">{[['Energi', nutrition?.energy_kcal, 'kkal'], ['Protein', nutrition?.protein_g, 'g'], ['Karbohidrat', nutrition?.carbohydrate_g, 'g'], ['Lemak', nutrition?.fat_g, 'g'], ['Serat', nutrition?.fiber_g, 'g']].map(([label, value, unit]) => <span key={label}><small>{label}</small><strong>{value ?? '—'} {unit}</strong></span>)}</div>{item.meal.allergens && <small>Informasi alergen: {item.meal.allergens}</small>}<small>Snapshot memakai nilai katalog saat catatan disimpan; bahan tambahan dan cara olah di luar katalog tidak dihitung.</small></section>}
    <div className="activity-detail-note"><span>Catatan sesi</span><p>{item.note}</p></div>
    <div className="detail-line"><span>Sesi & partisipasi</span><strong>{item.session}{item.participation ? ` · ${item.participation}` : ''}</strong></div>
    {item.durationMinutes && <div className="detail-line"><span>Durasi</span><strong>{item.durationMinutes} menit</strong></div>}
    {item.waterMl != null && <div className="detail-line"><span>Asupan minum tercatat</span><strong>{item.waterMl} ml</strong></div>}
    {item.mood && <div className="detail-line"><span>Suasana hati</span><strong>{item.mood}</strong></div>}
    <div className="detail-line"><span>Sumber</span><strong>{item.source}</strong></div>
    <div className="info-footnote"><Icon name="info" size={15} /><span>Catatan ini adalah observasi kegiatan, bukan kesimpulan klinis. Nilai gizi adalah estimasi katalog per porsi, bukan penilaian kebutuhan diet.</span></div><div className="modal-actions"><Button onClick={onClose}>Tutup detail</Button></div>
  </ModalShell>;
}

function Toast({ message, type = 'success', onClose }: LooseProps) {
  useEffect(() => { if (!message) return undefined; const timer = window.setTimeout(onClose, 4200); return () => window.clearTimeout(timer); }, [message, onClose]);
  if (!message) return null;
  return <div className={`toast toast-${type}`} role="status" aria-live="polite"><span className="toast-icon"><Icon name={type === 'success' ? 'check' : 'info'} size={16} /></span><span>{message}</span><button className="icon-button" onClick={onClose} aria-label="Tutup notifikasi"><Icon name="close" size={15} /></button></div>;
}

interface AppProps { user: AuthUser; onLogout: () => void }

export default function App({ user, onLogout }: AppProps): React.JSX.Element {
  const [data, setData] = useState(copySeed);
  const role = user?.role || 'caregiver';
  const storageKey = `${STORE_KEY}:${user?.id || 'anonymous'}`;
  const [hydratedKey, setHydratedKey] = useState('');
  const hydrated = hydratedKey === storageKey;
  const [section, setSection] = useState('home');
  const [messageTarget, setMessageTarget] = useState({ childId: '', contactId: '' });
  const [selectedId, setSelectedId] = useState('a');
  const [search, setSearch] = useState('');
  const [filter, setFilter] = useState('Semua');
  const [mobileOpen, setMobileOpen] = useState(false);
  const [notificationsOpen, setNotificationsOpen] = useState(false);
  const [notificationsHydrated, setNotificationsHydrated] = useState(false);
  const [notificationPermission, setNotificationPermission] = useState('default');
  const seenNotificationIdsRef = useRef<Set<string> | null>(null);
  const browserNotifiedIdsRef = useRef(new Set<string>());
  const [modal, setModal] = useState(null);
  const [toastMessage, setToastMessage] = useState('');
  const [toastType, setToastType] = useState('success');
  const [insightLoadState, setInsightLoadState] = useState<'idle' | 'loading' | 'ready' | 'error'>('idle');
  const [insightLoadError, setInsightLoadError] = useState('');
  const [insightStatusChildId, setInsightStatusChildId] = useState('');
  const [insightReloadCount, setInsightReloadCount] = useState(0);

  useEffect(() => {
    setData(loadDemo(storageKey));
    setNotificationsHydrated(false);
    seenNotificationIdsRef.current = null;
    browserNotifiedIdsRef.current.clear();
    setHydratedKey(storageKey);
  }, [storageKey]);
  useEffect(() => {
    if (typeof window !== 'undefined' && 'Notification' in window) setNotificationPermission(window.Notification.permission);
  }, []);
  useEffect(() => {
    if (!hydrated) return;
    try { window.localStorage.setItem(storageKey, JSON.stringify(data)); } catch { /* local browser storage is optional */ }
  }, [data, hydrated, storageKey]);
  useEffect(() => {
    if (!notificationsHydrated) return;
    const current = new Set<string>((data.notifications || []).map((item) => String(item.id)));
    if (seenNotificationIdsRef.current === null) {
      seenNotificationIdsRef.current = current;
      return;
    }
    const previous = seenNotificationIdsRef.current;
    if (typeof window !== 'undefined' && 'Notification' in window && window.Notification.permission === 'granted') {
      for (const item of data.notifications || []) {
        if (previous.has(String(item.id)) || browserNotifiedIdsRef.current.has(String(item.id))) continue;
        if (item.category === 'reminder' && item.dueAt && new Date(item.dueAt).getTime() > Date.now()) continue;
        try {
          new window.Notification(item.title, { body: item.body, tag: String(item.id) });
          browserNotifiedIdsRef.current.add(String(item.id));
        } catch { /* Browser pop-ups are optional; the saved in-app center remains available. */ }
      }
    }
    seenNotificationIdsRef.current = current;
  }, [data.notifications, notificationsHydrated]);

  useEffect(() => {
    if (!notificationsHydrated || notificationPermission !== 'granted' || typeof window === 'undefined' || !('Notification' in window)) return undefined;
    const notifyDueReminders = () => {
      const now = Date.now();
      for (const item of data.notifications || []) {
        const dueTime = item.dueAt ? new Date(item.dueAt).getTime() : Number.NaN;
        if (item.category !== 'reminder' || item.completedAt || !Number.isFinite(dueTime) || dueTime > now || dueTime < now - 24 * 60 * 60 * 1000) continue;
        if (browserNotifiedIdsRef.current.has(String(item.id))) continue;
        try {
          new window.Notification(item.title, { body: item.body, tag: String(item.id) });
          browserNotifiedIdsRef.current.add(String(item.id));
        } catch { /* Permission may change between the check and display. */ }
      }
    };
    notifyDueReminders();
    const timer = window.setInterval(notifyDueReminders, 10000);
    return () => window.clearInterval(timer);
  }, [data.notifications, notificationPermission, notificationsHydrated]);

  useEffect(() => {
    if (!hydrated || !['caregiver', 'doctor', 'parent', 'admin'].includes(role)) return undefined;
    let active = true;
    let inFlight = false;
    const refreshSharedData = async () => {
      if (!active || inFlight || !hasSessionToken()) return;
      inFlight = true;
      try {
        const clinicalStaff = role === 'caregiver' || role === 'doctor';
        const familyOrStaff = clinicalStaff || role === 'parent';
        const operationalStaff = clinicalStaff || role === 'admin';
        const [activityResult, messageResult, notificationResult, sensorResult, attendanceResult, observationResult, linkResult, childrenResult, mealResult, reportResult, modelStatusResult] = await Promise.allSettled([
          familyOrStaff ? apiGet('activities') : Promise.resolve(null),
          familyOrStaff ? apiGet('messages') : Promise.resolve(null),
          familyOrStaff ? apiGet('notifications') : Promise.resolve(null),
          operationalStaff ? apiGet('sensors/summary') : Promise.resolve(null),
          apiGet('attendance'),
          clinicalStaff ? apiGet('observations') : Promise.resolve(null),
          operationalStaff ? apiGet('children/links') : Promise.resolve(null),
          apiGet('children'),
          apiGet('meals/catalog'),
          role === 'admin' ? Promise.resolve(null) : apiGet('development/reports'),
          role === 'admin' ? Promise.resolve(null) : apiGet('development/model-status'),
        ]);
        if (!active || !hasSessionToken()) return;
        const assessmentChildIds = role === 'admin' ? [] : (user?.child_ids || []);
        const assessmentResults = assessmentChildIds.length
          ? await Promise.allSettled(assessmentChildIds.map((childId) => apiGet(`kpsp/children/${encodeURIComponent(childId)}/assessments`)))
          : [];
        if (!active) return;
        const activityPayload = activityResult.status === 'fulfilled' ? activityResult.value : null;
        const messagePayload = messageResult.status === 'fulfilled' ? messageResult.value : null;
        const notificationPayload = notificationResult.status === 'fulfilled' ? notificationResult.value : null;
        const sensorPayload = sensorResult.status === 'fulfilled' ? sensorResult.value : null;
        const attendancePayload = attendanceResult.status === 'fulfilled' ? attendanceResult.value : null;
        const observationPayload = observationResult.status === 'fulfilled' ? observationResult.value : null;
        const linkPayload = linkResult.status === 'fulfilled' ? linkResult.value : null;
        const childrenPayload = childrenResult.status === 'fulfilled' ? childrenResult.value : null;
        const mealPayload = mealResult.status === 'fulfilled' ? mealResult.value : null;
        const reportPayload = reportResult.status === 'fulfilled' ? reportResult.value : null;
        const modelStatusPayload = modelStatusResult.status === 'fulfilled' ? modelStatusResult.value : null;
        const serverNotifications = notificationPayload ? (notificationPayload.notifications || []).map(mapNotification) : null;
        const sensorLatest = sensorPayload?.latest;
        const sensorState = sensorPayload ? {
          connected: Boolean(sensorPayload.connected),
          fresh: Boolean(sensorPayload.fresh),
          temperature: sensorLatest?.temperature_c ?? null,
          humidity: sensorLatest?.humidity_pct ?? null,
          updatedAt: sensorLatest?.measured_at ? new Intl.DateTimeFormat('id-ID', { day: '2-digit', month: 'short', hour: '2-digit', minute: '2-digit', timeZone: 'Asia/Jakarta' }).format(new Date(sensorLatest.measured_at)) : null,
          roomId: sensorLatest?.room_id || null,
          deviceId: sensorLatest?.device_id || null,
          readings: (sensorPayload.readings || []).map((item) => ({ temperature: item.temperature_c, humidity: item.humidity_pct, measuredAt: item.measured_at })),
        } : null;
        const records = activityPayload ? (activityPayload.activities || []).map((record) => ({
          id: record.id,
          childId: record.child_id,
          category: record.category,
          title: record.title,
          note: record.note,
          session: record.session,
          time: record.time,
          shared: record.shared,
          source: 'Pengasuh',
          createdAt: new Intl.DateTimeFormat('id-ID', { day: '2-digit', month: 'short', year: 'numeric', timeZone: 'Asia/Jakarta' }).format(new Date(record.created_at)),
          createdAtIso: record.created_at,
          announcement: record.announcement,
          durationMinutes: record.duration_minutes,
          mood: record.mood,
          participation: record.participation,
          waterMl: record.water_ml,
          mealId: record.meal_id,
          mealServings: record.meal_servings,
          meal: record.meal,
          photoAvailable: record.photo_available,
          mediaAvailable: record.media_available,
          mediaContentType: record.media_content_type,
        })) : null;
        const observations = observationPayload ? (observationPayload.observations || []).map((record) => ({
          id: record.id,
          childId: record.child_id,
          aspect: record.aspect,
          milestone: record.milestone,
          reference: record.reference,
          result: record.result,
          context: record.context,
          note: record.note,
          time: record.time,
          observer: record.observer,
          createdAt: record.created_at,
          date: new Intl.DateTimeFormat('id-ID', { day: '2-digit', month: 'short', year: 'numeric', timeZone: 'Asia/Jakarta' }).format(new Date(record.created_at)),
        })) : null;
        const meals = mealPayload ? (mealPayload.meals || []).map((record) => ({
          id: record.id, name: record.name, servingLabel: record.serving_label, servingGrams: record.serving_grams,
          energyKcal: record.energy_kcal, proteinG: record.protein_g, carbohydrateG: record.carbohydrate_g,
          fatG: record.fat_g, fiberG: record.fiber_g, allergens: record.allergens, notes: record.notes,
          source: record.source, sourceUrl: record.source_url, createdAt: record.created_at,
        })) : null;
        const developmentReports = reportPayload ? (reportPayload.reports || []).map((record) => ({
          id: record.id, childId: record.child_id, periodStart: record.period_start, periodEnd: record.period_end,
          summary: record.summary, observationStats: record.observation_stats, status: record.status,
          createdBy: record.created_by, createdAt: record.created_at, reviewed: Boolean(record.reviewed_at),
          published: Boolean(record.published), publishedAt: record.published_at,
        })) : null;
        const serverChildren = childrenPayload ? (childrenPayload.children || []).map((record) => {
          const age = calculateAgeAt(record.birth_date, todayIsoDate());
          return {
            id: record.id,
            name: record.name,
            ageMonths: age?.roundedMonths ?? 0,
            birthDate: record.birth_date || '',
            room: record.room || 'Belum ditetapkan',
            attendance: 'Belum dicatat',
            checkIn: 'Belum dicatat',
            checkOut: 'Belum dicatat',
            pickupPersonName: '',
            note: '',
            status: record.status,
          };
        }) : null;
        const serverMessages = (messagePayload?.messages || []).map((message) => ({
          id: message.id,
          childId: message.child_id || 'all',
          author: message.author,
          role: message.role,
          senderId: message.sender_id,
          recipientId: message.recipient_id,
          recipientName: message.recipient_name,
          recipientRole: message.recipient_role,
          text: message.text,
          time: message.time,
          createdAt: message.created_at,
          kind: message.kind,
          isDirect: Boolean(message.is_direct),
          relatedActivityId: message.related_activity_id,
          read: false,
          source: message.is_direct ? 'Percakapan langsung' : 'Pesan tersimpan',
        }));
        const assessmentReadSucceeded = assessmentResults.every((result) => result.status === 'fulfilled');
        const serverAssessments = assessmentResults.flatMap((result) => result.status === 'fulfilled' ? (result.value.assessments || []) : []);
        const mappedAssessments = serverAssessments.map((record) => {
          const createdAt = record.created_at
            ? new Intl.DateTimeFormat('id-ID', { day: '2-digit', month: 'short', year: 'numeric', timeZone: 'Asia/Jakarta' }).format(new Date(record.created_at))
            : shortDateLabel;
          return {
            id: record.id,
            childId: record.child_id,
            actualAgeMonths: record.actual_age_months,
            birthDate: record.birth_date,
            screeningDate: record.screening_date,
            screeningAgeMonths: record.screening_age_months,
            screeningMode: record.screening_mode,
            status: record.status,
            answers: record.answers,
            answered: record.score?.answered_count ?? record.score?.yes_count,
            totalItems: record.score?.total_items,
            date: createdAt,
            score: record.score,
            sourceVersion: record.source_version,
            backendConnected: true,
            reviewed: record.reviewed,
            published: record.published,
            decision: record.review_decision,
            note: record.review_note,
          };
        });
        const remoteQueue = mappedAssessments.filter((item) => item.status === 'submitted').map((item) => ({
          id: item.id,
          childId: item.childId,
          domain: `KPSP · ${item.screeningAgeMonths} bulan`,
          priority: item.reviewed ? 'Sudah ditinjau' : 'Menunggu tinjauan',
          evidenceCount: item.answered,
          observationCount: 0,
          kpspCount: 1,
          ageMonths: item.actualAgeMonths,
          actualAgeMonths: item.actualAgeMonths,
          reason: item.score?.result_label ? `Hasil skrining: ${item.score.result_label} · ${item.score.yes_count}/${item.score.total_items} jawaban Ya. Hasil ini bukan diagnosis.` : 'Hasil KPSP menunggu tinjauan dokter.',
          date: item.date,
          reviewed: Boolean(item.reviewed),
          published: Boolean(item.published),
          note: item.note || '',
          decision: item.decision || '',
          assessmentId: item.id,
          screeningMode: item.screeningMode,
          screeningAgeMonths: item.screeningAgeMonths,
          kpspResult: item.score,
        }));
        const anyAssessmentSuccess = assessmentResults.some((result) => result.status === 'fulfilled');
        if (notificationPayload) setNotificationsHydrated(true);
        if (!records && !messagePayload && !notificationPayload && !sensorPayload && !attendancePayload && !observations && !linkPayload && !childrenPayload && !meals && !developmentReports && !modelStatusPayload && !anyAssessmentSuccess) return;
        setData((current) => {
          const nextActivities = role === 'admin' ? [] : (records || current.activities);
          const nextObservations = role === 'admin' ? [] : (observations || current.observations || []);
          const nextNotifications = role === 'admin' ? [] : (serverNotifications || current.notifications || []);
          const nextSensor = sensorState || current.sensor;
          const nextMessages = role === 'admin' ? [] : messagePayload
            ? serverMessages
            : current.messages.filter((message) => !message.sourceActivityId);
          const attendanceByChild = new Map<string, any>((attendancePayload?.attendance || []).map((item: any) => [String(item.child_id), item] as [string, any]));
          const baseChildren = serverChildren || current.children;
          const nextChildren = baseChildren.map((child) => {
            const item = attendanceByChild.get(child.id);
            return {
              ...child,
              attendance: item?.status || (serverChildren ? 'Belum dicatat' : child.attendance),
              checkIn: item?.check_in || (serverChildren ? 'Belum dicatat' : child.checkIn),
              checkOut: item?.check_out || (serverChildren ? 'Belum dicatat' : child.checkOut || 'Belum dicatat'),
              pickupPersonName: item?.pickup_person_name || (serverChildren ? '' : child.pickupPersonName || ''),
            };
          });
          const childrenChanged = JSON.stringify(nextChildren.map((child) => [child.id, child.name, child.room, child.ageMonths, child.attendance, child.checkIn, child.checkOut, child.pickupPersonName, child.status]))
            !== JSON.stringify(current.children.map((child) => [child.id, child.name, child.room, child.ageMonths, child.attendance, child.checkIn, child.checkOut, child.pickupPersonName, child.status]));
          const nextLinkedChildIds = linkPayload?.child_ids ?? (current.linkedChildIds || []);
          const linkedChildrenChanged = JSON.stringify(nextLinkedChildIds) !== JSON.stringify(current.linkedChildIds || []);
          const nextAssessments = role === 'admin' ? [] : (assessmentReadSucceeded ? mappedAssessments : current.assessments);
          const nextQueue = role === 'admin' ? [] : (assessmentReadSucceeded ? remoteQueue : current.queue);
          const nextMeals = meals || current.meals || [];
          const nextDevelopmentReports = role === 'admin' ? [] : (developmentReports || current.developmentReports || []);
          const nextModelStatus = role === 'admin' ? null : (modelStatusPayload || current.modelStatus);
          const notificationsChanged = JSON.stringify(nextNotifications.map((item) => [item.id, item.readAt, item.completedAt])) !== JSON.stringify((current.notifications || []).map((item) => [item.id, item.readAt, item.completedAt]));
          const sensorChanged = JSON.stringify(nextSensor) !== JSON.stringify(current.sensor);
          const queueState = (items) => items.map((item) => [item.id, item.reviewed, item.published, item.note, item.decision]);
          const assessmentState = (items) => items.map((item) => [item.id, item.status, item.reviewed, item.published, item.note]);
          const kpspChanged = JSON.stringify(queueState(nextQueue)) !== JSON.stringify(queueState(current.queue))
            || JSON.stringify(assessmentState(nextAssessments)) !== JSON.stringify(assessmentState(current.assessments));
          const observationsChanged = JSON.stringify(nextObservations.map((item) => item.id)) !== JSON.stringify((current.observations || []).map((item) => item.id));
          const mealsChanged = JSON.stringify(nextMeals) !== JSON.stringify(current.meals || []);
          const reportsChanged = JSON.stringify(nextDevelopmentReports.map((item) => [item.id, item.status, item.published, item.summary])) !== JSON.stringify((current.developmentReports || []).map((item) => [item.id, item.status, item.published, item.summary]));
          const modelStatusChanged = JSON.stringify(nextModelStatus) !== JSON.stringify(current.modelStatus);
          const activitiesChanged = JSON.stringify(nextActivities.map((item) => [item.id, item.photoAvailable, item.meal, item.shared])) !== JSON.stringify(current.activities.map((item) => [item.id, item.photoAvailable, item.meal, item.shared]));
          const messagesChanged = JSON.stringify(nextMessages.map((item) => item.id)) !== JSON.stringify(current.messages.map((item) => item.id));
          const sensitiveAdminDataPresent = role === 'admin' && (
            current.activities.length > 0 || current.messages.length > 0 || current.notifications.length > 0
            || (current.observations || []).length > 0 || (current.assessments || []).length > 0
            || (current.queue || []).length > 0 || (current.developmentReports || []).length > 0
            || Object.keys(current.consents || {}).length > 0 || (current.insights || []).length > 0
            || Boolean(current.modelStatus || current.insightMeta)
          );
          if (!activitiesChanged && !messagesChanged && !notificationsChanged && !sensorChanged && !childrenChanged && !kpspChanged && !observationsChanged && !linkedChildrenChanged && !mealsChanged && !reportsChanged && !modelStatusChanged && !sensitiveAdminDataPresent) return current;
          return {
            ...current,
            activities: nextActivities,
            messages: nextMessages,
            notifications: nextNotifications,
            sensor: nextSensor,
            children: nextChildren,
            linkedChildIds: nextLinkedChildIds,
            observations: nextObservations,
            assessments: nextAssessments,
            queue: nextQueue,
            meals: nextMeals,
            developmentReports: nextDevelopmentReports,
            modelStatus: nextModelStatus,
            consents: role === 'admin' ? {} : current.consents,
            insights: role === 'admin' ? [] : current.insights,
            insightMeta: role === 'admin' ? null : current.insightMeta,
          };
        });
      } catch {
        // Data yang sudah dimuat tetap terlihat bila sambungan sementara terhenti.
      } finally {
        inFlight = false;
      }
    };
    void refreshSharedData();
    const timer = window.setInterval(refreshSharedData, 10000);
    return () => { active = false; window.clearInterval(timer); };
  }, [hydrated, role, user?.child_ids?.join('|')]);

  const visibleChildren = useMemo(() => role === 'parent'
    ? data.children.filter((child) => (user?.child_ids || []).includes(child.id))
    : data.children, [data.children, role, user?.child_ids]);
  const activeChild = visibleChildren.find((child) => child.id === selectedId) || visibleChildren[0] || null;
  const activeInsightLoadState = insightStatusChildId === activeChild?.id ? insightLoadState : activeChild?.id ? 'loading' : 'idle';
  const activeInsightLoadError = insightStatusChildId === activeChild?.id ? insightLoadError : '';
  const refreshInsights = () => setInsightReloadCount((count) => count + 1);
  useEffect(() => {
    if (!hydrated || !hasSessionToken() || !['caregiver', 'doctor'].includes(role) || !activeChild?.id) {
      setInsightLoadState('idle');
      setInsightLoadError('');
      setInsightStatusChildId('');
      return undefined;
    }
    let active = true;
    setInsightStatusChildId(activeChild.id);
    setInsightLoadState('loading');
    setInsightLoadError('');
    apiGet(`development/insights/${encodeURIComponent(activeChild.id)}?days=90`).then((result) => {
      if (!active) return;
      setData((current) => ({ ...current, insights: result.insights || [], insightMeta: result }));
      setInsightLoadState('ready');
    }).catch((cause) => {
      if (!active) return;
      setData((current) => ({ ...current, insights: [], insightMeta: null }));
      setInsightLoadError(cause instanceof ApiError ? cause.message : 'Periksa sambungan dan akses akun, lalu coba lagi.');
      setInsightLoadState('error');
    });
    return () => { active = false; };
  }, [hydrated, role, activeChild?.id, data.observations, insightReloadCount]);
  const navItems = NAV[role];
  const allNavIds = navItems.flatMap((group) => group.items.map((item) => item.id));

  const showToast = (message, type = 'success') => { setToastType(type); setToastMessage(message); };
  const closeToast = () => setToastMessage('');
  const saveStimulationFeedback = async (childId: string, payload: DashboardRecord) => {
    try {
      await apiPost(`development/stimulation/${encodeURIComponent(childId)}/feedback`, payload);
      showToast('Feedback aktivitas tersimpan. Saran berikutnya akan menyesuaikan riwayat ini.');
      setInsightReloadCount((count) => count + 1);
      return true;
    } catch (cause) {
      showToast(cause instanceof ApiError ? cause.message : 'Feedback belum tersimpan. Coba lagi.', 'error');
      return false;
    }
  };
  const go = (nextSection) => { setSection(nextSection); setMobileOpen(false); setNotificationsOpen(false); };
  const requestBrowserNotifications = async () => {
    if (typeof window === 'undefined' || !('Notification' in window)) {
      showToast('Browser ini tidak mendukung notifikasi desktop. Pemberitahuan tetap tersimpan di aplikasi.', 'error');
      return;
    }
    if (!window.isSecureContext) {
      showToast('Notifikasi browser memerlukan koneksi HTTPS atau localhost yang aman.', 'error');
      return;
    }
    try {
      const permission = await window.Notification.requestPermission();
      setNotificationPermission(permission);
      showToast(permission === 'granted' ? 'Notifikasi browser diaktifkan saat aplikasi terbuka. Push saat aplikasi tertutup belum tersedia.' : 'Izin notifikasi browser belum diberikan. Pemberitahuan tetap tersimpan di aplikasi.', permission === 'granted' ? 'success' : 'error');
    } catch {
      showToast('Izin browser tidak dapat dibuka. Pemberitahuan tetap tersimpan di aplikasi.', 'error');
    }
  };
  const markNotificationRead = async (item) => {
    if (!item || item.readAt) return true;
    try {
      const response = await apiPost(`notifications/${encodeURIComponent(item.id)}/read`, {});
      const notification = mapNotification(response.notification);
      setData((current) => ({ ...current, notifications: [notification, ...(current.notifications || []).filter((entry) => entry.id !== notification.id)] }));
      return true;
    } catch (cause) {
      showToast(cause instanceof ApiError ? cause.message : 'Status baca belum tersimpan. Coba lagi.', 'error');
      return false;
    }
  };
  const openNotification = async (item) => {
    await markNotificationRead(item);
    if (item.title === 'Feedback aktivitas baru') {
      if (item.childId) setSelectedId(item.childId);
      setNotificationsOpen(false);
      go('recommendations');
      return;
    }
    if ((item.category === 'photo' || item.category === 'activity') && item.relatedActivityId) {
      const activity = data.activities.find((entry) => entry.id === item.relatedActivityId);
      if (activity) { setModal({ type: 'activity-detail', item: activity }); setNotificationsOpen(false); return; }
      go('activities');
      return;
    }
    if (item.category === 'message' && item.relatedMessageId) {
      const message = data.messages.find((entry) => entry.id === item.relatedMessageId && entry.isDirect);
      if (message) {
        const contactId = message.senderId === user?.id ? message.recipientId : message.senderId;
        setMessageTarget({ childId: message.childId, contactId });
      }
    }
    go('messages');
  };
  const completeReminder = async (item) => {
    try {
      const response = await apiPost(`notifications/${encodeURIComponent(item.id)}/complete`, {});
      const notification = mapNotification(response.notification);
      setData((current) => ({ ...current, notifications: [notification, ...(current.notifications || []).filter((entry) => entry.id !== notification.id)] }));
      showToast('Pengingat ditandai selesai.');
    } catch (cause) {
      showToast(cause instanceof ApiError ? cause.message : 'Pengingat belum dapat diselesaikan.', 'error');
    }
  };
  const saveReminder = async (payload) => {
    try {
      const response = await apiPost('notifications/reminders', {
        child_id: payload.childId, audience: payload.audience, title: payload.title, body: payload.body, due_at: payload.dueAt,
      });
      const notification = mapNotification(response.notification);
      if (payload.audience === 'self') setData((current) => ({ ...current, notifications: [notification, ...(current.notifications || []).filter((entry) => entry.id !== notification.id)] }));
      setModal(null);
      showToast(payload.audience === 'family' ? `Pengingat tersimpan untuk ${response.recipient_count} akun keluarga.` : 'Pengingat tersimpan untuk akun pengasuh ini.');
      return true;
    } catch (cause) {
      showToast(cause instanceof ApiError ? cause.message : 'Pengingat belum tersimpan. Coba lagi.', 'error');
      return false;
    }
  };
  const updateTask = (taskId) => setData((current) => ({ ...current, tasks: current.tasks.map((task) => task.id === taskId ? { ...task, done: !task.done } : task) }));
  const checkInAttendance = async (childId) => {
    const child = data.children.find((item) => item.id === childId);
    if (!child) return false;
    try {
      const response = await apiPost('attendance/check-in', { child_id: childId });
      const saved = response.attendance;
      setData((current) => ({
        ...current,
        children: current.children.map((item) => item.id === childId
          ? { ...item, attendance: saved.status, checkIn: saved.check_in, checkOut: saved.check_out, pickupPersonName: saved.pickup_person_name || '' }
          : item),
        __role: role,
        audit: addAudit({ ...current, __role: role }, 'Check-in anak dicatat', childId, 'Waktu dan petugas tersimpan'),
      }));
      showToast(`Check-in ${child.name} berhasil dicatat.`);
      return true;
    } catch (cause) {
      showToast(cause instanceof ApiError ? cause.message : 'Check-in belum tersimpan. Coba lagi.', 'error');
      return false;
    }
  };

  const checkOutAttendance = async ({ childId, pickupAuthorizationId }) => {
    const child = data.children.find((item) => item.id === childId);
    if (!child) return false;
    try {
      const response = await apiPost('attendance/check-out', {
        child_id: childId,
        pickup_authorization_id: pickupAuthorizationId,
        pickup_name_match_confirmed: true,
      });
      const saved = response.attendance;
      setData((current) => ({
        ...current,
        children: current.children.map((item) => item.id === childId
          ? { ...item, attendance: saved.status, checkIn: saved.check_in, checkOut: saved.check_out, pickupPersonName: saved.pickup_person_name || '' }
          : item),
        __role: role,
        audit: addAudit({ ...current, __role: role }, 'Check-out dan serah-terima dicatat', childId, `Penjemput berizin: ${saved.pickup_person_name}`),
      }));
      showToast(`${child.name} diserahkan kepada ${saved.pickup_person_name}.`);
      return true;
    } catch (cause) {
      showToast(cause instanceof ApiError ? cause.message : 'Check-out belum tersimpan. Coba lagi.', 'error');
      return false;
    }
  };
  const markAttendanceStatus = async (childId, status) => {
    const child = data.children.find((item) => item.id === childId);
    if (!child) return false;
    try {
      const response = await apiPost('attendance', { child_id: childId, status });
      const saved = response.attendance;
      setData((current) => ({
        ...current,
        children: current.children.map((item) => item.id === childId
          ? { ...item, attendance: saved.status, checkIn: saved.check_in, checkOut: saved.check_out, pickupPersonName: saved.pickup_person_name || '' }
          : item),
        __role: role,
        audit: addAudit({ ...current, __role: role }, `Status kehadiran dicatat: ${saved.status}`, childId, 'Kehadiran tersimpan'),
      }));
      showToast(`Status ${child.name} berhasil dicatat.`);
      return true;
    } catch (cause) {
      showToast(cause instanceof ApiError ? cause.message : 'Status kehadiran belum tersimpan. Coba lagi.', 'error');
      return false;
    }
  };

  const toggleConsent = (childId) => {
    const nextVisible = data.consents[childId] !== true;
    setData((current) => ({ ...current, consents: { ...current.consents, [childId]: nextVisible } }));
    showToast(nextVisible ? 'Saran perkembangan ditampilkan pada akun ini.' : 'Saran perkembangan disembunyikan pada akun ini.');
  };

  const saveActivity = async (payload) => {
    const childIds = payload.childIds?.length ? payload.childIds : [payload.childId];
    const savedItems = [];
    try {
      for (const childId of childIds) {
        const child = data.children.find((item) => item.id === childId);
        const result = await apiPost('activities', {
        child_id: childId,
        child_name: child?.name || 'Profil anak',
        category: payload.category,
        title: payload.title,
        note: payload.note,
        session: payload.session,
        time: payload.time,
        share_to_parent: payload.shared,
        duration_minutes: payload.durationMinutes,
        mood: payload.mood,
        participation: payload.participation,
        water_ml: payload.waterMl,
        meal_items: (payload.mealItems || []).map((item) => ({ meal_id: item.mealId, servings: item.servings })),
        media_data_url: payload.mediaDataUrl,
        media_consent_confirmed: payload.mediaConsentConfirmed,
        });
        const record = result.activity;
        const createdAt = record.created_at
          ? new Intl.DateTimeFormat('id-ID', { day: '2-digit', month: 'short', year: 'numeric', timeZone: 'Asia/Jakarta' }).format(new Date(record.created_at))
          : shortDateLabel;
        savedItems.push({
          id: record.id, childId: record.child_id, category: record.category, title: record.title,
          note: record.note, session: record.session, time: record.time, shared: record.shared,
          source: 'Pengasuh', createdAt, announcement: record.announcement,
          durationMinutes: record.duration_minutes, mood: record.mood, participation: record.participation,
          waterMl: record.water_ml, mealId: record.meal_id, mealServings: record.meal_servings,
          meal: record.meal, photoAvailable: record.photo_available,
          mediaAvailable: record.media_available, mediaContentType: record.media_content_type,
        });
      }
    } catch (cause) {
      showToast(cause instanceof ApiError ? cause.message : 'Catatan belum tersimpan. Coba lagi.', 'error');
      return;
    }
    const first = savedItems[0];
    setData((current) => ({ ...current, activities: [...savedItems, ...current.activities.filter((entry) => !savedItems.some((item) => item.id === entry.id))], __role: role, audit: addAudit({ ...current, __role: role }, first.shared ? 'Catatan kegiatan disimpan dan dibagikan' : 'Catatan kegiatan disimpan', first.childId, `${savedItems.length} profil · Aktivitas · ${first.category} · ${first.time}`) }));
    setModal(null);
    showToast(`${savedItems.length} catatan tersimpan${first.shared ? ' dan dibagikan ke keluarga' : ''}.`);
  };

  const saveMeal = async (payload) => {
    try {
      const response = await apiPost('meals/catalog', {
        name: payload.name, serving_label: payload.servingLabel, serving_grams: payload.servingGrams,
        energy_kcal: payload.energyKcal, protein_g: payload.proteinG, carbohydrate_g: payload.carbohydrateG,
        fat_g: payload.fatG, fiber_g: payload.fiberG, allergens: payload.allergens, notes: payload.notes,
        source: payload.source, source_url: payload.sourceUrl,
      });
      const record = response.meal;
      const meal = { id: record.id, name: record.name, servingLabel: record.serving_label, servingGrams: record.serving_grams, energyKcal: record.energy_kcal, proteinG: record.protein_g, carbohydrateG: record.carbohydrate_g, fatG: record.fat_g, fiberG: record.fiber_g, allergens: record.allergens, notes: record.notes, source: record.source, sourceUrl: record.source_url, createdAt: record.created_at };
      setData((current) => ({ ...current, meals: [meal, ...(current.meals || []).filter((item) => item.id !== meal.id)] }));
      setModal(null);
      showToast('Menu dan nilai gizi tersimpan. Nilai dicatat per porsi.');
    } catch (cause) {
      showToast(cause instanceof ApiError ? cause.message : 'Menu belum tersimpan. Periksa nilai lalu coba lagi.', 'error');
    }
  };

  const createQuarterlyReport = async (payload) => {
    try {
      const response = await apiPost('development/reports', { child_id: payload.childId, period_start: payload.periodStart, period_end: payload.periodEnd, summary: payload.summary });
      const record = response.report;
      const report = { id: record.id, childId: record.child_id, periodStart: record.period_start, periodEnd: record.period_end, summary: record.summary, observationStats: record.observation_stats, status: record.status, createdBy: record.created_by, createdAt: record.created_at, reviewed: Boolean(record.reviewed_at), published: Boolean(record.published), publishedAt: record.published_at };
      setData((current) => ({ ...current, developmentReports: [report, ...(current.developmentReports || []).filter((item) => item.id !== report.id)] }));
      setModal(null);
      showToast('Draf laporan tiga bulanan tersimpan; hanya terlihat oleh pengasuh dan dokter sampai ditinjau.');
    } catch (cause) {
      showToast(cause instanceof ApiError ? cause.message : 'Draf laporan belum tersimpan. Periksa periode lalu coba lagi.', 'error');
    }
  };

  const publishQuarterlyReport = async (report) => {
    try {
      const response = await apiPost(`development/reports/${encodeURIComponent(report.id)}/publish`, {});
      const record = response.report;
      const publishedReport = { ...report, status: record.status, reviewed: Boolean(record.reviewed_at), published: Boolean(record.published), publishedAt: record.published_at };
      setData((current) => ({ ...current, developmentReports: (current.developmentReports || []).map((item) => item.id === report.id ? { ...item, ...publishedReport } : item) }));
      showToast('Laporan ditinjau dan dibagikan kepada keluarga yang terhubung.');
      return true;
    } catch (cause) {
      showToast(cause instanceof ApiError ? cause.message : 'Laporan belum dapat dibagikan. Coba lagi.', 'error');
      return false;
    }
  };

  const saveChildProfileUpdate = async (payload) => {
    try {
      const response = await apiPatch(`children/${encodeURIComponent(payload.id)}`, {
        name: payload.name,
        birth_date: payload.birthDate,
        room: payload.room,
      });
      const record = response.child;
      setData((current) => ({
        ...current,
        children: current.children.map((child) => child.id === record.id
          ? { ...child, name: record.name, birthDate: record.birth_date, ageMonths: payload.ageMonths, room: record.room, status: record.status }
          : child),
        __role: role,
        audit: addAudit({ ...current, __role: role }, 'Profil roster diperbarui', record.id, `Ruang ${record.room || 'belum ditentukan'}`),
      }));
      setModal(null);
      showToast('Profil roster tersimpan di backend.');
      return true;
    } catch (cause) {
      showToast(cause instanceof ApiError ? cause.message : 'Profil belum diperbarui. Coba lagi.', 'error');
      return false;
    }
  };

  const saveChild = async (payload) => {
    if (role === 'admin' && hasSessionToken()) {
      try {
        const response = await apiPost('children', { name: payload.name, birth_date: payload.birthDate, room: payload.room });
        const record = response.child;
        const child = {
          id: record.id,
          name: record.name,
          ageMonths: payload.ageMonths,
          birthDate: record.birth_date || payload.birthDate,
          room: record.room || payload.room,
          attendance: 'Belum dicatat',
          checkIn: 'Belum dicatat',
          checkOut: 'Belum dicatat',
          pickupPersonName: '',
          note: '',
          status: record.status,
        };
        setData((current) => ({ ...current, children: [...current.children.filter((item) => item.id !== child.id), child] }));
        setSelectedId(child.id);
        setModal(null);
        showToast('Profil roster daycare tersimpan. Hubungan wali tetap perlu diverifikasi melalui proses resmi.');
      } catch (cause) {
        showToast(cause instanceof ApiError ? cause.message : 'Profil belum tersimpan. Coba lagi.', 'error');
      }
      return;
    }
    const id = uid('child');
    setData((current) => ({ ...current, children: [...current.children, { id, ...payload, attendance: 'Belum dicatat', checkIn: 'Belum dicatat', checkOut: 'Belum dicatat', pickupPersonName: '', note: 'Profil anak contoh.' }], consents: { ...current.consents, [id]: false }, __role: role, audit: addAudit({ ...current, __role: role }, 'Profil anak contoh ditambahkan', id, `Usia ${payload.ageMonths} bulan`) }));
    setSelectedId(id); setModal(null); showToast('Profil anak contoh ditambahkan ke akun ini.');
  };

  const saveObservation = async (payload) => {
    try {
      const response = await apiPost('observations', {
        child_id: payload.childId,
        aspect: payload.aspect,
        milestone: payload.milestone,
        reference: payload.reference,
        result: payload.result,
        context: payload.context,
        note: payload.note,
        time: payload.time,
      });
      const saved = response.observation;
      const observation = {
        id: saved.id,
        childId: saved.child_id,
        aspect: saved.aspect,
        milestone: saved.milestone,
        reference: saved.reference,
        result: saved.result,
        context: saved.context,
        note: saved.note,
        time: saved.time,
        observer: saved.observer,
        createdAt: saved.created_at,
        date: saved.created_at ? new Intl.DateTimeFormat('id-ID', { day: '2-digit', month: 'short', year: 'numeric', timeZone: 'Asia/Jakarta' }).format(new Date(saved.created_at)) : shortDateLabel,
      };
      setSelectedId(payload.childId);
      setData((current) => ({ ...current, observations: [observation, ...(current.observations || []).filter((item) => item.id !== observation.id)], __role: role, audit: addAudit({ ...current, __role: role }, 'Pengamatan disimpan', payload.childId, payload.aspect) }));
      setModal(null);
      showToast('Pengamatan tersimpan. Catatan ini tidak memberi nilai atau diagnosis otomatis.');
    } catch (cause) {
      showToast(cause instanceof ApiError ? cause.message : 'Pengamatan belum tersimpan. Coba lagi.', 'error');
    }
  };

  const saveKpsp = async (payload) => {
    const response = await apiPost('kpsp/assessments', {
      child_id: payload.childId,
      actual_age_months: payload.actualAgeMonths,
      birth_date: payload.birthDate,
      screening_date: payload.screeningDate,
      screening_age_months: payload.screeningAgeMonths,
      screening_mode: payload.screeningMode,
      status: payload.status,
      answers: payload.answers,
    });
    const saved = response.assessment;
    if (!saved?.id || !saved.score) throw new Error('Hasil pemeriksaan belum dapat disimpan. Coba lagi.');
    const score = saved.score;
    const savedDate = saved.created_at
      ? new Intl.DateTimeFormat('id-ID', { day: '2-digit', month: 'short', year: 'numeric', timeZone: 'Asia/Jakarta' }).format(new Date(saved.created_at))
      : shortDateLabel;
    const assessment = {
      id: saved.id,
      childId: saved.child_id,
      actualAgeMonths: saved.actual_age_months,
      birthDate: saved.birth_date,
      screeningDate: saved.screening_date,
      screeningAgeMonths: saved.screening_age_months,
      screeningMode: saved.screening_mode,
      answers: saved.answers,
      answered: score.answered_count,
      totalItems: score.total_items,
      date: savedDate,
      status: saved.status,
      score,
      sourceVersion: saved.source_version,
      backendConnected: true,
    };
    const queueItem = saved.status === 'submitted' ? {
      id: saved.id,
      childId: saved.child_id,
      domain: `KPSP · ${saved.screening_age_months} bulan`,
      priority: 'Menunggu tinjauan',
      evidenceCount: score.answered_count,
      observationCount: 0,
      kpspCount: 1,
      ageMonths: saved.actual_age_months,
      reason: `Hasil skrining: ${score.result_label || 'perlu dibaca dokter'} · ${score.yes_count}/${score.total_items} jawaban Ya. Hasil ini bukan diagnosis.`,
      date: savedDate,
      reviewed: false,
      published: false,
      note: '',
      assessmentId: saved.id,
      screeningMode: saved.screening_mode,
      actualAgeMonths: saved.actual_age_months,
      kpspResult: score,
    } : null;
    setData((current) => ({
      ...current,
      assessments: [assessment, ...current.assessments.filter((item) => item.id !== assessment.id)],
      queue: queueItem ? [queueItem, ...current.queue.filter((item) => item.id !== queueItem.id)] : current.queue,
      __role: role,
      audit: addAudit({ ...current, __role: role }, saved.status === 'submitted' ? 'Pemeriksaan KPSP dikirim untuk ditinjau' : 'Draft pemeriksaan KPSP disimpan', saved.child_id, `KPSP usia ${saved.screening_age_months} bulan · ${score.answered_count}/${score.total_items} jawaban`),
    }));
    showToast(saved.status === 'submitted'
      ? 'Hasil skrining tersimpan dan menunggu tinjauan dokter sebelum dibagikan.'
      : 'Draft pemeriksaan tersimpan.');
    return { backendConnected: true, assessment };
  };

  const saveReview = async (item) => {
    try {
      const response = await apiPost(`kpsp/assessments/${encodeURIComponent(item.id)}/review`, { decision: item.decision, note: item.note });
      const saved = response.assessment;
      const reviewedItem = { ...item, reviewed: Boolean(saved.reviewed), published: Boolean(saved.published), decision: saved.review_decision, note: saved.review_note };
      setData((current) => ({ ...current, queue: current.queue.map((row) => row.id === item.id ? { ...row, ...reviewedItem } : row), __role: role, audit: addAudit({ ...current, __role: role }, 'Hasil KPSP ditinjau dokter', item.childId, item.domain) }));
      setModal((current) => current ? { ...current, item: reviewedItem } : current);
      showToast('Tinjauan dokter tersimpan. Hasil belum dibagikan kepada keluarga.');
      return true;
    } catch (cause) {
      showToast(cause instanceof ApiError ? cause.message : 'Tinjauan belum tersimpan. Coba lagi.', 'error');
      return false;
    }
  };

  const publishReview = async (item) => {
    try {
      const response = await apiPost(`kpsp/assessments/${encodeURIComponent(item.id)}/publish`, {});
      const saved = response.assessment;
      setData((current) => ({ ...current, queue: current.queue.map((row) => row.id === item.id ? { ...row, reviewed: true, published: Boolean(saved.published), decision: saved.review_decision, note: saved.review_note } : row), __role: role, audit: addAudit({ ...current, __role: role }, 'Ringkasan KPSP dibagikan kepada keluarga', item.childId, item.domain) }));
      setModal((current) => current ? { ...current, item: { ...item, reviewed: true, published: Boolean(saved.published), decision: saved.review_decision, note: saved.review_note } } : current);
      showToast('Ringkasan ditampilkan kepada keluarga yang terhubung.');
      return true;
    } catch (cause) {
      showToast(cause instanceof ApiError ? cause.message : 'Ringkasan belum dibagikan. Coba lagi.', 'error');
      return false;
    }
  };

  const sendAnnouncement = async ({ target, text }) => {
    try {
      const response = await apiPost('messages', { child_id: target === 'all' ? null : target, text });
      const saved = response.message;
      const message = { id: saved.id, childId: saved.child_id || 'all', author: saved.author, role: saved.role, senderId: saved.sender_id, recipientId: saved.recipient_id, text: saved.text, time: saved.time, createdAt: saved.created_at, kind: saved.kind, isDirect: false, read: false, source: 'Pesan tersimpan' };
      setData((current) => ({ ...current, messages: [message, ...current.messages.filter((item) => item.id !== message.id)], __role: role, audit: addAudit({ ...current, __role: role }, 'Pengumuman dikirim', target === 'all' ? null : target, target === 'all' ? 'Semua keluarga tertaut' : 'Satu profil anak') }));
      setModal(null);
      showToast('Pengumuman terkirim ke ruang pesan keluarga.');
    } catch (cause) {
      showToast(cause instanceof ApiError ? cause.message : 'Pengumuman belum terkirim. Coba lagi.', 'error');
    }
  };

  const sendDirectMessage = async ({ childId, recipientId, text }) => {
    try {
      const response = await apiPost('messages', { child_id: childId, recipient_id: recipientId, text });
      const saved = response.message;
      const message = {
        id: saved.id,
        childId: saved.child_id,
        author: saved.author,
        role: saved.role,
        senderId: saved.sender_id,
        recipientId: saved.recipient_id,
        recipientName: saved.recipient_name,
        recipientRole: saved.recipient_role,
        text: saved.text,
        time: saved.time,
        createdAt: saved.created_at,
        kind: saved.kind,
        isDirect: true,
        relatedActivityId: saved.related_activity_id,
        read: false,
        source: 'Percakapan langsung',
      };
      setData((current) => ({
        ...current,
        messages: [message, ...current.messages.filter((item) => item.id !== message.id)],
        __role: role,
        audit: addAudit({ ...current, __role: role }, 'Pesan langsung dikirim', childId, 'Percakapan terpilih'),
      }));
      showToast(`Pesan terkirim ke ${saved.recipient_name}.`);
      return true;
    } catch (cause) {
      showToast(cause instanceof ApiError ? cause.message : 'Pesan belum terkirim. Coba lagi.', 'error');
      return false;
    }
  };

  const openActivity = (item) => setModal({ type: 'activity-detail', item });
  const onReset = () => {
    if (!window.confirm('Atur ulang tampilan pada akun ini? Catatan yang tersimpan di server uji tidak akan dihapus.')) return;
    setData(copySeed()); setSection('home'); setSelectedId('a'); showToast('Tampilan akun ini diatur ulang. Catatan di server tetap tersimpan.');
  };

  const title = role === 'parent' && section === 'home' ? 'Ringkasan hari ini' : (navItems.flatMap((group) => group.items).find((item) => item.id === section)?.label || TITLES[section] || 'Rumah Kecilku');
  const pendingTotal = data.queue.filter((item) => data.consents[item.childId] !== false && !item.reviewed).length;
  const unsharedCount = data.activities.filter((item) => !item.shared).length;
  const unreadNotifications = (data.notifications || []).filter((item) => !item.readAt).length;
  const latestNotifications = (data.notifications || []).filter((item) => !item.readAt).slice(0, 3);
  const notificationCount = role === 'doctor' ? pendingTotal + unreadNotifications : role === 'caregiver' ? unreadNotifications + unsharedCount : unreadNotifications;

  useEffect(() => {
    if (!allNavIds.includes(section)) setSection('home');
  }, [allNavIds.join('|'), section]);

  const page = (() => {
    switch (section) {
      case 'home':
        if (role === 'parent') return activeChild
          ? <ParentHome data={data} child={activeChild} onGo={go} onOpenMessage={() => go('messages')} onToggleConsent={toggleConsent} />
          : <ParentNoChildPage onGo={go} />;
        if (role === 'doctor') return <DoctorHome data={data} onGo={go} onOpenReview={(item) => setModal({ type: 'review', item })} />;
        if (role === 'admin') return <AdminHome data={data} onGo={go} />;
        return <CaregiverHome data={data} onGo={go} onNewActivity={() => setModal({ type: 'activity' })} onOpenActivity={openActivity} onOpenReview={(item) => setModal({ type: 'review', item })} onToggleTask={updateTask} />;
      case 'activities': return <ActivityPage role={role} data={data} children={visibleChildren} search={search} filter={filter} setFilter={setFilter} onOpenActivity={openActivity} onNewActivity={() => setModal({ type: 'activity' })} />;
      case 'meals': return <MealCatalogPage role={role} data={data} onAddMeal={() => setModal({ type: 'meal' })} />;
      case 'children': return <ChildrenPage role={role} data={data} selectedId={selectedId} setSelectedId={setSelectedId} search={search} onAddChild={() => setModal({ type: 'child' })} onEditChild={(child) => setModal({ type: 'child-edit', child })} onGo={go} onCheckIn={checkInAttendance} onCheckOut={checkOutAttendance} onMarkAttendance={markAttendanceStatus} />;
      case 'development': return <DevelopmentPage role={role} data={data} children={visibleChildren} selectedId={activeChild?.id || 'a'} setSelectedId={setSelectedId} onGo={go} onNewObservation={() => setModal({ type: 'observation' })} onNewQuarterlyReport={() => setModal({ type: 'quarterly-report' })} onPublishQuarterlyReport={publishQuarterlyReport} insightLoadState={activeInsightLoadState} insightLoadError={activeInsightLoadError} onRefreshInsights={refreshInsights} onFeedback={saveStimulationFeedback} onStartActivity={(titleValue) => setModal({ type: 'activity', title: titleValue })} />;
      case 'sensors': return <SensorPage role={role} data={data} />;
      case 'recommendations': return <RecommendationsPage role={role} data={data} children={visibleChildren} selectedId={activeChild?.id || 'a'} setSelectedId={setSelectedId} onGo={go} onStartActivity={(titleValue) => setModal({ type: 'activity', title: titleValue })} onNewObservation={() => setModal({ type: 'observation' })} insightLoadState={insightLoadState} insightLoadError={insightLoadError} insightStatusChildId={insightStatusChildId} onRefreshInsights={refreshInsights} onFeedback={saveStimulationFeedback} />;
      case 'messages': return <MessagesPage role={role} data={data} children={visibleChildren} onAnnounce={() => setModal({ type: 'announcement' })} onReminder={() => setModal({ type: 'reminder' })} onSendDirectMessage={sendDirectMessage} onOpenNotification={openNotification} onMarkNotificationRead={markNotificationRead} onCompleteReminder={completeReminder} onRequestBrowserNotifications={requestBrowserNotifications} notificationPermission={notificationPermission} requestedChildId={messageTarget.childId} requestedContactId={messageTarget.contactId} onTargetConsumed={() => setMessageTarget({ childId: '', contactId: '' })} />;
      case 'reports': return <ReportsPage role={role} data={data} children={visibleChildren} />;
      case 'privacy': return <PrivacyPage role={role} data={data} child={activeChild || data.children[0]} onToggleConsent={toggleConsent} onReset={onReset} />;
      case 'queue': return <QueuePage data={data} search={search} onOpenReview={(item) => setModal({ type: 'review', item })} />;
      case 'kpsp': return <KpspWorkspace data={data} children={visibleChildren} onSave={saveKpsp} />;
      default: return <CaregiverHome data={data} onGo={go} onNewActivity={() => setModal({ type: 'activity' })} onOpenActivity={openActivity} onOpenReview={(item) => setModal({ type: 'review', item })} onToggleTask={updateTask} />;
    }
  })();

  return (
    <div className={`app-shell role-${role}`}>
      {mobileOpen && <button className="mobile-scrim" aria-label="Tutup navigasi" onClick={() => setMobileOpen(false)} />}
      <aside className={`sidebar ${mobileOpen ? 'sidebar-open' : ''}`}>
        <div className="brand-lockup"><div className="brand-seal" aria-hidden="true"><span /><span /><span /></div><div className="brand-copy"><strong>Rumah Kecilku</strong><small>DAY CARE</small></div><button className="icon-button sidebar-close" aria-label="Tutup navigasi" onClick={() => setMobileOpen(false)}><Icon name="close" /></button></div>
        <div className="unit-switcher"><span className="unit-avatar">RK</span><span><small>RUANG KERJA</small><strong>Rumah Kecilku</strong></span></div>
        <nav className="side-nav" aria-label="Navigasi utama">{navItems.map((group) => <div className="nav-group" key={group.group}><div className="nav-group-label">{group.group}</div>{group.items.map((item) => <button key={item.id} className={`nav-item ${section === item.id ? 'nav-active' : ''}`} aria-current={section === item.id ? 'page' : undefined} onClick={() => go(item.id)}><span className="nav-icon"><Icon name={item.icon} size={18} /></span><span>{item.label}</span></button>)}</div>)}</nav>
        <div className="sidebar-bottom">{role !== 'admin' && <><div className="sidebar-help-card"><span className="help-mark"><Icon name="info" size={16} /></span><strong>Data dan privasi</strong><button onClick={() => go('privacy')}>Lihat pengaturan <Icon name="arrow" size={13} /></button></div><button className="reset-demo-button" onClick={onReset}><Icon name="refresh" size={15} />Reset tampilan akun ini</button></>}<div className="sidebar-version">Versi uji <span>v0.1</span></div></div>
      </aside>
      <div className="main-shell">
        <header className="topbar">
          <div className="topbar-left">
            <button className="icon-button mobile-menu" onClick={() => setMobileOpen(true)} aria-label="Buka navigasi"><span className="menu-lines"><i /><i /><i /></span></button>
            <div className="breadcrumbs"><span>Rumah Kecilku</span><i>/</i><strong>{title}</strong></div>
          </div>
          <div className="topbar-right">
            <form className="global-search" onSubmit={(event) => { event.preventDefault(); go(role === 'parent' ? 'activities' : role === 'doctor' ? 'queue' : 'children'); }}>
              <Icon name="search" size={17} /><label className="sr-only" htmlFor="global-search-input">Cari</label>
              <input id="global-search-input" value={search} onChange={(event) => setSearch(event.target.value)} placeholder={role === 'parent' ? 'Cari pembaruan...' : role === 'doctor' ? 'Cari antrean tinjauan...' : role === 'admin' ? 'Cari profil atau ruang...' : 'Cari profil atau catatan...'} /><kbd>↵</kbd>
            </form>
            <div className="topbar-divider" />
            <div className="account-control"><span className="account-avatar" aria-hidden="true">{user?.name?.trim()?.charAt(0)?.toUpperCase() || 'R'}</span><span className="account-copy"><strong>{user?.name || ROLE_LABELS[role]}</strong><small>{ROLE_LABELS[role]} · {user?.email || 'akun'}</small></span><button className="account-logout" type="button" onClick={onLogout}>Keluar</button></div>
            <div className="notification-wrap">
              <button className={`icon-button notification-button ${notificationsOpen ? 'button-open' : ''}`} aria-label={`Pemberitahuan, ${notificationCount} belum dibaca atau perlu diperiksa`} aria-expanded={notificationsOpen} onClick={() => setNotificationsOpen((value) => !value)}><Icon name="bell" size={19} />{notificationCount > 0 && <i />}</button>
              {notificationsOpen && <div className="notification-popover">
                <div className="popover-head"><strong>Pusat pemberitahuan</strong><button onClick={() => setNotificationsOpen(false)} aria-label="Tutup"><Icon name="close" size={15} /></button></div>
                {role === 'doctor' && pendingTotal > 0 && <button className="popover-item" onClick={() => go('queue')}><span className="popover-icon popover-icon-coral"><Icon name="review" size={16} /></span><span><strong>{pendingTotal} pemeriksaan menunggu</strong><small>Buka daftar tinjauan dokter.</small></span></button>}
                {latestNotifications.map((item) => <button className="popover-item" key={item.id} onClick={() => openNotification(item)}><span className="popover-icon popover-icon-sage">{item.category === 'photo' ? '📷' : item.category === 'reminder' ? '⏰' : item.category === 'message' ? '💬' : '🌱'}</span><span><strong>{item.title}</strong><small>{item.body}</small></span></button>)}
                {role === 'caregiver' && unsharedCount > 0 && <button className="popover-item" onClick={() => go('activities')}><span className="popover-icon popover-icon-coral"><Icon name="activity" size={16} /></span><span><strong>{unsharedCount} catatan belum dibagikan</strong><small>Periksa catatan sebelum memilih untuk berbagi.</small></span></button>}
                {notificationCount === 0 && <p className="popover-empty">Belum ada pemberitahuan baru.</p>}
                <button className="popover-footer" onClick={() => { setNotificationsOpen(false); go(role === 'doctor' && unreadNotifications === 0 ? 'queue' : 'messages'); }}>{role === 'doctor' && unreadNotifications === 0 ? 'Buka tinjauan dokter' : 'Buka pesan & pemberitahuan'} <Icon name="arrow" size={14} /></button>
              </div>}
            </div>
          </div>
        </header>
        <main className="page-content" id="main-content">{role === 'parent' && visibleChildren.length === 0 ? <ParentNoChildPage onGo={go} /> : page}</main>
        <footer className="app-footer"><span>Rumah Kecilku Day Care</span><button onClick={() => go('privacy')}>Batasan & privasi <Icon name="arrow" size={13} /></button></footer>
      </div>
      {modal?.type === 'activity' && <ModalActivityForm children={data.children} meals={data.meals} linkedChildIds={data.linkedChildIds || []} initialChildId={role === 'parent' ? activeChild?.id : selectedId} initialTitle={modal.title || ''} onSave={saveActivity} onClose={() => setModal(null)} />}
      {modal?.type === 'meal' && <ModalMealForm onSave={saveMeal} onClose={() => setModal(null)} />}
      {modal?.type === 'reminder' && <ModalReminderForm children={data.children} initialChildId={selectedId} onSave={saveReminder} onClose={() => setModal(null)} />}
      {modal?.type === 'quarterly-report' && <ModalQuarterlyReportForm children={visibleChildren} initialChildId={activeChild?.id || selectedId} onSave={createQuarterlyReport} onClose={() => setModal(null)} />}
      {modal?.type === 'observation' && <ModalObservationForm children={data.children} initialChildId={selectedId} onSave={saveObservation} onClose={() => setModal(null)} />} 
      {modal?.type === 'child' && <ModalChildForm isAdmin={role === 'admin'} onSave={saveChild} onClose={() => setModal(null)} />}
      {modal?.type === 'child-edit' && role === 'admin' && <ModalEditChildForm child={modal.child} onSave={saveChildProfileUpdate} onClose={() => setModal(null)} />}
      {modal?.type === 'announcement' && <ModalAnnouncement children={data.children.filter((child) => (data.linkedChildIds || []).includes(child.id))} onSave={sendAnnouncement} onClose={() => setModal(null)} />}
      {modal?.type === 'review' && <ModalReview item={modal.item} child={data.children.find((entry) => entry.id === modal.item.childId)} onSave={saveReview} onPublish={publishReview} onClose={() => setModal(null)} />}
      {modal?.type === 'activity-detail' && <ModalActivityDetail item={modal.item} child={data.children.find((entry) => entry.id === modal.item.childId) || activeChild} onClose={() => setModal(null)} />}
      <Toast message={toastMessage} type={toastType} onClose={closeToast} />
    </div>
  );
}
