/**
 * 小智吉祥物 · 5 个表情（与 prototypes/01-design-system.html 的新版卡通形象同步）。
 * 小程序不支持内联 SVG DOM，改为 SVG 字符串 -> data URI，用背景图渲染，保真度不变。
 * 每个表情为自包含完整 SVG（不依赖跨文档引用），保证小程序背景渲染兼容。
 */

export type MascotType = 'wave' | 'think' | 'cheer' | 'sweat' | 'grad'

/* ---------- 共用身体部件（与原型 xz-* 定义一致） ---------- */
const BODY = `
<path d="M86 187 L102 188 L102 201 L80 201 Q77 194 86 187Z" fill="#FFFDFC"/>
<path d="M118 188 L134 187 Q143 194 140 201 H118Z" fill="#FFFDFC"/>
<path d="M82 198 H101 M120 198 H138" fill="none" stroke="#E7D8C9" stroke-width="2.5"/>
<path d="M90 145 Q110 138 130 145 Q145 151 147 173 L137 186 H83 L73 173 Q76 151 90 145Z" fill="#FFFDFC"/>
<path d="M85 153 L95 152 V168 H125 V152 L135 153 L139 184 Q140 194 128 194 H92 Q80 194 81 184Z" fill="#FF7548"/>
<path d="M86 184 Q109 190 135 184" fill="none" stroke="#E65E37" stroke-width="3"/>
<circle cx="91" cy="168" r="2.5" fill="#FFFDFC" stroke="none"/>
<circle cx="129" cy="168" r="2.5" fill="#FFFDFC" stroke="none"/>
<path d="M101 176 Q106 174 110 177 Q114 174 119 176 V184 Q114 182 110 185 Q106 182 101 184Z" fill="#FFFDFC" stroke="none"/>
<path d="M110 177 V182" fill="none" stroke="#FF7548" stroke-width="1.5"/>
`

const HEAD = `
<ellipse cx="53" cy="111" rx="10" ry="12" fill="#FFE9D2"/>
<ellipse cx="167" cy="111" rx="10" ry="12" fill="#FFE9D2"/>
<path d="M50 111 L55 114 M165 114 L170 111" fill="none" stroke="#DEA786" stroke-width="2.5"/>
<path d="M56 88 C56 62 80 51 110 51 C142 51 164 65 164 89 L166 110 C166 138 145 156 110 156 C77 156 54 139 54 112Z" fill="#FFE9D2"/>
<path d="M46 102 C38 82 45 61 61 49 C71 41 83 37 96 38 C96 29 108 25 118 30 L112 38 C137 32 160 42 172 61 C182 77 179 95 165 107 L158 84 C145 87 132 82 122 72 C111 85 96 87 84 80 C78 91 69 96 59 92 L55 108Z" fill="#FF7548"/>
<path d="M62 65 Q72 51 88 49" fill="none" stroke="#FFB18C" stroke-width="6"/>
<path d="M98 48 Q103 44 110 44" fill="none" stroke="#FFB18C" stroke-width="4"/>
<ellipse cx="72" cy="128" rx="10" ry="5.5" fill="#FFAF99" stroke="none"/>
<ellipse cx="148" cy="128" rx="10" ry="5.5" fill="#FFAF99" stroke="none"/>
`

const REST_ARM = `
<path d="M81 150 Q67 156 64 172 Q64 180 71 181 Q76 181 78 175 L89 158Z" fill="#FFE9D2"/>
<path d="M68 173 L72 175" fill="none" stroke="#DEA786" stroke-width="2"/>
`

const HAPPY = `
<path d="M79 112 Q86 102 94 112 M126 112 Q134 102 141 112" fill="none" stroke-width="3.8"/>
<path d="M94 124 Q110 129 126 124 Q124 143 110 143 Q97 142 94 124Z" fill="#684039" stroke-width="3"/>
<path d="M102 137 Q111 131 120 137 Q111 145 102 137Z" fill="#FF929C" stroke="none"/>
`

const CHEER_ARM = `
<path d="M84 159 Q62 159 47 136 L33 119 Q27 111 31 106 Q35 102 40 107 L44 111 L42 103 Q41 98 46 98 Q50 98 51 104 L55 117 Q67 137 87 141Z" fill="#FFE9D2"/>
<path d="M38 117 L43 122" fill="none" stroke="#DEA786" stroke-width="2"/>
`

const spark = (transform: string) =>
  `<path transform="${transform}" d="M0 -11 L3 -3 L11 0 L3 3 L0 11 L-3 3 L-11 0 L-3 -3Z" fill="#F5B841" stroke-width="2.4"/>`

const WRAP = (inner: string) =>
  `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 220 220" fill="none" stroke="#3B302D" stroke-width="3.4" stroke-linecap="round" stroke-linejoin="round">${inner}</svg>`

const wave = WRAP(`
<ellipse cx="110" cy="207" rx="39" ry="5" fill="#F0E9DF" stroke="none"/>
${REST_ARM}
<path d="M137 151 C154 151 166 143 177 132 L172 124 C168 118 169 114 173 114 C176 114 178 118 181 121 L179 108 C178 104 180 101 183 102 C186 102 187 108 189 115 L188 101 C188 96 192 94 195 97 C197 100 196 108 197 114 L198 106 C199 102 203 102 205 105 C207 108 204 118 203 124 C202 132 198 138 191 141 C180 158 162 171 141 170Z" fill="#FFE9D2"/>
<path d="M181 127 Q184 124 188 125" fill="none" stroke="#DEA786" stroke-width="2"/>
${BODY}
<g transform="rotate(-6 110 143)">
${HEAD}
<ellipse cx="87" cy="111" rx="5.4" ry="7.4" fill="#3B302D" stroke="none"/>
<ellipse cx="134" cy="111" rx="5.4" ry="7.4" fill="#3B302D" stroke="none"/>
<circle cx="89" cy="108" r="1.8" fill="#FFFDFC" stroke="none"/>
<circle cx="136" cy="108" r="1.8" fill="#FFFDFC" stroke="none"/>
<path d="M100 129 Q110 133 122 127 Q119 140 110 140 Q103 139 100 129Z" fill="#684039" stroke-width="2.8"/>
<path d="M108 136 Q112 134 116 136" fill="none" stroke="#FF929C" stroke-width="3"/>
</g>
<path d="M182 85 L180 78 M203 88 L209 82" fill="none" stroke="#FF7548" stroke-width="3"/>
`)

const think = WRAP(`
<ellipse cx="110" cy="207" rx="39" ry="5" fill="#F0E9DF" stroke="none"/>
${REST_ARM}
<path d="M138 156 C160 155 178 143 181 115 L182 103 C177 100 174 94 175 87 L171 79 C169 75 171 72 175 73 L182 79 L178 72 C176 68 179 65 183 67 L191 76 C196 76 200 81 200 88 C201 96 197 102 194 107 L193 121 C190 149 174 169 141 174Z" fill="#FFE9D2"/>
${BODY}
<g transform="rotate(7 110 145)">
${HEAD}
<path d="M79 99 Q85 94 92 98 M128 94 Q135 88 142 94" fill="none" stroke-width="2.8"/>
<ellipse cx="91" cy="112" rx="5" ry="6.5" fill="#3B302D" stroke="none"/>
<ellipse cx="139" cy="107" rx="5" ry="6.5" fill="#3B302D" stroke="none"/>
<circle cx="93" cy="110" r="1.6" fill="#FFFDFC" stroke="none"/>
<circle cx="141" cy="105" r="1.6" fill="#FFFDFC" stroke="none"/>
<ellipse cx="116" cy="134" rx="5" ry="6" fill="#684039" stroke-width="2.5"/>
</g>
<path d="M182 103 C177 100 174 94 175 87 L171 79 C169 75 171 72 175 73 L182 79 L178 72 C176 68 179 65 183 67 L191 76 C196 76 200 81 200 88 C201 96 197 102 194 107" fill="#FFE9D2"/>
<path d="M181 83 L185 87 M190 83 Q186 84 187 89 Q188 93 192 91" fill="none" stroke="#DEA786" stroke-width="2"/>
<path d="M194 63 L198 58 M203 71 L209 69" fill="none" stroke="#FF7548" stroke-width="2.5"/>
<path d="M25 61 C23 50 40 48 43 58 C46 67 33 68 34 77" fill="none" stroke="#2B6CB0" stroke-width="4.5"/>
<circle cx="34" cy="87" r="2.8" fill="#2B6CB0" stroke="none"/>
`)

const cheer = WRAP(`
<ellipse cx="110" cy="207" rx="29" ry="4" fill="#F0E9DF" stroke="none"/>
<g transform="translate(0 -7) rotate(-4 110 150)">
${CHEER_ARM}
<g transform="translate(220 0) scale(-1 1)">${CHEER_ARM}</g>
${BODY}
${HEAD}
${HAPPY}
</g>
${spark('translate(28 66) rotate(-12)')}
${spark('translate(190 54) scale(.8)')}
<path d="M28 147 L23 153 M194 143 L200 148" fill="none" stroke="#FF7548" stroke-width="3"/>
`)

const sweat = WRAP(`
<ellipse cx="110" cy="207" rx="39" ry="5" fill="#F0E9DF" stroke="none"/>
${BODY}
<g transform="translate(0 4) rotate(5 110 145)">
${HEAD}
<path d="M78 100 Q86 101 93 96 M127 96 Q134 101 142 100" fill="none" stroke-width="2.6"/>
<path d="M80 110 L91 116 L80 121 M140 110 L129 116 L140 121" fill="none"/>
<path d="M100 138 Q110 129 120 138" fill="none" stroke-width="3"/>
</g>
<path d="M180 75 C177 84 171 90 172 97 C173 105 184 105 186 98 C188 92 184 82 180 75Z" fill="#8BD4E5" stroke-width="2.5"/>
<path d="M177 96 L178 98" fill="none" stroke="#FFFDFC" stroke-width="3"/>
<path d="M81 157 Q68 160 68 169 Q68 179 89 178 L96 181 Q104 182 105 175 Q106 169 99 167 L84 168 L88 162Z" fill="#FFE9D2"/>
<path d="M139 157 Q152 160 152 169 Q152 179 131 178 L124 181 Q116 182 115 175 Q114 169 121 167 L136 168 L132 162Z" fill="#FFE9D2"/>
<path d="M95 170 Q92 173 95 177 M125 170 Q128 173 125 177" fill="none" stroke="#DEA786" stroke-width="2"/>
`)

const grad = WRAP(`
<ellipse cx="110" cy="207" rx="39" ry="5" fill="#F0E9DF" stroke="none"/>
${REST_ARM}
<path d="M137 153 Q150 151 157 169 L147 179 L134 164Z" fill="#FFE9D2"/>
${BODY}
${HEAD}
${HAPPY}
<g transform="rotate(-8 110 46)">
<path d="M77 36 L79 57 Q110 69 141 57 L143 36Z" fill="#45414E"/>
<path d="M54 32 L110 12 L166 32 L110 52Z" fill="#45414E"/>
<path d="M72 32 L110 19 L144 31" fill="none" stroke="#77717F" stroke-width="2.5"/>
<path d="M112 32 L155 39 V65" fill="none" stroke="#F5B841" stroke-width="3"/>
<circle cx="155" cy="66" r="4" fill="#F5B841" stroke-width="2"/>
<path d="M152 71 L150 79 H160 L158 71" fill="#F5B841" stroke-width="2"/>
</g>
<path d="M110 160 L99 154 V168Z M110 160 L121 154 V168Z" fill="#F5B841" stroke-width="2.5"/>
<circle cx="110" cy="160" r="3" fill="#FF7548" stroke-width="2"/>
<g transform="rotate(12 139 176)">
<rect x="121" y="153" width="35" height="43" rx="4" fill="#FFFDFC" stroke-width="2.8"/>
<path d="M132 165 L137 170 L147 160" fill="none" stroke="#28A461" stroke-width="3"/>
<path d="M129 181 H148 M129 187 H142" fill="none" stroke="#D8C7B5" stroke-width="2.5"/>
</g>
<path d="M155 171 Q163 170 164 177 Q164 183 157 184 L152 182 Q148 178 151 174Z" fill="#FFE9D2" stroke-width="2.8"/>
${spark('translate(187 118) scale(.65)')}
`)

const RAW: Record<MascotType, string> = { wave, think, cheer, sweat, grad }

/** 生成可用于 background-image 的 data URI。 */
export function mascotDataUri(type: MascotType): string {
  const svg = RAW[type].replace(/\n/g, '')
  return `data:image/svg+xml,${encodeURIComponent(svg)}`
}
