import { defineNuxtConfig } from 'nuxt/config'

export default defineNuxtConfig({
  srcDir: 'app/',
  compatibilityDate: '2026-09-04',
  devtools: { enabled: false },
  typescript: { strict: true, typeCheck: false },
  css: ['~/assets/main.css', '~/assets/route.css'],
  runtimeConfig: { public: { apiBaseUrl: '' } },
})
