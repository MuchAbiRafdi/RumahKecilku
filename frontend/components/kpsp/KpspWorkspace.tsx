'use client';

import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { apiGet } from '../../lib/api';
import {
  calculateAgeAt,
  formatAgeDetail,
  KPSP_SCHEDULE_MONTHS,
  recommendedScreeningAge,
  todayIsoDate,
} from '../../lib/kpsp-age';
import { Icon } from '../icons';
import type { ChildProfile, DashboardData, KpspAge, KpspForm, KpspFormItem, KpspScore } from '../../lib/types';
import type { KpspScreeningMode } from '../../lib/kpsp-age';

export type KpspAnswer = 'Ya' | 'Tidak';
type KpspStatus = 'draft' | 'submitted';
interface KpspHistoryItem {
  id: string;
  childId: string;
  actualAgeMonths: number | null;
  screeningAgeMonths: number | null;
  status: KpspStatus;
  answers: Record<string, KpspAnswer>;
  answered: number;
  score: KpspScore;
  reviewed?: boolean;
  published?: boolean;
}
interface SavedKpspAssessment {
  id?: string;
  score?: KpspScore;
  status?: KpspStatus;
}
interface KpspSaveResponse {
  backendConnected?: boolean;
  assessment?: SavedKpspAssessment | null;
}
interface KpspSavePayload {
  childId: string;
  birthDate: string;
  screeningDate: string;
  actualAgeMonths: number | null;
  screeningAgeMonths: number | null;
  screeningMode: KpspScreeningMode;
  answers: Record<string, KpspAnswer>;
  answered: number;
  totalItems: number;
  status: KpspStatus;
  score: KpspScore;
}
interface KpspWorkspaceProps {
  data: DashboardData;
  children: ChildProfile[];
  onSave: (payload: KpspSavePayload) => Promise<KpspSaveResponse>;
}
interface KpspSaveNotice {
  status: KpspStatus;
  backendConnected: boolean;
  assessment: SavedKpspAssessment | null;
}

const questionCountLabel = (form: KpspForm | null): string => `${form?.item_count || form?.items?.length || 0} pertanyaan`;

function localScore(form: KpspForm | null, answers: Record<string, KpspAnswer>, status: KpspStatus): KpspScore {
  const items = form?.items || [];
  const answered = Object.keys(answers).length;
  const complete = items.length > 0 && answered === items.length;
  const yesCount = Object.values(answers).filter((answer) => answer === 'Ya').length;
  let resultCode = null;
  let resultLabel = null;
  const noByDomain = {};
  let uncategorizedNo = 0;

  if (complete && status === 'submitted') {
    if (yesCount >= 9) {
      resultCode = 'S';
      resultLabel = 'Sesuai dengan tahap perkembangannya (S)';
    } else if (yesCount >= 7) {
      resultCode = 'M';
      resultLabel = 'Meragukan (M)';
    } else {
      resultCode = 'P';
      resultLabel = 'Kemungkinan ada penyimpangan (P)';
    }
    items.forEach((item) => {
      if (answers[String(item.number)] !== 'Tidak') return;
      if (!item.domains?.length) {
        uncategorizedNo += 1;
        return;
      }
      item.domains.forEach((domain) => {
        noByDomain[domain] = (noByDomain[domain] || 0) + 1;
      });
    });
  }

  return {
    total_items: items.length,
    answered_count: answered,
    yes_count: complete ? yesCount : null,
    no_count: complete ? items.length - yesCount : null,
    result_code: resultCode,
    result_label: resultLabel,
    no_by_domain: noByDomain,
    uncategorized_no_count: uncategorizedNo,
    is_complete: complete,
  };
}

function formatShortDate(value: string | null | undefined): string {
  if (!value) return '—';
  const [year, month, day] = value.split('-').map(Number);
  if (!year || !month || !day) return value;
  return new Intl.DateTimeFormat('id-ID', { day: 'numeric', month: 'short', year: 'numeric', timeZone: 'UTC' })
    .format(new Date(Date.UTC(year, month - 1, day)));
}

export default function KpspWorkspace({ data, children, onSave }: KpspWorkspaceProps): React.JSX.Element {
  const [childId, setChildId] = useState(children[0]?.id || '');
  const [mode, setMode] = useState<KpspScreeningMode>('routine');
  const [screeningDate, setScreeningDate] = useState(todayIsoDate());
  const [birthDate, setBirthDate] = useState<string | null>(null);
  const [form, setForm] = useState<KpspForm | null>(null);
  const [answers, setAnswers] = useState<Record<string, KpspAnswer>>({});
  const [history, setHistory] = useState<KpspHistoryItem[]>([]);
  const [loadingForm, setLoadingForm] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');
  const [formSource, setFormSource] = useState<'api' | 'local' | ''>('');
  const [saveNotice, setSaveNotice] = useState<KpspSaveNotice | null>(null);
  const [historyNotice, setHistoryNotice] = useState('');
  const [formReloadKey, setFormReloadKey] = useState(0);

  const child = children.find((entry) => entry.id === childId) || children[0];
  const currentBirthDate = birthDate ?? child?.birthDate ?? '';
  const age = useMemo(() => calculateAgeAt(currentBirthDate, screeningDate), [currentBirthDate, screeningDate]);
  const actualAgeMonths = age?.roundedMonths ?? null;
  const recommendedAge = actualAgeMonths === null ? null : recommendedScreeningAge(actualAgeMonths, mode);
  const routineDeferred = mode === 'routine' && actualAgeMonths !== null && !KPSP_SCHEDULE_MONTHS.includes(actualAgeMonths);
  const canScreenNow = recommendedAge !== null && !routineDeferred;

  useEffect(() => {
    if (!child) return;
    setBirthDate(child.birthDate || '');
    setAnswers({});
    setSaveNotice(null);
  }, [child?.id, child?.birthDate]);

  useEffect(() => {
    let active = true;
    setForm(null);
    setError('');
    setFormSource('');
    if (recommendedAge === null || routineDeferred) {
      setLoadingForm(false);
      return () => { active = false; };
    }
    setLoadingForm(true);
    (async () => {
      try {
        const payload = await apiGet<KpspForm>(`kpsp/forms/${recommendedAge}`);
        if (!active) return;
        setForm(payload);
        setFormSource('api');
      } catch (apiError: unknown) {
        try {
          const fallback = await fetch('/kpsp-catalog.json', { cache: 'no-store' });
          if (!fallback.ok) throw new Error('Katalog KPSP lokal tidak dapat dimuat.');
          const catalog = await fallback.json();
          const localForm = catalog.forms.find((entry) => entry.age_months === recommendedAge);
          if (!localForm) throw new Error('Formulir untuk usia ini tidak ditemukan di katalog lokal.');
          if (!active) return;
          setForm(localForm);
          setFormSource('local');
          setHistoryNotice('Formulir cadangan digunakan. Pengiriman jawaban tetap memerlukan sambungan.');
        } catch (fallbackError) {
          if (!active) return;
          setError(fallbackError instanceof Error ? fallbackError.message : apiError instanceof Error ? apiError.message : 'Formulir KPSP tidak dapat dimuat.');
        }
      } finally {
        if (active) setLoadingForm(false);
      }
    })();
    return () => { active = false; };
  }, [recommendedAge, routineDeferred, formReloadKey]);

  const refreshHistory = useCallback(async () => {
    if (!childId) return;
    try {
      const payload = await apiGet<{ assessments?: Array<Record<string, any>> }>(`kpsp/children/${encodeURIComponent(childId)}/assessments`);
      const remote = (payload.assessments || []).map((entry) => ({
        id: entry.id,
        childId: entry.child_id,
        actualAgeMonths: entry.actual_age_months,
        birthDate: entry.birth_date,
        screeningDate: entry.screening_date,
        screeningAgeMonths: entry.screening_age_months,
        screeningMode: entry.screening_mode,
        status: entry.status,
        answers: entry.answers,
        score: entry.score,
        answered: entry.score?.answered_count ?? entry.score?.yes_count ?? Object.keys(entry.answers || {}).length,
        sourceVersion: entry.source_version,
        createdAt: entry.created_at,
        reviewed: entry.reviewed,
        published: entry.published,
      }));
      setHistory(remote);
      setHistoryNotice('Riwayat pemeriksaan diperbarui.');
    } catch {
      setHistory([]);
      setHistoryNotice('Riwayat belum dapat dimuat. Periksa sambungan lalu coba lagi.');
    }
  }, [childId]);

  useEffect(() => {
    void refreshHistory();
    const timer = window.setInterval(refreshHistory, 15000);
    return () => window.clearInterval(timer);
  }, [refreshHistory]);

  const answerCount = Object.keys(answers).length;
  const complete = Boolean(form?.items?.length) && answerCount === form.items.length;
  const setAnswer = (number: number, value: KpspAnswer): void => {
    setAnswers((previous) => ({ ...previous, [String(number)]: value }));
    setSaveNotice(null);
  };

  const saveAssessment = async (status: KpspStatus): Promise<void> => {
    if (!form || !child || !age || !canScreenNow) return;
    if (status === 'submitted' && !complete) {
      setError('Jawab semua pertanyaan sebelum mengirim formulir.');
      return;
    }
    if (answerCount === 0) {
      setError('Pilih setidaknya satu jawaban sebelum menyimpan jawaban sementara.');
      return;
    }
    setSaving(true);
    setError('');
    try {
      const result = await onSave({
        childId: child.id,
        birthDate: currentBirthDate,
        screeningDate,
        actualAgeMonths,
        screeningAgeMonths: recommendedAge,
        screeningMode: mode,
        answers,
        answered: answerCount,
        totalItems: form.items.length,
        status,
        score: localScore(form, answers, status),
      });
      setSaveNotice({ status, backendConnected: Boolean(result?.backendConnected), assessment: result?.assessment || null });
      setAnswers({});
      await refreshHistory();
    } catch (saveError) {
      setError(saveError instanceof Error ? saveError.message : 'Skrining belum dapat disimpan.');
    } finally {
      setSaving(false);
    }
  };

  const availableHistory = history;

  return (
    <div className="kpsp-workspace">
      <header className="kpsp-hero gradient-warm-light">
        <div className="kpsp-hero-copy">
          <span className="kpsp-eyebrow"><Icon name="clipboard" size={15} /> FORMULIR KPSP</span>
          <h1>Pemeriksaan KPSP sesuai usia anak.</h1>
          <p>Pilih profil anak dan tanggal pemeriksaan. Usia membantu menentukan formulir KPSP yang sesuai.</p>
          <div className="kpsp-hero-tags"><span><i />16 kelompok umur</span><span><i />9–10 pertanyaan sesuai formulir</span><span><i />Gambar pendukung formulir</span></div>
        </div>
        <div className="kpsp-hero-stamp"><span>RK</span><small>PEMERIKSAAN<br />KPSP</small></div>
      </header>

      <section className="kpsp-setup panel">
        <div className="kpsp-section-heading"><div><span className="eyebrow">01 · KONTEKS PEMERIKSAAN</span><h2>Hitung usia dan pilih formulir</h2><p>Usia anak dipakai untuk menentukan kelompok formulir berikutnya atau yang lebih muda bila ada keluhan.</p></div><span className="kpsp-step-number">01</span></div>
        <div className="kpsp-setup-grid">
          <label className="kpsp-field"><span>Profil anak contoh</span><select value={child?.id || ''} onChange={(event) => { setChildId(event.target.value); setSaveNotice(null); }} aria-label="Pilih profil anak contoh">{children.map((entry) => <option value={entry.id} key={entry.id}>{entry.name} · {entry.ageMonths} bulan</option>)}</select></label>
          <label className="kpsp-field"><span>Tanggal lahir profil anak contoh</span><input type="date" value={currentBirthDate} onChange={(event) => { setBirthDate(event.target.value); setAnswers({}); setSaveNotice(null); }} /></label>
          <label className="kpsp-field"><span>Tanggal pemeriksaan</span><input type="date" value={screeningDate} onChange={(event) => { setScreeningDate(event.target.value); setAnswers({}); setSaveNotice(null); }} /></label>
          <fieldset className="kpsp-field kpsp-mode-field"><legend>Tujuan pemeriksaan</legend><div className="kpsp-segmented" role="group" aria-label="Tujuan pemeriksaan"><button type="button" className={mode === 'routine' ? 'is-active' : ''} aria-pressed={mode === 'routine'} onClick={() => { setMode('routine'); setAnswers({}); setSaveNotice(null); }}>Rutin</button><button type="button" className={mode === 'concern' ? 'is-active' : ''} aria-pressed={mode === 'concern'} onClick={() => { setMode('concern'); setAnswers({}); setSaveNotice(null); }}>Ada keluhan</button></div></fieldset>
        </div>
        <div className="kpsp-age-summary">
          <span className="kpsp-age-icon"><Icon name="calendar" size={19} /></span>
          <div><small>USIA ANAK</small><strong>{formatAgeDetail(age)}</strong><span>{mode === 'routine' ? (routineDeferred ? `Belum waktu skrining rutin; jadwalkan kembali pada ${recommendedAge} bulan dan jangan isi formulir sekarang.` : 'Usia tepat pada jadwal rutin; formulir dapat digunakan sekarang.') : 'Ada keluhan: pilih usia skrining terdekat yang lebih muda bila usia bukan jadwal.'}</span></div>
          <div className="kpsp-recommendation"><small>FORMULIR YANG DIPILIH</small><strong>{recommendedAge ? `${recommendedAge} bulan` : 'Belum tersedia'}</strong>{recommendedAge && <span>{questionCountLabel(form)}</span>}</div>
        </div>
        {recommendedAge === null && <div className="kpsp-inline-alert" role="status"><Icon name="info" size={17} /><span>{actualAgeMonths === null ? 'Tanggal lahir atau tanggal pemeriksaan tidak valid. Periksa tanggal dan pastikan tanggal lahir tidak berada setelah tanggal pemeriksaan.' : actualAgeMonths > 72 ? 'Jadwal pemeriksaan KPSP berakhir pada usia 72 bulan. Arahkan pertanyaan kepada tenaga kesehatan.' : 'Belum ada usia skrining yang lebih muda untuk keluhan sebelum 3 bulan. Minta arahan tenaga kesehatan.'}</span></div>}
        {routineDeferred && recommendedAge !== null && <div className="kpsp-appointment-panel" role="status"><span><Icon name="calendar" size={19} /></span><div><small>PEMERIKSAAN RUTIN BELUM JATUH TEMPO</small><strong>Jadwalkan kembali saat anak berusia {recommendedAge} bulan.</strong><p>Jadwalkan kembali saat anak mencapai usia pemeriksaan berikutnya. Contoh: usia 7 bulan → kembali pada 9 bulan. Formulir tidak diisi sekarang.</p></div><button type="button" className="btn btn-outline btn-small" onClick={() => { setMode('concern'); setAnswers({}); }}>Ada keluhan? Pilih alur keluhan</button></div>}
        {historyNotice && <div className="kpsp-source-status"><span className={formSource === 'api' ? 'status-dot-live' : 'status-dot-local'} />{historyNotice}</div>}
      </section>

      <section className="kpsp-schedule panel">
        <div className="kpsp-schedule-head"><div><span className="eyebrow">JADWAL PEMERIKSAAN KPSP</span><h2>Kelompok umur pemeriksaan</h2></div><span className="kpsp-schedule-count">16 usia</span></div>
        <div className="kpsp-age-chips" aria-label="Jadwal KPSP dalam bulan">{[3, 6, 9, 12, 15, 18, 21, 24, 30, 36, 42, 48, 54, 60, 66, 72].map((month) => <span className={month === recommendedAge ? `kpsp-age-chip ${routineDeferred ? 'next' : 'current'}` : month === actualAgeMonths ? 'kpsp-age-chip exact' : 'kpsp-age-chip'} key={month}>{month}<small>bln</small></span>)}</div>
        <div className="kpsp-rule-notes"><p><strong>Rutin:</strong> jika belum mencapai usia pemeriksaan, jadwalkan kembali pada kelompok umur berikutnya (contoh: 7 → 9 bulan). Jangan isi formulir lebih awal.</p><p><strong>Ada keluhan:</strong> jika umur bukan usia pemeriksaan, gunakan formulir untuk kelompok umur terdekat yang lebih muda.</p></div>
      </section>

      <section className="kpsp-form-section">
        <div className="kpsp-form-heading"><div><span className="eyebrow">02 · FORMULIR YANG SESUAI</span><h2>{form?.title || (routineDeferred ? `Jadwal berikutnya · ${recommendedAge} bulan` : recommendedAge ? `Kuesioner Praskrining · ${recommendedAge} bulan` : 'Formulir belum dipilih')}</h2><p>{form ? `${questionCountLabel(form)}  · sesuai acuan pemeriksaan · jawaban yang tersedia adalah Ya atau Tidak.` : routineDeferred ? 'Pemeriksaan rutin belum jatuh tempo; formulir tidak dimuat sebelum usia skrining tiba.' : 'Formulir akan tampil setelah usia dan konteks tersedia.'}</p></div>{form && <span className="kpsp-form-counter">{answerCount}/{form.items.length} dijawab</span>}</div>
        {loadingForm && <div className="kpsp-state panel" role="status"><span className="kpsp-spinner" /><div><strong>Memuat formulir KPSP</strong><small>Menyiapkan pertanyaan dan gambar pendukung.</small></div></div>}
        {error && !form && <div className="kpsp-error panel" role="alert"><Icon name="info" size={18} /><div><strong>Formulir belum dapat dimuat</strong><p>{error}</p><button type="button" className="kpsp-text-button" onClick={() => setFormReloadKey((value) => value + 1)}>Coba muat ulang</button></div></div>}
        {!loadingForm && canScreenNow && form && <>
          {formSource === 'local' && <div className="kpsp-inline-alert kpsp-local-alert"><Icon name="info" size={17} /><span>Formulir cadangan sedang digunakan. Jawaban hanya dapat disimpan saat sambungan tersedia.</span></div>}
          <div className="kpsp-question-list">
            {form.items.map((item) => (
              <article className="kpsp-question-card" key={item.number}>
                <div className="kpsp-question-number">{String(item.number).padStart(2, '0')}</div>
                <div className="kpsp-question-body">
                  <div className="kpsp-question-meta"><span>PERTANYAAN {item.number}</span><div className="kpsp-domain-list">{item.domains?.length ? item.domains.map((domain) => <span key={domain}>{domain}</span>) : <span className="kpsp-domain-missing">Kategori tidak tercantum pada formulir</span>}</div></div>
                  <p className="kpsp-question-text">{item.question}</p>
                  {item.stimulus && <figure className="kpsp-stimulus"><img src={item.stimulus.url} alt={item.stimulus.alt} loading="lazy" /><figcaption>{item.stimulus.alt} <span>· gambar dari formulir</span></figcaption></figure>}
                  {item.examiner_note && <aside className="kpsp-examiner-note"><strong><Icon name="info" size={14} /> Khusus pemeriksa — jangan dibacakan</strong><span>{item.examiner_note.replace('Panduan pemeriksa — ', '')}</span></aside>}
                  <fieldset className="kpsp-answer-group">
                    <legend className="sr-only">Jawaban untuk pertanyaan {item.number}</legend>
                    {(['Ya', 'Tidak'] as const).map((answer) => <label className={`kpsp-answer-option ${answers[String(item.number)] === answer ? `selected ${answer === 'Ya' ? 'answer-yes' : 'answer-no'}` : ''}`} key={answer}><input type="radio" name={`kpsp-${item.number}`} value={answer} checked={answers[String(item.number)] === answer} onChange={() => setAnswer(item.number, answer)} /><span className="kpsp-answer-indicator">{answers[String(item.number)] === answer && <i />}</span><span>{answer}</span></label>)}
                  </fieldset>
                </div>
              </article>
            ))}
          </div>
          <div className="kpsp-submit-panel panel">
            <div><span className="eyebrow">03 · SIMPAN & TINJAU</span><h3>Simpan jawaban untuk ditinjau</h3><p>Hasil skrining tidak otomatis diterbitkan kepada keluarga. Dokter perlu meninjau ringkasan sebelum dapat dibagikan.</p>{error && <div className="kpsp-save-error" role="alert">{error}</div>}{saveNotice && <div className={`kpsp-save-success ${saveNotice.backendConnected ? '' : 'local-only'}`} role="status"><Icon name="check" size={15} /><span>{saveNotice.status === 'submitted' ? 'Respons dikirim untuk ditinjau dokter.' : 'Jawaban sementara tersimpan.'}</span></div>}</div>
            <div className="kpsp-submit-actions"><button type="button" className="btn btn-outline" onClick={() => saveAssessment('draft')} disabled={saving || answerCount === 0}><Icon name="clipboard" size={17} /><span>{saving ? 'Menyimpan…' : 'Simpan jawaban sementara'}</span></button><button type="button" className="btn btn-primary" onClick={() => saveAssessment('submitted')} disabled={saving || !complete}><Icon name="check" size={17} /><span>{saving ? 'Mengirim…' : 'Kirim untuk tinjauan dokter'}</span></button></div>
          </div>
        </>}
      </section>

      <section className="kpsp-history panel">
        <div className="kpsp-schedule-head"><div><span className="eyebrow">RIWAYAT & JEJAK VERSI</span><h2>Riwayat skrining profil</h2></div><button className="kpsp-refresh-button" type="button" onClick={refreshHistory}><Icon name="refresh" size={15} /> Segarkan</button></div>
        {availableHistory.length ? <div className="kpsp-history-list">{availableHistory.map((entry) => {
          const score = entry.score;
          return <article className="kpsp-history-row" key={entry.id}><span className={`kpsp-history-icon ${entry.status === 'submitted' ? 'complete' : ''}`}><Icon name={entry.status === 'submitted' ? 'check' : 'clipboard'} size={16} /></span><div className="kpsp-history-main"><strong>KPSP usia {entry.screeningAgeMonths} bulan · {entry.status === 'submitted' ? 'menunggu tinjauan' : 'jawaban tersimpan'}</strong><small>Umur anak {entry.actualAgeMonths} bulan · {entry.answered} pertanyaan dijawab</small></div><div className="kpsp-history-result">{score.result_code ? <><strong>{score.result_code}</strong><small>{score.result_label}</small></> : <span>Belum dinilai</span>}</div></article>;
        })}</div> : <div className="kpsp-empty-history"><span><Icon name="clipboard" size={19} /></span><div><strong>Belum ada riwayat skrining</strong><small>Jawaban yang disimpan akan tercatat di sini untuk setiap profil.</small></div></div>}
      </section>

      {saveNotice?.assessment?.score?.result_code && <section className="kpsp-latest-result panel"><div className="kpsp-latest-result-icon">{saveNotice.assessment.score.result_code}</div><div><span className="eyebrow">HASIL SKRINING · KHUSUS TINJAUAN DOKTER</span><h3>{saveNotice.assessment.score.result_label}</h3><p>{saveNotice.assessment.score.yes_count}/{saveNotice.assessment.score.total_items} jawaban Ya. Ini hasil skrining, bukan diagnosis; perlu dilihat bersama konteks dan ditinjau dokter sebelum dibagikan.</p></div></section>}

      <footer className="kpsp-disclaimer"><Icon name="privacy" size={17} /><span>Ikuti petunjuk pada formulir KPSP dan pastikan pemeriksa memahami setiap pertanyaan. KPSP adalah skrining, bukan diagnosis. Hasil tidak dibagikan kepada keluarga sebelum ditinjau dan diterbitkan dokter.</span></footer>
    </div>
  );
}
