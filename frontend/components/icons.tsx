import React from 'react';
import type { IconName } from '../lib/types';

const art: Record<IconName, React.ReactNode> = {
  home: <><path d="M3.5 10.4 12 3.7l8.5 6.7"/><path d="M5.4 9.4v10.2h13.2V9.4M9.2 19.6v-6.2h5.6v6.2"/></>,
  activity: <><path d="M4 5.5h16M4 12h11M4 18.5h8"/><circle cx="18" cy="12" r="2.2"/><path d="m17 18 1.1 1.1L20.7 16"/></>,
  child: <><circle cx="12" cy="8" r="3.7"/><path d="M4.5 20c.7-3.5 3.3-5.3 7.5-5.3s6.8 1.8 7.5 5.3"/><path d="M8.7 8.5h.1m7.1 0h.1"/></>,
  growth: <><path d="M19.5 4.5C12 4.7 6 7.2 6 12.4c0 3.2 2.1 5.2 5.2 5.2 5.2 0 7.8-6 8.3-13.1Z"/><path d="M4.2 20c1.5-3.8 4.3-6.5 8.7-8.7"/><path d="M14.5 8.2c1 .7 1.7 1.6 2.1 2.7"/></>,
  clipboard: <><path d="M8 5.5h8.1a2 2 0 0 1 2 2v12H5.9v-12a2 2 0 0 1 2.1-2Z"/><path d="M9 5.6V4.5A1.5 1.5 0 0 1 10.5 3h3A1.5 1.5 0 0 1 15 4.5v1.1M8.5 11h7m-7 3.5h7m-7 3.5h4"/></>,
  review: <><path d="M4 5.5h9M4 10.5h7M4 15.5h5"/><circle cx="16.2" cy="15.4" r="4.1"/><path d="m19.2 18.4 2 2"/><path d="m14.5 15.4 1.2 1.2 2.3-2.6"/></>,
  sensor: <><path d="M12 3.5v9.1"/><circle cx="12" cy="17.4" r="3.3"/><path d="M8.1 12.6a5.4 5.4 0 1 0 7.8 0M5.5 10.4a9 9 0 1 0 13 0"/></>,
  message: <><path d="M4 5.7A2.7 2.7 0 0 1 6.7 3h10.6A2.7 2.7 0 0 1 20 5.7v8.6a2.7 2.7 0 0 1-2.7 2.7h-6l-4.8 3.3v-3.3h-.1A2.7 2.7 0 0 1 4 14.3Z"/><path d="M8 8.5h8m-8 3.5h5"/></>,
  report: <><path d="M5 19.5V11m7 8.5V5m7 14.5v-6"/><path d="M3.5 20.5h17"/><circle cx="5" cy="8.5" r="1.2"/><circle cx="12" cy="3.5" r="1.2"/><circle cx="19" cy="11.5" r="1.2"/></>,
  privacy: <><path d="M12 3 19 6v5.2c0 4.3-2.5 7.8-7 9.8-4.5-2-7-5.5-7-9.8V6Z"/><path d="m8.7 12.1 2.1 2.1 4.5-4.6"/></>,
  spark: <><path d="m12 3.2 1.4 5.4 5.4 1.4-5.4 1.4-1.4 5.4-1.4-5.4-5.4-1.4 5.4-1.4Z"/><path d="m19 16 .7 2.3 2.3.7-2.3.7L19 22l-.7-2.3L16 19l2.3-.7Z"/></>,
  plus: <><path d="M12 5v14M5 12h14"/></>,
  search: <><circle cx="10.8" cy="10.8" r="6.5"/><path d="m16 16 4.3 4.3"/></>,
  bell: <><path d="M18.2 9.7a6.2 6.2 0 0 0-12.4 0c0 7-2.6 7-2.6 8.7h17.6c0-1.7-2.6-1.7-2.6-8.7Z"/><path d="M10 21h4"/></>,
  chevron: <><path d="m8 10 4 4 4-4"/></>,
  arrow: <><path d="M4.5 12h14M12.5 6l6 6-6 6"/></>,
  clock: <><circle cx="12" cy="12" r="8.5"/><path d="M12 7v5.2l3.3 2"/></>,
  check: <><path d="m5 12.5 4.3 4.2L19.5 6.5"/></>,
  close: <><path d="m6 6 12 12M18 6 6 18"/></>,
  download: <><path d="M12 3.8v11.7m-4.5-4.2 4.5 4.5 4.5-4.5"/><path d="M5 18.5v2h14v-2"/></>,
  send: <><path d="m3.5 11.5 17-8-6.2 17-2.1-7-8.7-2Z"/><path d="m12.2 13.5 4.1-4.2"/></>,
  calendar: <><rect x="4" y="5.2" width="16" height="15" rx="2.2"/><path d="M8 3.4v3.4m8-3.4v3.4M4 9h16m-11 4h2m3.5 0h2m-7.5 3.5h2"/></>,
  filter: <><path d="M4 6h16M7 12h10m-7 6h4"/><circle cx="8" cy="6" r="1.6"/><circle cx="15" cy="12" r="1.6"/></>,
  leaf: <><path d="M19.7 4.6C12.4 4.9 6 7.1 6 12.6c0 3.1 2.2 5 5.1 5 5.3 0 8-5.8 8.6-13Z"/><path d="M4.3 20c1.2-3.7 4.2-6.5 8.5-8.5"/></>,
  sun: <><circle cx="12" cy="12" r="4"/><path d="M12 2.7v2m0 14.6v2m9.3-9.3h-2m-14.6 0h-2m16.9-6.6-1.4 1.4M5.8 18.2l-1.4 1.4m15.2 0-1.4-1.4M5.8 5.8 4.4 4.4"/></>,
  drop: <><path d="M12 3.4c-2.7 3.7-6.5 7.1-6.5 11.2a6.5 6.5 0 0 0 13 0C18.5 10.5 14.7 7.1 12 3.4Z"/><path d="M9 15.6a3.2 3.2 0 0 0 3.2 2.5"/></>,
  book: <><path d="M4 5.5a2 2 0 0 1 2-2h5.8v16H6a2 2 0 0 0-2 2Zm16 0a2 2 0 0 0-2-2h-5.8v16H18a2 2 0 0 1 2 2Z"/><path d="M7 7h2m6 0h2"/></>,
  play: <><path d="m8.2 5.5 10 6.5-10 6.5Z"/></>,
  refresh: <><path d="M19.5 9A7.8 7.8 0 0 0 5.6 6.3L4 8"/><path d="M4 4.5V8h3.5M4.5 15a7.8 7.8 0 0 0 13.9 2.7L20 16"/><path d="M20 19.5V16h-3.5"/></>,
  info: <><circle cx="12" cy="12" r="8.7"/><path d="M12 11v5m0-8h.01"/></>,
};

interface IconProps {
  name: IconName;
  size?: number;
  className?: string;
}

export function Icon({ name, size = 19, className = '' }: IconProps): React.JSX.Element {
  return (
    <svg className={className} width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true" focusable="false">
      {art[name] || art.info}
    </svg>
  );
}
