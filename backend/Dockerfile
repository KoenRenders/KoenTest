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
USER app
CMD ["./startup.sh"]
