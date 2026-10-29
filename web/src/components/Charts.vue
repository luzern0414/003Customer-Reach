<script setup lang="ts">
// 三种图：trend（多系列平滑折线 + 十字线）、donut（环图）、bars（横向条形）。悬浮即出自定义提示。
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'

interface Series { name: string; color: string; values: number[] }
const props = defineProps<{
  type: 'trend' | 'donut' | 'bars'
  labels: string[]
  series?: Series[]
  values?: number[]
  colors?: string[]
  unit?: string
  height?: number
}>()

const root = ref<HTMLElement | null>(null)
const width = ref(640)
let observer: ResizeObserver | null = null
onMounted(() => {
  observer = new ResizeObserver(([entry]) => { width.value = Math.max(280, Math.round(entry.contentRect.width)) })
  if (root.value) observer.observe(root.value)
})
onBeforeUnmount(() => observer?.disconnect())
const PAD = { l: 36, r: 12, t: 12, b: 28 }
const H = computed(() => props.height || 220)
const W = computed(() => width.value)
const hover = ref<number | null>(null)
const pos = ref({ x: 0, y: 0 })

const max = computed(() => Math.max(1, ...(props.series || []).flatMap((s) => s.values)))
const x = (i: number) => PAD.l + (props.labels.length <= 1 ? 0 : (i * (W.value - PAD.l - PAD.r)) / (props.labels.length - 1))
const y = (v: number) => H.value - PAD.b - (v / max.value) * (H.value - PAD.t - PAD.b)
function smooth(values: number[]): string {
  const pts = values.map((v, i) => [x(i), y(v)])
  if (pts.length < 2) return pts.length ? `M${pts[0][0]} ${pts[0][1]}h1` : ''
  let d = `M${pts[0][0]} ${pts[0][1]}`
  for (let i = 1; i < pts.length; i++) {
    const [x0, y0] = pts[i - 1], [x1, y1] = pts[i], cx = (x0 + x1) / 2
    d += ` C${cx} ${y0} ${cx} ${y1} ${x1} ${y1}`
  }
  return d
}
const ticks = computed(() => [0, 0.5, 1].map((r) => Math.round(max.value * r)))
const xTicks = computed(() => {
  const n = props.labels.length, step = Math.max(1, Math.ceil(n / Math.max(3, Math.floor(W.value / 110))))
  return props.labels.map((l, i) => ({ l: l.slice(5), i })).filter(({ i }) => i % step === 0 || i === n - 1)
})
function onMove(event: MouseEvent) {
  const svg = event.currentTarget as SVGSVGElement
  const box = svg.getBoundingClientRect()
  const px = ((event.clientX - box.left) / box.width) * W.value
  const n = props.labels.length
  if (!n) return
  hover.value = Math.min(n - 1, Math.max(0, Math.round(((px - PAD.l) / (W.value - PAD.l - PAD.r)) * (n - 1))))
  pos.value = { x: event.clientX - box.left, y: event.clientY - box.top }
}

const total = computed(() => (props.values || []).reduce((a, b) => a + b, 0))
const arcs = computed(() => {
  let angle = -Math.PI / 2
  return (props.values || []).map((v, i) => {
    const sweep = total.value ? (v / total.value) * Math.PI * 2 : 0
    const a0 = angle, a1 = angle + Math.max(sweep - 0.02, 0.001)
    angle += sweep
    const r = 70, c = 90
    const large = a1 - a0 > Math.PI ? 1 : 0
    return { i, d: `M${c + r * Math.cos(a0)} ${c + r * Math.sin(a0)} A${r} ${r} 0 ${large} 1 ${c + r * Math.cos(a1)} ${c + r * Math.sin(a1)}`, color: props.colors?.[i] || '#d4d4d8' }
  })
})
const barMax = computed(() => Math.max(1, ...(props.values || [])))
const pct = (v: number) => (total.value ? Math.round((v / total.value) * 100) : 0)
</script>

<template>
  <div ref="root" class="chart" @mouseleave="hover = null">
    <template v-if="type === 'trend'">
      <svg :viewBox="`0 0 ${W} ${H}`" :width="W" :height="H" class="svg" @mousemove="onMove" role="img" aria-label="趋势图">
        <g v-for="t in ticks" :key="t">
          <line :x1="PAD.l" :x2="W - PAD.r" :y1="y(t)" :y2="y(t)" class="grid" />
          <text :x="PAD.l - 6" :y="y(t) + 4" text-anchor="end" class="axis-label">{{ t }}</text>
        </g>
        <text v-for="t in xTicks" :key="t.i" :x="x(t.i)" :y="H - 8" :text-anchor="t.i === labels.length - 1 ? 'end' : t.i === 0 ? 'start' : 'middle'" class="axis-label">{{ t.l }}</text>
        <line v-if="hover !== null" :x1="x(hover)" :x2="x(hover)" :y1="PAD.t" :y2="H - PAD.b" class="cross" />
        <path v-for="s in series" :key="s.name" :d="smooth(s.values)" fill="none" :stroke="s.color" stroke-width="2" />
        <template v-if="labels.length === 1">
          <circle v-for="s in series" :key="s.name" :cx="x(0)" :cy="y(s.values[0] || 0)" r="4" :fill="s.color" />
        </template>
        <template v-if="hover !== null">
          <circle v-for="s in series" :key="s.name" :cx="x(hover)" :cy="y(s.values[hover] || 0)" r="4" fill="#fff" :stroke="s.color" stroke-width="2" />
        </template>
      </svg>
      <div v-if="hover !== null" class="tip" :style="{ left: Math.min(pos.x + 12, 9999) + 'px', top: pos.y + 'px' }">
        <div class="tip-title">{{ labels[hover] }}</div>
        <div v-for="s in series" :key="s.name" class="tip-row"><i :style="{ background: s.color }" />{{ s.name }}<b>{{ s.values[hover] || 0 }} {{ unit }}</b></div>
      </div>
      <div class="legend"><span v-for="s in series" :key="s.name"><i :style="{ background: s.color }" />{{ s.name }}</span></div>
    </template>

    <div v-else-if="type === 'donut'" class="donut-wrap">
      <div class="donut">
        <svg viewBox="0 0 180 180" class="donut-svg" role="img" aria-label="占比图">
          <path v-for="a in arcs" :key="a.i" :d="a.d" fill="none" :stroke="a.color" :stroke-width="hover === a.i ? 26 : 22"
                @mouseenter="hover = a.i" @mousemove="pos = { x: $event.offsetX, y: $event.offsetY }" />
          <text x="90" y="86" text-anchor="middle" class="donut-num">{{ total }}</text>
          <text x="90" y="106" text-anchor="middle" class="axis-label">{{ unit }}</text>
        </svg>
        <div v-if="hover !== null" class="tip" :style="{ left: pos.x + 12 + 'px', top: pos.y + 'px' }">
          <div class="tip-row"><i :style="{ background: colors?.[hover] }" />{{ labels[hover] }}<b>{{ values?.[hover] }} {{ unit }} · {{ pct(values?.[hover] || 0) }}%</b></div>
        </div>
      </div>
      <div class="legend column">
        <span v-for="(l, i) in labels" :key="l" @mouseenter="hover = i" @mouseleave="hover = null"><i :style="{ background: colors?.[i] }" />{{ l }}<b>{{ values?.[i] }}</b></span>
      </div>
    </div>

    <template v-else>
      <div class="bars">
        <div v-for="(l, i) in labels" :key="l" class="bar-row" @mouseenter="hover = i" @mouseleave="hover = null">
          <span class="bar-label">{{ l }}</span>
          <span class="bar-track"><span class="bar-fill" :style="{ width: ((values?.[i] || 0) / barMax) * 100 + '%', background: colors?.[i] || '#3f3f46' }" /></span>
          <span class="bar-value num">{{ values?.[i] }}</span>
          <div v-if="hover === i" class="tip inline"><div class="tip-row">{{ l }}<b>{{ values?.[i] }} {{ unit }} · {{ pct(values?.[i] || 0) }}%</b></div></div>
        </div>
      </div>
    </template>
  </div>
</template>

<style scoped>
.chart { position: relative; }
.svg { display: block; width: 100%; height: auto; }
.grid { stroke: #f4f4f5; }
.cross { stroke: #d4d4d8; stroke-dasharray: 3 3; }
.axis-label { font-size: 12px; fill: var(--ink-3); }
.tip { position: absolute; z-index: 5; pointer-events: none; transform: translateY(-50%); background: #fff; border: 1px solid var(--line); border-radius: 8px; padding: 8px 12px; box-shadow: var(--shadow-pop); font-size: 12px; line-height: 20px; white-space: nowrap; }
.tip.inline { right: 0; top: 50%; }
.tip-title { color: var(--ink-3); margin-bottom: 2px; }
.tip-row { display: flex; align-items: center; gap: 6px; }
.tip-row b { margin-left: 12px; font-weight: 600; }
.tip-row i, .legend i { width: 8px; height: 8px; border-radius: 50%; display: inline-block; }
.legend { display: flex; gap: 16px; justify-content: center; font-size: 12px; color: var(--ink-2); margin-top: 4px; }
.legend span { display: inline-flex; align-items: center; gap: 6px; }
.legend.column { flex-direction: column; gap: 6px; align-items: stretch; flex: 1; min-width: 0; justify-content: center; font-size: 14px; }
.legend.column b { margin-left: auto; font-weight: 600; }
.donut-wrap { display: flex; align-items: center; gap: 20px; }
.donut { position: relative; display: flex; justify-content: center; flex: none; }
.donut-svg { width: 150px; height: 150px; }
.donut-num { font-size: 22px; font-weight: 600; fill: var(--ink); }
.bars { display: flex; flex-direction: column; gap: 10px; }
.bar-row { position: relative; display: grid; grid-template-columns: 76px minmax(0, 1fr) 36px; gap: 10px; align-items: center; font-size: 14px; }
.bar-label { color: var(--ink-2); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.bar-track { height: 6px; background: var(--subtle); border-radius: 4px; overflow: hidden; }
.bar-fill { display: block; height: 100%; border-radius: 4px; }
.bar-value { text-align: right; font-weight: 600; }
</style>
