FROM nginx:1.28.0-alpine@sha256:30f1c0d78e0ad60901648be663a710bdadf19e4c10ac6782c235200619158284
COPY src/web/ /usr/share/nginx/html/
COPY docker/nginx.compose.conf /etc/nginx/conf.d/default.conf
EXPOSE 80
