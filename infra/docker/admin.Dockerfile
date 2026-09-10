FROM node:22-alpine AS build

WORKDIR /app
RUN corepack disable && npm install --global --force pnpm@12.3.4
COPY package.json pnpm-lock.yaml pnpm-workspace.yaml tsconfig.base.json ./
RUN sed -i '/"packageManager"/d' package.json
COPY apps/admin-web/package.json apps/admin-web/package.json
COPY packages/api-client/package.json packages/api-client/package.json
COPY packages/api-types/package.json packages/api-types/package.json
COPY apps/admin-web apps/admin-web
COPY packages packages
ARG VITE_API_BASE_URL=http://localhost:8000
ENV VITE_API_BASE_URL=${VITE_API_BASE_URL}
ARG VITE_APP_BASE=/admin/
ENV VITE_APP_BASE=${VITE_APP_BASE}
RUN pnpm --config.manage-package-manager-versions=false install --frozen-lockfile
RUN pnpm --config.manage-package-manager-versions=false --filter @mindbooking/admin-web build

FROM nginx:1.27-alpine
COPY --from=build /app/apps/admin-web/dist /usr/share/nginx/html
COPY infra/nginx/spa.conf /etc/nginx/conf.d/default.conf
EXPOSE 80
