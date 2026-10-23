export type Role = 'parent' | 'caregiver' | 'doctor' | 'admin';

export type IconName =
  | 'home' | 'activity' | 'child' | 'growth' | 'clipboard' | 'review' | 'sensor'
  | 'message' | 'report' | 'privacy' | 'spark' | 'plus' | 'search' | 'bell'
  | 'chevron' | 'arrow' | 'clock' | 'check' | 'close' | 'download' | 'send'
  | 'calendar' | 'filter' | 'leaf' | 'sun' | 'drop' | 'book' | 'play'
  | 'refresh' | 'info';

export interface AuthUser {
  id: string;
  name: string;
  email: string;
  role: Role;
  child_ids?: string[];
}

export interface ChildProfile {
  id: string;
  name: string;
  ageMonths: number;
  birthDate: string;
  room: string;
  attendance: string;
  checkIn: string;
  checkOut?: string;
  pickupPersonName?: string;
  note: string;
  status?: 'active' | 'inactive';
}

/** Flexible records are used only at the API/data boundary; persisted structures are typed below. */
export type DashboardRecord = Record<string, any>;

export interface DashboardData {
  __role?: Role;
  linkedChildIds: string[];
  children: ChildProfile[];
  activities: DashboardRecord[];
  messages: DashboardRecord[];
  notifications: DashboardRecord[];
  queue: DashboardRecord[];
  assessments: DashboardRecord[];
  observations: DashboardRecord[];
  recommendations: DashboardRecord[];
  meals: DashboardRecord[];
  developmentReports: DashboardRecord[];
  insights: DashboardRecord[];
  insightMeta: DashboardRecord | null;
  modelStatus: DashboardRecord | null;
  sensor: {
    connected: boolean;
    temperature: number | null;
    humidity: number | null;
    updatedAt: string | null;
    readings: DashboardRecord[];
  };
  consents: Record<string, boolean>;
  tasks: DashboardRecord[];
  audit: DashboardRecord[];
}

export interface KpspAge {
  completedMonths: number;
  remainderDays: number;
  roundedMonths: number;
}

export interface KpspFormItem {
  number: number;
  question: string;
  text?: string;
  prompt?: string;
  image?: string;
  stimulus?: { url: string; alt: string } | null;
  examiner_note?: string;
  domains?: string[];
  [key: string]: any;
}

export interface KpspForm {
  age_months: number;
  title?: string;
  item_count?: number;
  items: KpspFormItem[];
  [key: string]: any;
}

export interface KpspScore {
  total_items: number;
  answered_count: number;
  yes_count: number | null;
  no_count: number | null;
  result_code: string | null;
  result_label: string | null;
  no_by_domain: Record<string, number>;
  uncategorized_no_count: number;
  is_complete: boolean;
  [key: string]: any;
}
