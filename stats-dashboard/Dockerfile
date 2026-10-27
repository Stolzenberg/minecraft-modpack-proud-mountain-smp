FROM python:3.13-alpine
RUN apk add --no-cache tzdata && pip install --no-cache-dir pymysql==1.1.1
WORKDIR /app
COPY fetch_lang.py ./
RUN python3 fetch_lang.py 1.21.1
COPY app.py index.html favicon.svg ./
USER nobody
# PyMySQL fragt beim Import nach dem Benutzernamen, die UID aus compose.yaml hat keinen Eintrag in /etc/passwd
ENV USER=stats
EXPOSE 8080
HEALTHCHECK --interval=60s --timeout=5s CMD wget -qO- http://127.0.0.1:8080/api/stats >/dev/null || exit 1
CMD ["python3", "-u", "app.py"]
