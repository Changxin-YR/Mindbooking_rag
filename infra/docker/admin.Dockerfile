FROM node:22-alpine AS build

WORKDIR /app
RUN corepack enable
COPY package.json pnpm-lock.yaml pnpm-workspace.yaml tsconfig.base.json ./
COPY apps/admin-web/package.json apps/admin-web/package.json
COPY packages/api-client/package.json packages/api-client/package.json
COPY packages/api-types/package.json packages/api-types/package.json
COPY apps/admin-web apps/admin-web
COPY packages packages
RUN pnpm install --frozen-lockfile
RUN pnpm --filter @mindbooking/admin-web build

FROM nginx:1.27-alpine
COPY --from=build /app/apps/admin-web/dist /usr/share/nginx/html
COPY infra/nginx/spa.conf /etc/nginx/conf.d/default.conf
EXPOSE 80
