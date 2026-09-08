FROM node:22-alpine AS build
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci --ignore-scripts
COPY . .
RUN npm run build

FROM nginxinc/nginx-unprivileged:1.30.4-alpine3.24
USER root
# Keep the Alpine runtime packages patched independently of the Nginx image
# release cadence. This covers libexpat and the util-linux/libuuid CVEs.
RUN apk upgrade --no-cache libexpat libuuid
COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /app/dist /usr/share/nginx/html
USER nginx
EXPOSE 8080
