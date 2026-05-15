FROM nginx:alpine
COPY index.html /usr/share/nginx/html/
COPY mockup-*.png /usr/share/nginx/html/
EXPOSE 80
