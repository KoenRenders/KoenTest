"use client";
import { useEffect, useRef, useState } from "react";
import { streamChat, type ChatMsg } from "@/lib/api";

// Zwevende chatbot 'Raakje' (#205). Tekst-first; de microfoon-knop (Web Speech
// API) komt als progressive enhancement in een latere fase. De LLM zit achter
// het backend-laagje — deze widget weet niets van de provider.

const WELCOME =
  "Hallo, ik ben Raakje! 👋 Stel me gerust een vraag over Raak Millegem, onze activiteiten of het lidmaatschap. Ik kan ook je vraag of idee doorgeven aan het bestuur.";

export default function ChatWidget() {
  const [open, setOpen] = useState(false);
  const [messages, setMessages] = useState<ChatMsg[]>([]);
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const scrollRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight });
  }, [messages, open]);

  async function send() {
    const text = input.trim();
    if (!text || busy) return;

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
            <textarea
              className="flex-1 resize-none border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500 max-h-28"
              rows={1}
              placeholder="Typ je vraag…"
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
