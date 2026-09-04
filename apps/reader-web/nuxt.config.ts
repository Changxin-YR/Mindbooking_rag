import { defineNuxtConfig } from 'nuxt/config'

export default defineNuxtConfig({
  srcDir: 'app/',
  devtools: { enabled: false },
  typescript: { strict: true, typeCheck: false },
  css: ['~/assets/main.css'],
  runtimeConfig: { public: { apiBaseUrl: '' } },
})
