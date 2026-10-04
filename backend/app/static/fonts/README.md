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
- Bestanden: `Inter-Italic.ttf` en `Inter-BoldItalic.ttf` — **enkel voor de PDF**
  (het vergaderverslag, #939). Reden: WeasyPrint/Pango maakt géén schuine variant
  bij wanneer er alleen een rechte letter bestaat, dus zonder deze twee bestanden
  bleef cursieve tekst rechtop staan — gemeten, niet aangenomen. De site heeft ze
  niet nodig: de browser doet daar wél schuinstelling.
- **The `.ttf` files are real TrueType (glyf outlines) since #1522.** Until then
  they were Debian's CFF fonts under a `.ttf` name, and the italics were `.otf`:
  WeasyPrint embedded every font of the meeting PDF as CFF in an OpenType wrapper
  (`FontFile3/OpenType`), and an Android phone's built-in PDF preview showed all
  of its text as wrong glyphs. TrueType is embedded as `FontFile2`, the form every
  reader handles. `meetings/tests/test_meeting_pdf_fonts.py` holds it: a font the
  PDF names without a `glyf` table fails the test.
- Herkomst: the `.ttf` files come from the official Inter 4.1 release,
  `Inter-4.1.zip` from https://github.com/rsms/inter/releases/tag/v4.1
  (sha256 `9883fdd4a49d4fb66bd8177ba6625ef9a64aa45899767dde3d36aa425756b11e`),
  folder `extras/ttf/` — the same design version (`4.001;git-9221beed3`) as the
  `woff2` files, which still come from het Debian-pakket `fonts-inter` 4.1+ds-1
  (OTF, met `fontTools` omgezet naar woff2).
- **Subset** op Latin, Latin Extended-A/B, interpunctie, valuta en enkele pijlen
  (`U+0000-024F`, `U+2000-206F`, `U+20A0-20BF`, …). Dat scheelt fors: 596 kB OTF
  wordt 65 kB woff2. De site is nl-BE; volledige Unicode-dekking is niet nodig.
- Licentie: **SIL Open Font License 1.1** (OFL) en Apache-2.0, zoals vermeld in
  het copyright-bestand van het Debian-pakket.

Reproduceren — the `.ttf` files (#1522), from the official release, with the
same ranges:

```bash
unzip -j Inter-4.1.zip 'extras/ttf/Inter-*.ttf' -d src
RANGES="U+0000-00FF,U+0100-017F,U+0180-024F,U+2000-206F,U+20A0-20BF,U+2122,U+2190-2193,U+2212,U+FB00-FB04"
for name in Regular Medium SemiBold Bold Italic BoldItalic; do
  python3 -m fontTools.subset "src/Inter-$name.ttf" --unicodes="$RANGES" \
    --layout-features='*' --output-file="Inter-$name.ttf"
done
```

Reproduceren — the `woff2` files (geen sudo nodig, geen externe download):

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
