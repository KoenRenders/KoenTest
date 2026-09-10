FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
ARG APP_VERSION=onbekend
ARG GIT_SHA=onbekend
ENV APP_VERSION=$APP_VERSION
ENV GIT_SHA=$GIT_SHA
RUN chmod +x startup.sh
RUN APP_ENV=build SECRET_KEY=build-time-check DATABASE_URL=postgresql://x:x@localhost/x python check_imports.py
# Non-root (#395): de app heeft geen root nodig; beperkt de schade bij een
# container-escape of RCE in de applicatie.
RUN useradd --create-home --uid 10001 app && chown -R app:app /app
# #766: the directory for the application log, with the right owner. A named volume
# mounted on it inherits ownership and permissions from this point in the image — which
# is why the mkdir lives here and not in an entrypoint: the app runs as `app` and
# cannot create a directory inside a volume that root already created.
RUN mkdir -p /var/log/raak && chown app:app /var/log/raak
USER app
CMD ["./startup.sh"]
