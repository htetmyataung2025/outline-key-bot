import { readFile, mkdir, writeFile } from 'node:fs/promises'
import { resolve } from 'node:path'

// Turn the actual production Vue bundle into an offline, single-file preview.
// This is not the old HTML prototype; it runs the compiled Vue components.
let html = await readFile('dist/index.html', 'utf8')
html = html.replace(/<script\b[^>]*data-telegram-sdk[^>]*>[\s\S]*?<\/script>\s*/gi, '')
const entry = html.match(/<script\b[^>]*type="module"[^>]*src="([^"]+)"[^>]*><\/script>/) ||
              html.match(/<script\b[^>]*src="((?!https?:\/\/)[^"]+)"[^>]*><\/script>/)
if (!entry) throw new Error('Missing Vite JavaScript entry')
const js = await readFile(resolve('dist', entry[1].replace(/^\.\//, '').replace(/^\//, '')), 'utf8')
if (/\bimport\s*\(/.test(js)) throw new Error('Standalone export requires a single, statically imported entry bundle')
html = html.replace(entry[0], () => `<script type="module">${js.replace(/<\/script/gi, '<\\/script')}</script>`)
for (const link of [...html.matchAll(/<link\b[^>]*rel="stylesheet"[^>]*>/g)]) {
  const href = link[0].match(/href="([^"]+)"/)?.[1]
  if (!href) continue
  const css = await readFile(resolve('dist', href.replace(/^\.\//, '').replace(/^\//, '')), 'utf8')
  html = html.replace(link[0], () => `<style>${css}</style>`)
}
const notices = (await Promise.all(['manrope-OFL.txt', 'notosansmyanmar-OFL.txt'].map(file => readFile(`licenses/${file}`, 'utf8')))).join('\n\n').replaceAll('--', '- -')
html = html.replace('</body>', () => `<!-- Embedded font licenses:\n${notices}\n-->\n</body>`)
await mkdir('artifacts', { recursive: true })
await writeFile('artifacts/tunnel-vue-preview.html', html)
console.log(`Standalone Vue preview: artifacts/tunnel-vue-preview.html (${Math.round(Buffer.byteLength(html) / 1024)} KB)`)
