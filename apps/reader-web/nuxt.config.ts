import { defineNuxtConfig } from 'nuxt/config'

export default defineNuxtConfig({
  srcDir: 'app/',
  devtools: { enabled: false },
  typescript: { strict: true, typeCheck: true },
  css: ['~/assets/main.css'],
  runtimeConfig: { public: { apiBaseUrl: '' } },
})
