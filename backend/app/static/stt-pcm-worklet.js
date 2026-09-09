// AudioWorklet voor de Voxtral-spraakinvoer (#282). Draait in de audio-thread: neemt
// de mic-blokken (Float32 op de snelheid van de AudioContext), zet ze om naar 16-bit
// PCM (pcm_s16le, wat Voxtral verwacht) en stuurt elk blok naar de hoofdthread,
// samen met de RMS-energie voor stilte-detectie (VAD).
//
// #772: hier wordt NIET meer herbemonsterd. Tussen #751 en #772 stond hier lineaire
// interpolatie zonder anti-aliasfilter, en dat is geen herbemonstering maar decimatie:
// 48/16 is precies 3, dus de posities vielen op hele samples en de interpolatie kreeg
// nooit een breukdeel te zien. Gemeten op die versie, met een raster van 125 Hz over
// de uitgang: een toon van 10 kHz kwam terug op 6 kHz met amplitude 0,25 — even sterk
// als het origineel — en 14 kHz op 2 kHz, midden in de spraakband. Nul demping. Een
// mens hoort daar nog spraak doorheen; Voxtral kreeg tientallen audioblokken en
// stuurde nul `transcription.text.delta` terug.
//
// De les is niet "bouw een beter filter" maar "doe het niet zelf". Herbemonsteren is
// de taak van de browser, die het met een echt filter doet. `stt.js` vraagt daarom om
// 16 kHz en probeert de context daarop te zetten; lukt dat niet, dan gaat de audio op
// apparaatsnelheid naar de server en krijgt Voxtral die snelheid te horen. Deze
// worklet is daardoor wat hij altijd had moeten zijn: Float32 naar Int16, en tellen.
//
// De RMS hoort bij dezelfde stroom die verstuurd wordt — dat was de reden dat ze hier
// berekend wordt en niet in `stt.js`, en dat blijft zo.

class SttPcmWorklet extends AudioWorkletProcessor {
  process(inputs) {
    const input = inputs[0];
    if (!input || input.length === 0) return true;
    const channel = input[0];
    if (!channel || channel.length === 0) return true;

    const n = channel.length;
    const pcm = new Int16Array(n);
    let sumSq = 0;
    for (let i = 0; i < n; i++) {
      let s = channel[i];
      if (s > 1) s = 1;
      else if (s < -1) s = -1;
      pcm[i] = s < 0 ? s * 0x8000 : s * 0x7fff;
      sumSq += s * s;
    }
    const rms = Math.sqrt(sumSq / n);
    // Transfer de buffer (zero-copy) i.p.v. te kopiëren.
    this.port.postMessage({ pcm: pcm.buffer, rms }, [pcm.buffer]);
    return true;
  }
}

registerProcessor("stt-pcm-worklet", SttPcmWorklet);
