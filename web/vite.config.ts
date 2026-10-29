import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import Components from 'unplugin-vue-components/vite'

// Element Plus 按需引入：每个组件从自己的目录导入（从包入口导入会连带打包全部组件）；
// 样式仍整体引入（main.ts），命令式调用的消息框也有样式。
const PARENT: Record<string, string> = {
  TableColumn: 'table', FormItem: 'form', RadioGroup: 'radio', RadioButton: 'radio', Option: 'select', OptionGroup: 'select',
  TimelineItem: 'timeline', DropdownMenu: 'dropdown', DropdownItem: 'dropdown', CheckboxGroup: 'checkbox', CheckboxButton: 'checkbox',
  SkeletonItem: 'skeleton',
}
const elementPlus = [
  {
    type: 'component' as const,
    resolve: (name: string) => {
      if (!/^El[A-Z]/.test(name)) return undefined
      const base = name.slice(2)
      const dir = PARENT[base] || base.replace(/([a-z0-9])([A-Z])/g, '$1-$2').toLowerCase()
      return { name, from: `element-plus/es/components/${dir}/index.mjs` }
    },
  },
  {
    type: 'directive' as const,
    resolve: (name: string) => (name === 'Loading' ? { name: 'ElLoadingDirective', from: 'element-plus/es/components/loading/index.mjs' } : undefined),
  },
]

export default defineConfig({
  plugins: [vue(), Components({ resolvers: elementPlus, dts: false })],
  server: { proxy: { '/api': 'http://127.0.0.1:8000' } },
  build: {
    rollupOptions: {
      output: {
        manualChunks(id) {
          if (/node_modules\/(markstream|stream-markdown|markdown-it|shiki|@shikijs)/.test(id)) return 'markdown'
          if (id.includes('node_modules/element-plus')) return 'ui'
          if (id.includes('node_modules')) return 'vendor'
        },
      },
    },
  },
})
