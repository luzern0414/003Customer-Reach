<script setup lang="ts">
// 全站一套线性图标：24 栅格、1.75 像素描边（任何尺寸保持同一线宽）、圆角端点；颜色跟随文字。
const props = withDefaults(defineProps<{ name: string; size?: number }>(), { size: 20 })

const PATHS: Record<string, string> = {
  lock: 'M6 11h12v10H6zM8.5 11V8a3.5 3.5 0 0 1 7 0v3M12 15v2',
  logout: 'M15 4h4v16h-4M10 8l-4 4 4 4M6 12h10',
  ticket: 'M4 7h16v3a2 2 0 0 0 0 4v3H4v-3a2 2 0 0 0 0-4zM14 7v10',
  radar: 'M12 3a9 9 0 1 0 9 9M12 7.5a4.5 4.5 0 1 0 4.5 4.5M12 12l5-5',
  sidebar: 'M4 5h16v14H4zM9 5v14',
  down: 'M6 9l6 6 6-6',
  overview: 'M4 20V10M10 20V4M16 20v-7M21 20H3',
  workbench: 'M4 5h16v11H9l-5 4z M8 9h8M8 12h5',
  company: 'M4 21V5l8-2v18M12 7h8v14M7 8h2M7 12h2M7 16h2M15 11h2M15 15h2M2 21h20',
  lead: 'M12 4a8 8 0 1 0 0 16a8 8 0 1 0 0-16M12 8a4 4 0 1 0 0 8a4 4 0 1 0 0-8M12 11.2a.8.8 0 1 0 0 1.6a.8.8 0 1 0 0-1.6',
  source: 'M5 6c0-1.7 3.1-3 7-3s7 1.3 7 3-3.1 3-7 3-7-1.3-7-3M5 6v6c0 1.7 3.1 3 7 3s7-1.3 7-3V6M5 12v6c0 1.7 3.1 3 7 3s7-1.3 7-3v-6',
  settings: 'M12 9a3 3 0 1 0 0 6a3 3 0 1 0 0-6M12 2v3M12 19v3M2 12h3M19 12h3M4.9 4.9l2.1 2.1M17 17l2.1 2.1M4.9 19.1L7 17M17 7l2.1-2.1',
  search: 'M11 5a6 6 0 1 0 0 12a6 6 0 1 0 0-12M20 20l-4.5-4.5',
  plus: 'M12 5v14M5 12h14',
  refresh: 'M20 12a8 8 0 1 1-2.3-5.7M20 4v5h-5',
  download: 'M12 4v11M7 10l5 5 5-5M5 20h14',
  external: 'M14 4h6v6M20 4l-9 9M18 14v5a1 1 0 0 1-1 1H5a1 1 0 0 1-1-1V7a1 1 0 0 1 1-1h5',
  doc: 'M6 3h9l4 4v14H6zM14 3v5h5M9 12h7M9 16h5',
  check: 'M5 12l4 4 10-10',
  close: 'M6 6l12 12M18 6L6 18',
  chevron: 'M9 6l6 6-6 6',
  back: 'M15 6l-6 6 6 6',
  play: 'M8 5l11 7-11 7z',
  stop: 'M7 7h10v10H7z',
  attach: 'M20 11.5l-8 8a5 5 0 0 1-7-7l8.5-8.5a3.3 3.3 0 0 1 4.7 4.7L9.7 17.2a1.7 1.7 0 0 1-2.4-2.4L15 7',
  copy: 'M9 9h11v11H9zM5 15H4V4h11v1',
  user: 'M12 4a4 4 0 1 0 0 8a4 4 0 1 0 0-8M4 21a8 8 0 0 1 16 0',
  phone: 'M5 4h4l2 5-2.5 1.5a11 11 0 0 0 5 5L15 13l5 2v4a2 2 0 0 1-2 2A16 16 0 0 1 3 6a2 2 0 0 1 2-2',
  calendar: 'M4 6h16v14H4zM4 10h16M8 3v4M16 3v4',
  alert: 'M12 3l10 18H2zM12 10v4M12 17v.5',
  trash: 'M4 7h16M10 11v6M14 11v6M6 7l1 13h10l1-13M9 7V4h6v3',
  link: 'M10 14a4 4 0 0 0 5.7 0l3-3a4 4 0 0 0-5.7-5.7l-1 1M14 10a4 4 0 0 0-5.7 0l-3 3a4 4 0 0 0 5.7 5.7l1-1',
  pin: 'M12 21s7-6.2 7-11.5A7 7 0 0 0 5 9.5C5 14.8 12 21 12 21M12 7a2.5 2.5 0 1 0 0 5a2.5 2.5 0 1 0 0-5',
  cart: 'M3 4h2l2.4 11h11L21 7H6.2M9 19.5a1 1 0 1 0 0 .1M18 19.5a1 1 0 1 0 0 .1',
  trophy: 'M8 4h8v5a4 4 0 0 1-8 0zM8 6H4a3 3 0 0 0 4 3M16 6h4a3 3 0 0 1-4 3M12 13v4M8 21h8M9 17h6',
  customers: 'M9 4a3.5 3.5 0 1 0 0 7a3.5 3.5 0 1 0 0-7M2 20a7 7 0 0 1 14 0M16 4.5a3.5 3.5 0 0 1 0 6.5M18.5 14A7 7 0 0 1 22 20',
  supplier: 'M2 6h11v10H2zM13 9h4l4 4v3h-8M6 18.5a1.5 1.5 0 1 0 0 .1M17 18.5a1.5 1.5 0 1 0 0 .1',
  rival: 'M4 4l16 16M20 4L4 20M4 4h4M4 4v4M20 4h-4M20 4v4',
  menu: 'M4 6h16M4 12h16M4 18h16',
  send: 'M12 19V5M6 11l6-6 6 6',
  skip: 'M5 5l9 7-9 7zM18 5v14',
  login: 'M14 4h5v16h-5M10 16l4-4-4-4M14 12H3',
  history: 'M4 12a8 8 0 1 0 2.3-5.7M4 4v5h5M12 8v4l3 2',
  spark: 'M12 3v4M12 17v4M3 12h4M17 12h4M6 6l2.5 2.5M15.5 15.5L18 18M6 18l2.5-2.5M15.5 8.5L18 6',
  mail: 'M3 6h18v12H3zM3 7l9 6 9-6',
  web: 'M12 3a9 9 0 1 0 0 18a9 9 0 1 0 0-18M3 12h18M12 3c2.5 2.5 3.8 5.5 3.8 9s-1.3 6.5-3.8 9c-2.5-2.5-3.8-5.5-3.8-9S9.5 5.5 12 3',
  note: 'M5 4h14v16H5zM8 8h8M8 12h8M8 16h5',
  analysis: 'M4 19h16M6 16l4-5 3 3 5-7',
  flag: 'M5 21V4M5 4h11l-2 4 2 4H5',
}
</script>

<template>
  <svg :width="props.size" :height="props.size" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.75"
       stroke-linecap="round" stroke-linejoin="round" aria-hidden="true" class="icon" style="flex:none">
    <path :d="PATHS[props.name] || PATHS.doc" vector-effect="non-scaling-stroke" />
  </svg>
</template>
