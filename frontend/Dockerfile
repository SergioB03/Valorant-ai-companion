# Stage 1: build the Vite bundle. VITE_API_URL is baked in at build time; in the
# Docker Compose deployment the API is served same-origin under /api (see Caddyfile),
# which also means the browser never makes a cross-origin (CORS) request.
FROM node:22-alpine AS build
WORKDIR /src
COPY package.json package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY . .
ARG VITE_API_URL=/api
ARG VITE_ANALYTICS=
ENV VITE_API_URL=$VITE_API_URL VITE_ANALYTICS=$VITE_ANALYTICS
RUN npm run build

# Stage 2: Caddy serves the static bundle and proxies /api/* to the backend.
FROM caddy:2-alpine
COPY Caddyfile /etc/caddy/Caddyfile
COPY --from=build /src/dist /srv
