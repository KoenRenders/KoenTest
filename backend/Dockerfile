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
# #766: de map voor het applicatielog, met de juiste eigenaar. Een named volume
# erop neemt eigendom en rechten van dit punt in het image over — daarom staat de
# mkdir hier en niet in een entrypoint: de app draait als `app` en kan zelf geen
# map maken in een volume dat root al aangemaakt heeft.
RUN mkdir -p /var/log/raak && chown app:app /var/log/raak
USER app
CMD ["./startup.sh"]
