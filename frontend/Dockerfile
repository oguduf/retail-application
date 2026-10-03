FROM nginx:1.27-alpine

COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY index.html styles.css app.js /usr/share/nginx/html/

RUN chown -R 101:101 /var/cache/nginx && chown 101:101 /var/run
USER 101:101

EXPOSE 8080

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 CMD ["wget", "-q", "-O", "/dev/null", "http://127.0.0.1:8080/health"]

ENTRYPOINT ["nginx"]
CMD ["-g", "daemon off;"]
