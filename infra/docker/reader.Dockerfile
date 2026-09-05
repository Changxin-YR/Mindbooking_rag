FROM node:22-alpine AS build

WORKDIR /app
RUN corepack enable
COPY package.json pnpm-lock.yaml pnpm-workspace.yaml tsconfig.base.json ./
COPY apps/reader-web/package.json apps/reader-web/package.json
COPY packages/api-client/package.json packages/api-client/package.json
COPY packages/api-types/package.json packages/api-types/package.json
COPY apps/reader-web apps/reader-web
COPY packages packages
RUN pnpm install --frozen-lockfile
RUN pnpm --filter @mindbooking/reader-web build

FROM node:22-alpine
WORKDIR /app
COPY --from=build /app/apps/reader-web/.output .output
ENV NODE_ENV=production
ENV NITRO_HOST=0.0.0.0
ENV NITRO_PORT=80
EXPOSE 80
CMD ["node", ".output/server/index.mjs"]
