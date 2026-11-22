import { ArrowUp, LoaderCircle, Mic } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { useI18n } from "../i18n";

/* Browsers name the speech API differently; the typing here is just enough for one-shot dictation. */
interface Recognition {
  lang: string;
  interimResults: boolean;
  continuous: boolean;
  onresult: ((event: { results: ArrayLike<ArrayLike<{ transcript: string }>> }) => void) | null;
  onend: (() => void) | null;
  onerror: (() => void) | null;
  start: () => void;
  stop: () => void;
}
type RecognitionCtor = new () => Recognition;

function speechApi(): RecognitionCtor | undefined {
  const w = window as unknown as { SpeechRecognition?: RecognitionCtor; webkitSpeechRecognition?: RecognitionCtor };
  return w.SpeechRecognition ?? w.webkitSpeechRecognition;
}

/** Types out example requests one letter at a time while the box is empty. */
function useTypedPlaceholder(examples: string[], active: boolean) {
  const [text, setText] = useState("");
  useEffect(() => {
    if (!active || examples.length === 0) return;
    const reduce = window.matchMedia?.("(prefers-reduced-motion: reduce)").matches;
    if (reduce) {
      setText(examples[0]);
      return;
    }
    let example = 0;
    let index = 0;
    let deleting = false;
    let timer = 0;
    const tick = () => {
      const full = examples[example];
      if (!deleting) {
        index += 1;
        setText(full.slice(0, index));
        if (index >= full.length) {
          deleting = true;
          timer = window.setTimeout(tick, 2200);
          return;
        }
        timer = window.setTimeout(tick, 42 + Math.random() * 50);
      } else {
        index -= 2;
        setText(full.slice(0, Math.max(0, index)));
        if (index <= 0) {
          deleting = false;
          example = (example + 1) % examples.length;
          timer = window.setTimeout(tick, 420);
          return;
        }
        timer = window.setTimeout(tick, 18);
      }
    };
    timer = window.setTimeout(tick, 500);
    return () => window.clearTimeout(timer);
  }, [active, examples]);
  return text;
}

/**
 * The one place to ask: a sentence in the person's own words, typed or spoken
 * (English or Hindi). Raahi reads it on submit; nothing is sent while typing.
 */
export function AskRaahi({
  initialText = "",
  isLoading,
  compact = false,
  onAsk,
}: {
  initialText?: string;
  isLoading: boolean;
  compact?: boolean;
  onAsk: (text: string) => void;
}) {
  const { t, lang } = useI18n();
  const [text, setText] = useState(initialText);
  const [listening, setListening] = useState(false);
  const [focused, setFocused] = useState(false);
  const recognition = useRef<Recognition | null>(null);
  const area = useRef<HTMLTextAreaElement>(null);
  const placeholder = useTypedPlaceholder(t.askExamples, !text && !focused);
  const canSpeak = typeof window !== "undefined" && Boolean(speechApi());

  useEffect(() => setText(initialText), [initialText]);

  // Grow with the text, up to a few lines.
  useEffect(() => {
    const el = area.current;
    if (!el) return;
    el.style.height = "auto";
    el.style.height = `${Math.min(el.scrollHeight, 180)}px`;
  }, [text, compact]);

  function submit(value = text) {
    const clean = value.trim();
    if (clean && !isLoading) onAsk(clean);
  }

  function toggleVoice() {
    const Api = speechApi();
    if (!Api) return;
    if (listening) {
      recognition.current?.stop();
      return;
    }
    const r = new Api();
    r.lang = lang === "hi" ? "hi-IN" : "en-IN";
    r.interimResults = false;
    r.continuous = false;
    r.onresult = (event) => {
      const said = event.results[0]?.[0]?.transcript ?? "";
      setText(said);
      submit(said);
    };
    r.onend = () => setListening(false);
    r.onerror = () => setListening(false);
    recognition.current = r;
    r.start();
    setListening(true);
  }

  return (
    <div className={`ask ${compact ? "ask--compact" : ""}`}>
      <form
        className={`ask-box ${listening ? "is-listening" : ""}`}
        role="search"
        onSubmit={(event) => {
          event.preventDefault();
          submit();
        }}
      >
        <label htmlFor="ask-input" className="sr-only">
          {t.askLabel}
        </label>
        <textarea
          id="ask-input"
          ref={area}
          rows={1}
          value={text}
          maxLength={600}
          onChange={(event) => setText(event.target.value)}
          onFocus={() => setFocused(true)}
          onBlur={() => setFocused(false)}
          onKeyDown={(event) => {
            if (event.key === "Enter" && !event.shiftKey) {
              event.preventDefault();
              submit();
            }
          }}
          placeholder={focused ? t.askExamples[0] : placeholder}
          enterKeyHint="send"
          autoComplete="off"
          lang={lang}
        />
        <div className="ask-tools">
          {canSpeak && (
            <button
              type="button"
              className="ask-mic"
              onClick={toggleVoice}
              aria-pressed={listening}
              aria-label={listening ? t.askListening : t.askListen}
              title={listening ? t.askListening : t.askListen}
            >
              <Mic size={20} aria-hidden="true" />
            </button>
          )}
          <button className="ask-send" type="submit" disabled={isLoading || !text.trim()} aria-label={t.askSend}>
            {isLoading ? <LoaderCircle className="spin" size={20} /> : <ArrowUp size={20} />}
            {!compact && <span>{t.askSend}</span>}
          </button>
        </div>
        {listening && <span className="ask-listening" aria-live="polite">{t.askListening}</span>}
      </form>
      {!compact && (
        <div className="ask-try">
          <span>{t.askTry}</span>
          <ul>
            {t.askExamples.slice(0, 3).map((example, index) => (
              <li key={example} style={{ "--i": index } as React.CSSProperties}>
                <button
                  type="button"
                  onClick={() => {
                    setText(example);
                    submit(example);
                  }}
                >
                  {example}
                </button>
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}
