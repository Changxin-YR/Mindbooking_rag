FROM node:22-alpine AS build

WORKDIR /app
RUN corepack disable && npm install --global --force pnpm@12.3.4
COPY package.json pnpm-lock.yaml pnpm-workspace.yaml tsconfig.base.json ./
RUN sed -i '/"packageManager"/d' package.json
COPY apps/reader-web/package.json apps/reader-web/package.json
COPY packages/api-client/package.json packages/api-client/package.json
COPY packages/api-types/package.json packages/api-types/package.json
COPY apps/reader-web apps/reader-web
COPY packages packages
ARG NUXT_PUBLIC_API_BASE_URL=http://localhost:8000
ENV NUXT_PUBLIC_API_BASE_URL=${NUXT_PUBLIC_API_BASE_URL}
ARG NUXT_APP_BASE_URL=/
ENV NUXT_APP_BASE_URL=${NUXT_APP_BASE_URL}
RUN pnpm --config.manage-package-manager-versions=false install --frozen-lockfile
RUN pnpm --config.manage-package-manager-versions=false --filter @mindbooking/reader-web build

FROM node:22-alpine
WORKDIR /app
COPY --from=build /app/apps/reader-web/.output .output
ENV NODE_ENV=production
ENV NITRO_HOST=0.0.0.0
ENV NITRO_PORT=80
EXPOSE 80
CMD ["node", ".output/server/index.mjs"]
