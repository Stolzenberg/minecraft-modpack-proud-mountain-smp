FROM python:3.13-alpine
RUN apk add --no-cache tzdata
WORKDIR /app
COPY app.py index.html favicon.svg ./
USER nobody
EXPOSE 8080
HEALTHCHECK --interval=60s --timeout=5s CMD wget -qO- http://127.0.0.1:8080/api/stats >/dev/null || exit 1
CMD ["python3", "-u", "app.py"]
