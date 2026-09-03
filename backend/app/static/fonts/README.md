# Lettertypes (self-hosted)

## Radio Canada Big

- Bestand: `RadioCanadaBig-VariableFont_wght.ttf` (variabel, gewicht 400–700).
- Gebruik: het **merkfont** van Raak, enkel op de koppen (zie `scripts/build-css.sh`,
  `@font-face` + `@layer base` in de gegenereerde `app.css`). Lopende tekst blijft
  een neutrale systeemfont.
- Licentie: **SIL Open Font License 1.1** (OFL) — vrij te gebruiken en te
  herdistribueren, ook zelf-gehost. Bron: Google Fonts
  (https://fonts.google.com/specimen/Radio+Canada+Big). De volledige OFL-tekst
  hoort bij het lettertype op de bronpagina.

## Inter

- Bestanden: `Inter-{Regular,Medium,SemiBold,Bold}.{woff2,ttf}` — gewichten
  400/500/600/700, de vier die het design system gebruikt.
- Gebruik: de **body-font** (lopende tekst, tabellen, formulieren). Radio Canada
  Big blijft voorbehouden aan koppen.
- Herkomst: het Debian-pakket `fonts-inter` 4.1+ds-1 (upstream
  https://github.com/rsms/inter). Debian levert OTF; die zijn met `fontTools`
  omgezet naar woff2 en ttf.
- **Subset** op Latin, Latin Extended-A/B, interpunctie, valuta en enkele pijlen
  (`U+0000-024F`, `U+2000-206F`, `U+20A0-20BF`, …). Dat scheelt fors: 596 kB OTF
  wordt 65 kB woff2. De site is nl-BE; volledige Unicode-dekking is niet nodig.
- Licentie: **SIL Open Font License 1.1** (OFL) en Apache-2.0, zoals vermeld in
  het copyright-bestand van het Debian-pakket.

Reproduceren (geen sudo nodig, geen externe download):

```bash
apt-get download fonts-inter python3-fonttools python3-brotli
for d in *.deb; do dpkg-deb -x "$d" x; done
export PYTHONPATH=x/usr/lib/python3/dist-packages
RANGES="U+0000-00FF,U+0100-017F,U+0180-024F,U+2000-206F,U+20A0-20BF,U+2122,U+2190-2193,U+2212,U+FB00-FB04"
python3 -m fontTools.subset x/usr/share/fonts/opentype/inter/Inter-Regular.otf \
  --unicodes="$RANGES" --layout-features='*' --flavor=woff2 --output-file=Inter-Regular.woff2
```

Self-hosted (geen externe font-CDN) omwille van privacy/GDPR en om externe
verzoeken vanuit de browser te vermijden — in lijn met het Europe-First-beleid.
