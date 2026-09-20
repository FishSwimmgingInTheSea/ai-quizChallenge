/**
 * 线性小图标集 · 24×24（手绘风：圆头描边 + 墨色 #2E2A26 + 语义色）。
 * 与 Mascot 同一套路：小程序不支持内联 SVG DOM，SVG 字符串 -> data URI，用背景图渲染。
 */

export type IconName =
  | 'medal'
  | 'check'
  | 'cross'
  | 'clock'
  | 'star'
  | 'book'
  | 'bulb'
  | 'quote'
  | 'target'
  | 'flag'
  | 'poster'
  | 'posterWhite'
  | 'replay'
  | 'rocketWhite'

const WRAP = (inner: string) =>
  `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24">${inner}</svg>`

const QUOTE_MARK =
  '<path d="M10.8,6.8 C8.3,8.4 6.9,10.6 6.9,13.9 C6.9,16.1 8.2,17.6 9.8,17.6 C11.2,17.6 12.3,16.5 12.3,15.2 C12.3,13.9 11.2,12.9 9.9,12.9 C9.7,12.9 9.5,12.9 9.3,13 C9.5,11.2 10.5,9.6 11.9,8.5 Z" fill="#F5B841" stroke="#8A6D00" stroke-width="1.5" stroke-linejoin="round"/>'

const RAW: Record<IconName, string> = {
  /* 奖章：绶带 + 圆章 + 小星 */
  medal: WRAP(`
<path d="M9.2,13.2 L6.4,21.5 L12,18 L17.6,21.5 L14.8,13.2 Z" fill="#FF6B35" stroke="#2E2A26" stroke-width="1.8" stroke-linejoin="round"/>
<circle cx="12" cy="9" r="6.2" fill="#FFD23F" stroke="#2E2A26" stroke-width="2"/>
<path d="M0,-3.1 L1,-1 L3.2,-0.8 L1.5,0.8 L2,3.1 L0,1.8 L-2,3.1 L-1.5,0.8 L-3.2,-0.8 L-1,-1 Z" fill="#FFF3C4" stroke="#2E2A26" stroke-width="1" transform="translate(12,9)"/>
`),
  check: WRAP(`
<circle cx="12" cy="12" r="9" fill="#E9F7EF" stroke="#28A461" stroke-width="2"/>
<path d="M7.6,12.4 L10.8,15.6 L16.6,8.9" fill="none" stroke="#1B7A43" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round"/>
`),
  cross: WRAP(`
<circle cx="12" cy="12" r="9" fill="#FDF0EE" stroke="#E63946" stroke-width="2"/>
<path d="M9,9 L15,15 M15,9 L9,15" stroke="#C42F3B" stroke-width="2.4" stroke-linecap="round"/>
`),
  clock: WRAP(`
<circle cx="12" cy="12" r="9" fill="#EEF4FA" stroke="#2B6CB0" stroke-width="2"/>
<path d="M12,7.2 L12,12 L15.4,14" fill="none" stroke="#2B6CB0" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"/>
<circle cx="12" cy="12" r="1.1" fill="#2B6CB0"/>
`),
  star: WRAP(`
<path d="M12,3 L14.6,8.8 L20.9,9.5 L16.2,13.9 L17.6,20.1 L12,16.8 L6.4,20.1 L7.8,13.9 L3.1,9.5 L9.4,8.8 Z" fill="#FFD23F" stroke="#2E2A26" stroke-width="1.8" stroke-linejoin="round"/>
`),
  book: WRAP(`
<path d="M12,6.6 C10.2,5 7.2,4.6 4.2,5 L4.2,18.2 C7.2,17.6 10.2,18 12,19.4 C13.8,18 16.8,17.6 19.8,18.2 L19.8,5 C16.8,4.6 13.8,5 12,6.6 Z" fill="#EEF4FA" stroke="#2B6CB0" stroke-width="1.9" stroke-linejoin="round"/>
<path d="M12,6.6 L12,19.4" stroke="#2B6CB0" stroke-width="1.5"/>
<path d="M6.6,8.8 Q8.4,8.4 10,9.2 M6.6,12.2 Q8.4,11.8 10,12.6 M14,9.2 Q15.6,8.4 17.4,8.8" fill="none" stroke="#2B6CB0" stroke-width="1.3" stroke-linecap="round"/>
`),
  bulb: WRAP(`
<path d="M12,3.2 C8.3,3.2 5.6,6 5.6,9.6 C5.6,11.9 6.9,13.4 7.9,14.7 C8.7,15.7 9,16.6 9,17.6 L15,17.6 C15,16.6 15.3,15.7 16.1,14.7 C17.1,13.4 18.4,11.9 18.4,9.6 C18.4,6 15.7,3.2 12,3.2 Z" fill="#FDF6E3" stroke="#8A6D00" stroke-width="1.9" stroke-linejoin="round"/>
<path d="M9.6,20.2 L14.4,20.2" stroke="#8A6D00" stroke-width="2" stroke-linecap="round"/>
<path d="M9.2,9.4 C9.5,8 10.6,7 12,7" fill="none" stroke="#F5B841" stroke-width="1.7" stroke-linecap="round"/>
`),
  quote: WRAP(`${QUOTE_MARK}<g transform="translate(6.8,0)">${QUOTE_MARK}</g>`),
  target: WRAP(`
<circle cx="12" cy="12" r="9" fill="#E9F7EF" stroke="#28A461" stroke-width="2"/>
<circle cx="12" cy="12" r="5.2" fill="#FFFFFF" stroke="#28A461" stroke-width="1.8"/>
<circle cx="12" cy="12" r="1.9" fill="#1B7A43"/>
`),
  flag: WRAP(`
<path d="M6,21.5 L6,3.5" stroke="#2E2A26" stroke-width="2.2" stroke-linecap="round"/>
<path d="M6,4.6 C9,3.1 11.8,6.2 15,5 C16.6,4.4 17.9,4.5 19,5 L19,12.2 C17.9,11.7 16.6,11.6 15,12.2 C11.8,13.4 9,10.3 6,11.8 Z" fill="#FF6B35" stroke="#2E2A26" stroke-width="1.7" stroke-linejoin="round"/>
`),
  poster: WRAP(`
<rect x="4" y="4.5" width="16" height="15" rx="2.5" fill="#FFF2EB" stroke="#EA5A24" stroke-width="1.9"/>
<circle cx="9.2" cy="9.4" r="1.7" fill="#F5B841" stroke="#2E2A26" stroke-width="1.3"/>
<path d="M4.8,16.8 L9.2,12.6 L12.2,15.2 L15.6,11.8 L19.2,15.2" fill="none" stroke="#EA5A24" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>
`),
  posterWhite: WRAP(`
<rect x="4" y="4.5" width="16" height="15" rx="2.5" fill="none" stroke="#FFFFFF" stroke-width="1.9"/>
<circle cx="9.2" cy="9.4" r="1.7" fill="#FFE9D2"/>
<path d="M4.8,16.8 L9.2,12.6 L12.2,15.2 L15.6,11.8 L19.2,15.2" fill="none" stroke="#FFFFFF" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>
`),
  replay: WRAP(`
<path d="M19.2,12 A7.2,7.2 0 1 1 16.4,6.3" fill="none" stroke="#2E2A26" stroke-width="2.1" stroke-linecap="round"/>
<path d="M15.9,2.6 L16.5,7 L20.5,5.7 Z" fill="#2E2A26"/>
`),
  /* 白描火箭：实底主按钮（橙底白字）专用 */
  rocketWhite: WRAP(`
<path d="M12,2.6 C14.5,4.5 15.8,7.3 15.8,10.4 C15.8,12.3 15.3,14.1 14.4,15.7 L9.6,15.7 C8.7,14.1 8.2,12.3 8.2,10.4 C8.2,7.3 9.5,4.5 12,2.6 Z" fill="none" stroke="#FFFFFF" stroke-width="1.9" stroke-linejoin="round"/>
<circle cx="12" cy="9.4" r="2.2" fill="none" stroke="#FFFFFF" stroke-width="1.7"/>
<path d="M8.2,12.2 L5.6,15 L6,17.5 L8.8,15.5 M15.8,12.2 L18.4,15 L18,17.5 L15.2,15.5" fill="none" stroke="#FFFFFF" stroke-width="1.8" stroke-linejoin="round"/>
<path d="M10.3,18.2 L12,21.4 L13.7,18.2" fill="none" stroke="#FFFFFF" stroke-width="1.9" stroke-linecap="round" stroke-linejoin="round"/>
`),
}

/** 生成可用于 background-image 的 data URI。 */
export function iconDataUri(name: IconName): string {
  const svg = RAW[name].replace(/\n/g, '')
  return `data:image/svg+xml,${encodeURIComponent(svg)}`
}
