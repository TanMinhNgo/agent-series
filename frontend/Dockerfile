FROM node:22-alpine AS build
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci --ignore-scripts
COPY . .
RUN npm run build

FROM nginxinc/nginx-unprivileged:1.30.4-alpine3.24
USER root
# Keep the Alpine runtime packages patched independently of the Nginx image
# release cadence. CVE-2026-66046 is fixed by libexpat 2.8.4-r0.
RUN apk upgrade --no-cache libexpat
COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /app/dist /usr/share/nginx/html
USER nginx
EXPOSE 8080
