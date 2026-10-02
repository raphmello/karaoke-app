# Caddy with the frontend built in: Node and pnpm exist only in the build stage (docs/ARCHITECTURE.md, deployment).
FROM node:22-slim AS web
ARG PNPM_VERSION=12.8.1
RUN npm install -g pnpm@${PNPM_VERSION}
WORKDIR /web
COPY web/package.json web/pnpm-lock.yaml ./
RUN --mount=type=cache,target=/root/.local/share/pnpm/store pnpm install --frozen-lockfile
COPY web/ ./
RUN pnpm build

FROM caddy:2
COPY docker/Caddyfile /etc/caddy/Caddyfile
COPY --from=web /web/dist /srv/web
