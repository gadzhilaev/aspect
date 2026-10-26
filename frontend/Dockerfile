# Aspect frontend: production Vite build + nginx reverse proxy to API.
FROM node:24.19.0-bookworm-slim AS build

WORKDIR /web

COPY package.json package-lock.json ./
RUN npm ci

COPY . ./
# Same-origin API via nginx (/api → api:8000). Do not bake Docker hostname.
ENV VITE_API_BASE_URL= \
    VITE_AGENT_DEMO=true
RUN npm run build

FROM nginx:1.27.5-alpine

COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /web/dist /usr/share/nginx/html

EXPOSE 80

HEALTHCHECK --interval=15s --timeout=5s --start-period=10s --retries=5 \
  CMD wget -q -O /dev/null http://127.0.0.1/healthz || exit 1
