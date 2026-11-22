import { ArrowUp, LoaderCircle, Mic, Square } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { useI18n } from "../i18n";
import { API_BASE, USE_DEMO } from "../lib/api";
import {
  browserRecognition,
  canRecord,
  recognizeInBrowser,
  startRecording,
  transcribe,
  VoiceError,
  type Recording,
  type VoiceErrorKind,
} from "../lib/voice";

type VoiceState = "idle" | "listening" | "transcribing";

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
  const [voice, setVoice] = useState<VoiceState>("idle");
  const [voiceError, setVoiceError] = useState<VoiceErrorKind>();
  const [focused, setFocused] = useState(false);
  const recording = useRef<Recording | null>(null);
  const browserStop = useRef<(() => void) | null>(null);
  // After one "server can't transcribe" answer, go straight to the browser's recognizer.
  const serverVoice = useRef(!USE_DEMO);
  const box = useRef<HTMLFormElement>(null);
  const area = useRef<HTMLTextAreaElement>(null);
  const placeholder = useTypedPlaceholder(t.askExamples, !text && !focused && voice === "idle");
  const canSpeak = typeof window !== "undefined" && (canRecord() || Boolean(browserRecognition()));
  const listening = voice === "listening";

  useEffect(() => () => recording.current?.cancel(), []);

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

  /** Show the heard words in the box, then ask: the person sees exactly what Raahi will read. */
  function heard(said: string) {
    setText(said);
    setVoice("idle");
    submit(said);
  }

  function failed(error: unknown) {
    setVoice("idle");
    setVoiceError(error instanceof VoiceError ? error.kind : "failed");
  }

  // Loudness drives the mic ring (a CSS variable, so React doesn't re-render 10 times a second).
  const setLevel = (level: number) => box.current?.style.setProperty("--level", level.toFixed(3));

  async function finishRecording() {
    const current = recording.current;
    recording.current = null;
    if (!current) return;
    setVoice("transcribing");
    try {
      const pcm = await current.stop();
      heard(await transcribe(pcm, lang, API_BASE));
    } catch (error) {
      if (error instanceof VoiceError && error.kind === "unavailable" && browserRecognition()) {
        serverVoice.current = false; // this server can't transcribe: use the browser's recognizer from now on
        setVoice("idle");
        setVoiceError("unavailable");
        return;
      }
      failed(error);
    }
  }

  async function toggleVoice() {
    setVoiceError(undefined);
    if (voice === "listening") {
      if (recording.current) void finishRecording();
      else browserStop.current?.();
      return;
    }
    if (voice === "transcribing") return;
    if (serverVoice.current && canRecord()) {
      try {
        recording.current = await startRecording(setLevel, () => void finishRecording());
        setVoice("listening");
      } catch (error) {
        failed(error);
      }
      return;
    }
    // Fallback: the browser's own recognizer (demo build, or a server without voice).
    const run = recognizeInBrowser(lang);
    browserStop.current = run.stop;
    setVoice("listening");
    run.result.then(heard, failed).finally(() => {
      browserStop.current = null;
    });
  }

  const voiceMessage = voiceError
    ? {
        unsupported: t.voiceUnsupported,
        denied: t.voiceDenied,
        "no-mic": t.voiceNoMic,
        "no-speech": t.voiceNoSpeech,
        unavailable: browserRecognition() ? t.voiceTryAgain : t.voiceUnavailable,
        failed: t.voiceFailed,
      }[voiceError]
    : null;

  return (
    <div className={`ask ${compact ? "ask--compact" : ""}`}>
      <form
        ref={box}
        className={`ask-box ${listening ? "is-listening" : ""} ${voice === "transcribing" ? "is-transcribing" : ""}`}
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
          placeholder={voice !== "idle" ? "" : focused ? t.askExamples[0] : placeholder}
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
              disabled={voice === "transcribing"}
              aria-label={listening ? t.voiceStop : t.askListen}
              title={listening ? t.voiceStop : t.askListen}
            >
              {voice === "transcribing" ? (
                <LoaderCircle className="spin" size={20} aria-hidden="true" />
              ) : listening ? (
                <Square size={16} fill="currentColor" aria-hidden="true" />
              ) : (
                <Mic size={20} aria-hidden="true" />
              )}
            </button>
          )}
          <button className="ask-send" type="submit" disabled={isLoading || !text.trim()} aria-label={t.askSend}>
            {isLoading ? <LoaderCircle className="spin" size={20} /> : <ArrowUp size={20} />}
            {!compact && <span>{t.askSend}</span>}
          </button>
        </div>
        <span className={`ask-voice-status ${voiceMessage ? "is-error" : ""}`} aria-live="polite">
          {listening ? t.askListening : voice === "transcribing" ? t.voiceTranscribing : voiceMessage}
        </span>
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
