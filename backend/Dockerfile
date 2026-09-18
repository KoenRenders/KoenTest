FROM python:3.12-slim
WORKDIR /app
# WeasyPrint (#258) rendert de vergader-PDF en heeft Pango/Cairo nodig — een
# systeemafhankelijkheid, geen pip-pakket. Ze staat hier vóór de pip-install zodat
# de laag gecachet blijft, en `check_imports.py` verderop importeert weasyprint:
# ontbreekt een van deze pakketten, dan faalt de BUILD en niet de eerste PDF in
# productie.
#
# libcairo2 (#989): CairoSVG renders the PNG version of an SVG logo for e-mail.
# Measured: WeasyPrint 70 no longer uses Cairo, and the Pango packages do not
# bring it along — Koen chose to add it (17 September 2026).
#
# Inkscape (#1007, CR-10): renders the poster SVGs to PDF and PNG as a
# subprocess, without network. fontconfig sees the app's own fonts (Radio Canada
# Big, Caveat, Inter) through the symlink below, so a poster embeds the same
# faces on every host; `fc-cache` makes them known at build time.
RUN apt-get update \
    && apt-get install -y --no-install-recommends libpango-1.0-0 libpangoft2-1.0-0 libcairo2 inkscape fontconfig \
    && rm -rf /var/lib/apt/lists/*
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
ARG APP_VERSION=onbekend
ARG GIT_SHA=onbekend
ENV APP_VERSION=$APP_VERSION
ENV GIT_SHA=$GIT_SHA
RUN chmod +x startup.sh
RUN mkdir -p /usr/local/share/fonts && ln -s /app/app/static/fonts /usr/local/share/fonts/raak && fc-cache -f
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
