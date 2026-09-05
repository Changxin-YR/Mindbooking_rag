FROM node:22-alpine AS build

WORKDIR /app
RUN corepack enable
COPY package.json pnpm-lock.yaml pnpm-workspace.yaml tsconfig.base.json ./
COPY apps/writer-web/package.json apps/writer-web/package.json
COPY packages/api-client/package.json packages/api-client/package.json
COPY packages/api-types/package.json packages/api-types/package.json
COPY apps/writer-web apps/writer-web
COPY packages packages
RUN pnpm install --frozen-lockfile
RUN pnpm --filter @mindbooking/writer-web build

FROM nginx:1.27-alpine
COPY --from=build /app/apps/writer-web/dist /usr/share/nginx/html
COPY infra/nginx/spa.conf /etc/nginx/conf.d/default.conf
EXPOSE 80
