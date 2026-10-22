import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
// 保留旧hash资源，已打开页面的懒加载不会因重建被删文件；不自动递归清空dist。
export default defineConfig({plugins:[vue()],server:{proxy:{'/api':'http://127.0.0.1:8000'}},build:{emptyOutDir:false,rollupOptions:{output:{manualChunks(id){if(/node_modules\/(markstream|stream-markdown|markdown-it|@mdit|shiki|@shikijs|hast|unist|vfile|oniguruma)/.test(id))return 'markdown';if(id.includes('node_modules/vue-element-plus-x')||id.includes('node_modules/x-sender'))return 'chat';if(id.includes('node_modules/element-plus')||id.includes('node_modules/@element-plus'))return 'ui';if(id.includes('node_modules'))return 'vendor'}}}}})
