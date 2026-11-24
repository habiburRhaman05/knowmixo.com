# syntax=docker/dockerfile:1.7
# Multi-stage build for the Knowmivo Next.js frontend.
#
# Design:
#   - `deps`  installs production dependencies against a small base.
#   - `build` runs the production build with Next.js' standalone output.
#   - `run`   copies only the standalone server, static assets and public
#             files. The final image is non-root and runs `next` directly
#             (no npm wrapper) for faster startup and smaller surface.
#
# Build arguments:
#   NEXT_PUBLIC_APP_URL          public URL of this deployment
#   NEXT_PUBLIC_GOOGLE_CLIENT_ID baked into the client bundle at build time

FROM node:22-alpine AS deps
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci --no-audit --no-fund --omit=optional

FROM node:22-alpine AS build
WORKDIR /app
ENV NEXT_TELEMETRY_DISABLED=1
ARG NEXT_PUBLIC_APP_URL
ARG NEXT_PUBLIC_GOOGLE_CLIENT_ID
ENV NEXT_PUBLIC_APP_URL=${NEXT_PUBLIC_APP_URL}
ENV NEXT_PUBLIC_GOOGLE_CLIENT_ID=${NEXT_PUBLIC_GOOGLE_CLIENT_ID}
COPY --from=deps /app/node_modules ./node_modules
COPY . .
# `next.config.mjs` reads env eagerly on import, so provide stubs here.
ENV BACKEND_INTERNAL_URL=http://127.0.0.1:8000
RUN npm run build

FROM node:22-alpine AS run
WORKDIR /app
RUN addgroup -g 10001 nodegrp && adduser -D -u 10001 -G nodegrp knowmivo
ENV NODE_ENV=production
ENV NEXT_TELEMETRY_DISABLED=1
ENV PORT=3000
ENV HOSTNAME=0.0.0.0

# Next standalone bundles only what the server needs, including its own
# node_modules.
COPY --from=build /app/public ./public
COPY --from=build /app/.next/standalone ./
COPY --from=build /app/.next/static ./.next/static

USER knowmivo
EXPOSE 3000
HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
  CMD node -e "require('http').get('http://127.0.0.1:3000/api/health', r => process.exit(r.statusCode === 200 ? 0 : 1)).on('error', () => process.exit(1))"

CMD ["node", "server.js"]
