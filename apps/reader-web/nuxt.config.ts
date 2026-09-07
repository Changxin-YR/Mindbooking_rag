import { defineNuxtConfig } from 'nuxt/config'

const environment = (globalThis as typeof globalThis & {
  process?: { env?: Record<string, string | undefined> }
}).process?.env

export default defineNuxtConfig({
  srcDir: 'app/',
  app: { baseURL: environment?.NUXT_APP_BASE_URL || '/' },
  compatibilityDate: '2026-09-04',
  devtools: { enabled: false },
  typescript: { strict: true, typeCheck: false },
  css: ['~/assets/main.css', '~/assets/route.css'],
  runtimeConfig: { public: { apiBaseUrl: environment?.NUXT_PUBLIC_API_BASE_URL || 'http://localhost:8000' } },
})
