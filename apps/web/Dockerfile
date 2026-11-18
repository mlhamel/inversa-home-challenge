# syntax=docker/dockerfile:1
# Build context is the repository root:
#   docker build -f apps/web/Dockerfile -t inversa-frontend .
FROM node:22-bookworm-slim AS build

ENV NEXT_TELEMETRY_DISABLED=1

WORKDIR /app

COPY apps/web/package.json apps/web/package-lock.json ./

RUN --mount=type=cache,target=/root/.npm \
    npm ci

COPY apps/web .

ARG NEXT_PUBLIC_API_URL=http://localhost:8000
ENV NEXT_PUBLIC_API_URL=$NEXT_PUBLIC_API_URL

RUN npm run build

FROM node:22-bookworm-slim

ENV NODE_ENV=production \
    NEXT_TELEMETRY_DISABLED=1

WORKDIR /app

COPY --from=build --chown=node:node /app/node_modules ./node_modules
COPY --from=build --chown=node:node /app/.next ./.next
COPY --from=build --chown=node:node /app/package.json ./package.json
COPY --from=build --chown=node:node /app/next.config.mjs ./next.config.mjs

USER node

EXPOSE 8080

CMD ["sh", "-c", "exec node node_modules/next/dist/bin/next start -p ${PORT:-8080}"]
