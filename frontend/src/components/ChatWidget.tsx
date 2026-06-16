"use client";
import { useEffect, useRef, useState } from "react";
import { streamChat, type ChatMsg } from "@/lib/api";

// Zwevende chatbot 'Raakje' (#205). Tekst-first met spraakinvoer (STT) als
// progressive enhancement: de microfoonknop verschijnt enkel als de browser de
// Web Speech API ondersteunt. STT staat volledig los van de LLM. Let op: in
// Chrome/Safari verloopt de herkenning via de servers van de browserleverancier
// (Google/Apple) — vermeld dit in de privacyverklaring.

const WELCOME =
  "Hallo, ik ben Raakje! 👋 Stel me gerust een vraag over Raak Millegem, onze activiteiten of het lidmaatschap. Ik kan ook je vraag of idee doorgeven aan het bestuur.";

// Minimale shim voor de niet-gestandaardiseerde Web Speech API-types.
type SpeechRecognitionLike = {
  lang: string;
  interimResults: boolean;
  continuous: boolean;
  onresult: (e: SpeechResultEvent) => void;
  onerror: () => void;
  onend: () => void;
  start: () => void;
  stop: () => void;
};
type SpeechResultEvent = {
  resultIndex: number;
  results: ArrayLike<ArrayLike<{ transcript: string }> & { isFinal: boolean }>;
};
type SpeechRecognitionCtor = new () => SpeechRecognitionLike;

export default function ChatWidget() {
  const [open, setOpen] = useState(false);
  const [messages, setMessages] = useState<ChatMsg[]>([]);
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const [listening, setListening] = useState(false);
  const scrollRef = useRef<HTMLDivElement>(null);
  const recRef = useRef<SpeechRecognitionLike | null>(null);
  const ctorRef = useRef<SpeechRecognitionCtor | null>(null);
  const [sttSupported, setSttSupported] = useState(false);

  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight });
  }, [messages, open]);

  // Feature-detectie van de Web Speech API (alleen client-side).
  useEffect(() => {
    const w = window as unknown as {
      SpeechRecognition?: SpeechRecognitionCtor;
      webkitSpeechRecognition?: SpeechRecognitionCtor;
    };
    const Ctor = w.SpeechRecognition || w.webkitSpeechRecognition;
    if (Ctor) {
      ctorRef.current = Ctor;
      setSttSupported(true);
    }
    return () => recRef.current?.stop();
  }, []);

  function toggleMic() {
    if (busy) return;
    if (listening) {
      recRef.current?.stop();
      return;
    }
    const Ctor = ctorRef.current;
    if (!Ctor) return;

    const rec = new Ctor();
    rec.lang = "nl-BE";
    rec.interimResults = true;
    rec.continuous = false;

    let finalText = "";
    rec.onresult = (e) => {
      let interim = "";
      for (let i = e.resultIndex; i < e.results.length; i++) {
        const res = e.results[i];
        const transcript = res[0].transcript;
        if (res.isFinal) finalText += transcript;
        else interim += transcript;
      }
      setInput((finalText + interim).trim());
    };
    rec.onerror = () => setListening(false);
    rec.onend = () => setListening(false);

    recRef.current = rec;
    setInput("");
    setListening(true);
    rec.start();
  }

  async function send() {
    const text = input.trim();
    if (!text || busy) return;
    recRef.current?.stop();

    const history: ChatMsg[] = [...messages, { role: "user", content: text }];
    setMessages([...history, { role: "assistant", content: "" }]);
    setInput("");
    setBusy(true);

    try {
      let answer = "";
      for await (const delta of streamChat(history)) {
        answer += delta;
        setMessages([...history, { role: "assistant", content: answer }]);
      }
      if (!answer.trim()) {
        setMessages([
          ...history,
          { role: "assistant", content: "Sorry, ik kreeg geen antwoord. Probeer het opnieuw." },
        ]);
      }
    } catch (err) {
      const msg = err instanceof Error ? err.message : "Er ging iets mis.";
      setMessages([...history, { role: "assistant", content: msg }]);
    } finally {
      setBusy(false);
    }
  }

  function onKeyDown(e: React.KeyboardEvent<HTMLTextAreaElement>) {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      send();
    }
  }

  return (
    <>
      {/* Zwevende knop */}
      <button
        aria-label={open ? "Sluit chat" : "Open chat met Raakje"}
        onClick={() => setOpen((o) => !o)}
        className="fixed bottom-5 right-5 z-50 h-14 w-14 rounded-full bg-blue-700 hover:bg-blue-800 text-white shadow-lg flex items-center justify-center text-2xl transition-colors"
      >
        {open ? "✕" : "💬"}
      </button>

      {/* Paneel */}
      {open && (
        <div className="fixed bottom-24 right-5 z-50 w-[92vw] max-w-sm h-[70vh] max-h-[32rem] bg-white rounded-2xl shadow-2xl border border-gray-200 flex flex-col overflow-hidden">
          <div className="bg-blue-700 text-white px-4 py-3 font-semibold flex items-center gap-2">
            <span className="text-xl">💬</span> Raakje — chat met de vereniging
          </div>

          <div ref={scrollRef} className="flex-1 overflow-y-auto p-3 space-y-3 bg-gray-50">
            <Bubble role="assistant" content={WELCOME} />
            {messages.map((m, i) => (
              <Bubble key={i} role={m.role} content={m.content} typing={busy && m.role === "assistant" && i === messages.length - 1 && !m.content} />
            ))}
          </div>

          <div className="border-t border-gray-200 p-2 flex items-end gap-2">
            {sttSupported && (
              <button
                onClick={toggleMic}
                disabled={busy}
                aria-label={listening ? "Stop met opnemen" : "Spreek je vraag in"}
                title="Spreek je vraag in (spraakherkenning via de browser)"
                className={
                  "shrink-0 h-10 w-10 rounded-lg flex items-center justify-center text-lg transition-colors disabled:opacity-40 " +
                  (listening
                    ? "bg-red-600 text-white animate-pulse"
                    : "bg-gray-100 hover:bg-gray-200 text-gray-700")
                }
              >
                🎤
              </button>
            )}
            <textarea
              className="flex-1 resize-none border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500 max-h-28"
              rows={1}
              placeholder={listening ? "Aan het luisteren…" : "Typ je vraag…"}
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={onKeyDown}
              disabled={busy}
            />
            <button
              onClick={send}
              disabled={busy || !input.trim()}
              className="bg-blue-700 hover:bg-blue-800 disabled:opacity-40 text-white font-semibold rounded-lg px-4 py-2 text-sm transition-colors"
            >
              Stuur
            </button>
          </div>
        </div>
      )}
    </>
  );
}

function Bubble({
  role,
  content,
  typing,
}: {
  role: ChatMsg["role"];
  content: string;
  typing?: boolean;
}) {
  const isUser = role === "user";
  return (
    <div className={isUser ? "flex justify-end" : "flex justify-start"}>
      <div
        className={
          "max-w-[85%] rounded-2xl px-3 py-2 text-sm whitespace-pre-wrap " +
          (isUser
            ? "bg-blue-700 text-white rounded-br-sm"
            : "bg-white border border-gray-200 text-gray-800 rounded-bl-sm")
        }
      >
        {typing ? <span className="text-gray-400">Raakje typt…</span> : content}
      </div>
    </div>
  );
}
