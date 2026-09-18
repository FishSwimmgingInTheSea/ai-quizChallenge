/**
 * 小智吉祥物 · 5 个表情（1:1 取自 prototypes 的 SVG symbol）。
 * 小程序不支持内联 SVG DOM，改为 SVG 字符串 -> data URI，用背景图渲染，保真度不变。
 */

export type MascotType = 'wave' | 'think' | 'cheer' | 'sweat' | 'grad'

const WRAP = (inner: string) =>
  `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 180 195">${inner}</svg>`

const wave = WRAP(`
<path d="M26,195 C26,160 54,148 90,148 C126,148 154,160 154,195 Z" fill="#FFFFFF" stroke="#2E2A26" stroke-width="3"/>
<path d="M67,152 L63,193" stroke="#FF6B35" stroke-width="9" stroke-linecap="round"/>
<path d="M113,152 L117,193" stroke="#FF6B35" stroke-width="9" stroke-linecap="round"/>
<path d="M150,168 Q174,134 160,66" stroke="#2E2A26" stroke-width="15" fill="none" stroke-linecap="round"/>
<path d="M150,168 Q174,134 160,66" stroke="#FFE9D2" stroke-width="9" fill="none" stroke-linecap="round"/>
<circle cx="37" cy="102" r="9" fill="#FFE9D2" stroke="#2E2A26" stroke-width="3"/>
<circle cx="143" cy="102" r="9" fill="#FFE9D2" stroke="#2E2A26" stroke-width="3"/>
<circle cx="90" cy="98" r="52" fill="#FFE9D2" stroke="#2E2A26" stroke-width="3"/>
<path d="M37,90 Q52,68 66,82 Q78,62 90,80 Q102,62 114,82 Q128,68 143,90 C147,30 119,10 90,10 C61,10 33,30 37,90 Z" fill="#FF6B35" stroke="#2E2A26" stroke-width="3" stroke-linejoin="round"/>
<ellipse cx="60" cy="114" rx="8" ry="5" fill="#FFB199"/><ellipse cx="120" cy="114" rx="8" ry="5" fill="#FFB199"/>
<circle cx="71" cy="100" r="5" fill="#2E2A26"/><circle cx="109" cy="100" r="5" fill="#2E2A26"/>
<circle cx="73" cy="98" r="1.7" fill="#FFFFFF"/><circle cx="111" cy="98" r="1.7" fill="#FFFFFF"/>
<path d="M80,121 Q90,129 100,121" stroke="#2E2A26" stroke-width="3" fill="none" stroke-linecap="round"/>
<circle cx="160" cy="66" r="12" fill="#FFE9D2" stroke="#2E2A26" stroke-width="3"/>
<path d="M170,48 L175,40 M172,60 L179,56" stroke="#2E2A26" stroke-width="2.5" stroke-linecap="round"/>
`)

const think = WRAP(`
<path d="M26,195 C26,160 54,148 90,148 C126,148 154,160 154,195 Z" fill="#FFFFFF" stroke="#2E2A26" stroke-width="3"/>
<path d="M67,152 L63,193" stroke="#FF6B35" stroke-width="9" stroke-linecap="round"/>
<path d="M113,152 L117,193" stroke="#FF6B35" stroke-width="9" stroke-linecap="round"/>
<path d="M150,168 Q178,126 126,30" stroke="#2E2A26" stroke-width="14" fill="none" stroke-linecap="round"/>
<path d="M150,168 Q178,126 126,30" stroke="#FFE9D2" stroke-width="8" fill="none" stroke-linecap="round"/>
<circle cx="37" cy="102" r="9" fill="#FFE9D2" stroke="#2E2A26" stroke-width="3"/>
<circle cx="143" cy="102" r="9" fill="#FFE9D2" stroke="#2E2A26" stroke-width="3"/>
<circle cx="90" cy="98" r="52" fill="#FFE9D2" stroke="#2E2A26" stroke-width="3"/>
<path d="M37,90 Q52,68 66,82 Q78,62 90,80 Q102,62 114,82 Q128,68 143,90 C147,30 119,10 90,10 C61,10 33,30 37,90 Z" fill="#FF6B35" stroke="#2E2A26" stroke-width="3" stroke-linejoin="round"/>
<ellipse cx="60" cy="114" rx="8" ry="5" fill="#FFB199"/><ellipse cx="120" cy="114" rx="8" ry="5" fill="#FFB199"/>
<circle cx="75" cy="96" r="5" fill="#2E2A26"/><circle cx="113" cy="96" r="5" fill="#2E2A26"/>
<ellipse cx="90" cy="122" rx="6" ry="7" fill="none" stroke="#2E2A26" stroke-width="3"/>
<circle cx="126" cy="30" r="11" fill="#FFE9D2" stroke="#2E2A26" stroke-width="3"/>
<path d="M28,46 L20,38 M36,32 L32,22" stroke="#2E2A26" stroke-width="2.5" stroke-linecap="round"/>
<path d="M30,58 Q42,58 42,70 Q42,80 32,82 L32,90" stroke="#2B6CB0" stroke-width="4" fill="none" stroke-linecap="round"/>
<circle cx="32" cy="98" r="3.5" fill="#2B6CB0"/>
`)

const cheer = WRAP(`
<path d="M26,195 C26,160 54,148 90,148 C126,148 154,160 154,195 Z" fill="#FFFFFF" stroke="#2E2A26" stroke-width="3"/>
<path d="M67,152 L63,193" stroke="#FF6B35" stroke-width="9" stroke-linecap="round"/>
<path d="M113,152 L117,193" stroke="#FF6B35" stroke-width="9" stroke-linecap="round"/>
<path d="M30,168 Q6,138 16,52" stroke="#2E2A26" stroke-width="15" fill="none" stroke-linecap="round"/>
<path d="M30,168 Q6,138 16,52" stroke="#FFE9D2" stroke-width="9" fill="none" stroke-linecap="round"/>
<path d="M150,168 Q174,138 164,52" stroke="#2E2A26" stroke-width="15" fill="none" stroke-linecap="round"/>
<path d="M150,168 Q174,138 164,52" stroke="#FFE9D2" stroke-width="9" fill="none" stroke-linecap="round"/>
<circle cx="37" cy="102" r="9" fill="#FFE9D2" stroke="#2E2A26" stroke-width="3"/>
<circle cx="143" cy="102" r="9" fill="#FFE9D2" stroke="#2E2A26" stroke-width="3"/>
<circle cx="90" cy="98" r="52" fill="#FFE9D2" stroke="#2E2A26" stroke-width="3"/>
<path d="M37,90 Q52,68 66,82 Q78,62 90,80 Q102,62 114,82 Q128,68 143,90 C147,30 119,10 90,10 C61,10 33,30 37,90 Z" fill="#FF6B35" stroke="#2E2A26" stroke-width="3" stroke-linejoin="round"/>
<ellipse cx="60" cy="114" rx="8" ry="5" fill="#FFB199"/><ellipse cx="120" cy="114" rx="8" ry="5" fill="#FFB199"/>
<path d="M63,100 Q71,92 79,100" stroke="#2E2A26" stroke-width="3.5" fill="none" stroke-linecap="round"/>
<path d="M101,100 Q109,92 117,100" stroke="#2E2A26" stroke-width="3.5" fill="none" stroke-linecap="round"/>
<path d="M75,118 Q90,140 105,118 Z" fill="#8C4A52" stroke="#2E2A26" stroke-width="3" stroke-linejoin="round"/>
<path d="M81,129 Q90,136 99,129 L99,126 Q90,123 81,126 Z" fill="#FF8FA3"/>
<circle cx="16" cy="52" r="11" fill="#FFE9D2" stroke="#2E2A26" stroke-width="3"/>
<circle cx="164" cy="52" r="11" fill="#FFE9D2" stroke="#2E2A26" stroke-width="3"/>
<path d="M0,-9 L2.5,-3 L9,-2.5 L4,2 L5.5,9 L0,5.5 L-5.5,9 L-4,2 L-9,-2.5 L-2.5,-3 Z" fill="#FFD23F" stroke="#2E2A26" stroke-width="2" transform="translate(12,28) rotate(-16)"/>
<path d="M0,-9 L2.5,-3 L9,-2.5 L4,2 L5.5,9 L0,5.5 L-5.5,9 L-4,2 L-9,-2.5 L-2.5,-3 Z" fill="#FFD23F" stroke="#2E2A26" stroke-width="2" transform="translate(168,28) rotate(16)"/>
`)

const sweat = WRAP(`
<path d="M26,195 C26,160 54,148 90,148 C126,148 154,160 154,195 Z" fill="#FFFFFF" stroke="#2E2A26" stroke-width="3"/>
<path d="M67,152 L63,193" stroke="#FF6B35" stroke-width="9" stroke-linecap="round"/>
<path d="M113,152 L117,193" stroke="#FF6B35" stroke-width="9" stroke-linecap="round"/>
<circle cx="37" cy="102" r="9" fill="#FFE9D2" stroke="#2E2A26" stroke-width="3"/>
<circle cx="143" cy="102" r="9" fill="#FFE9D2" stroke="#2E2A26" stroke-width="3"/>
<circle cx="90" cy="98" r="52" fill="#FFE9D2" stroke="#2E2A26" stroke-width="3"/>
<path d="M37,90 Q52,68 66,82 Q78,62 90,80 Q102,62 114,82 Q128,68 143,90 C147,30 119,10 90,10 C61,10 33,30 37,90 Z" fill="#FF6B35" stroke="#2E2A26" stroke-width="3" stroke-linejoin="round"/>
<ellipse cx="60" cy="114" rx="8" ry="5" fill="#FFB199"/><ellipse cx="120" cy="114" rx="8" ry="5" fill="#FFB199"/>
<path d="M63,96 L75,102 L63,108" stroke="#2E2A26" stroke-width="3" fill="none" stroke-linejoin="round" stroke-linecap="round"/>
<path d="M117,96 L105,102 L117,108" stroke="#2E2A26" stroke-width="3" fill="none" stroke-linejoin="round" stroke-linecap="round"/>
<path d="M80,126 Q90,118 100,126" stroke="#2E2A26" stroke-width="3" fill="none" stroke-linecap="round"/>
<path d="M152,32 Q161,49 152,57 Q143,49 152,32 Z" fill="#7EC8E3" stroke="#2E2A26" stroke-width="2.5"/>
<path d="M50,84 L58,90 M122,84 L114,90" stroke="#2E2A26" stroke-width="2" opacity=".45" stroke-linecap="round"/>
`)

const grad = WRAP(`
<path d="M26,195 C26,160 54,148 90,148 C126,148 154,160 154,195 Z" fill="#FFFFFF" stroke="#2E2A26" stroke-width="3"/>
<path d="M67,152 L63,193" stroke="#FF6B35" stroke-width="9" stroke-linecap="round"/>
<path d="M113,152 L117,193" stroke="#FF6B35" stroke-width="9" stroke-linecap="round"/>
<circle cx="37" cy="102" r="9" fill="#FFE9D2" stroke="#2E2A26" stroke-width="3"/>
<circle cx="143" cy="102" r="9" fill="#FFE9D2" stroke="#2E2A26" stroke-width="3"/>
<circle cx="90" cy="98" r="52" fill="#FFE9D2" stroke="#2E2A26" stroke-width="3"/>
<path d="M37,90 Q52,68 66,82 Q78,62 90,80 Q102,62 114,82 Q128,68 143,90 C147,30 119,10 90,10 C61,10 33,30 37,90 Z" fill="#FF6B35" stroke="#2E2A26" stroke-width="3" stroke-linejoin="round"/>
<ellipse cx="60" cy="114" rx="8" ry="5" fill="#FFB199"/><ellipse cx="120" cy="114" rx="8" ry="5" fill="#FFB199"/>
<path d="M63,100 Q71,92 79,100" stroke="#2E2A26" stroke-width="3.5" fill="none" stroke-linecap="round"/>
<path d="M101,100 Q109,92 117,100" stroke="#2E2A26" stroke-width="3.5" fill="none" stroke-linecap="round"/>
<path d="M75,118 Q90,140 105,118 Z" fill="#8C4A52" stroke="#2E2A26" stroke-width="3" stroke-linejoin="round"/>
<path d="M81,129 Q90,136 99,129 L99,126 Q90,123 81,126 Z" fill="#FF8FA3"/>
<rect x="60" y="26" width="60" height="12" rx="4" fill="#2E2A26"/>
<path d="M46,26 L90,8 L134,26 L90,40 Z" fill="#2E2A26"/>
<path d="M132,26 L140,42" stroke="#FFD23F" stroke-width="3" stroke-linecap="round"/>
<circle cx="141" cy="45" r="4.5" fill="#FFD23F" stroke="#2E2A26" stroke-width="2"/>
<path d="M90,152 L76,144 L76,162 Z M90,152 L104,144 L104,162 Z" fill="#FF6B35" stroke="#2E2A26" stroke-width="2.5" stroke-linejoin="round"/>
<circle cx="90" cy="153" r="4.5" fill="#FFD23F" stroke="#2E2A26" stroke-width="2"/>
`)

const RAW: Record<MascotType, string> = { wave, think, cheer, sweat, grad }

/** 生成可用于 background-image 的 data URI。 */
export function mascotDataUri(type: MascotType): string {
  const svg = RAW[type].replace(/\n/g, '')
  return `data:image/svg+xml,${encodeURIComponent(svg)}`
}
