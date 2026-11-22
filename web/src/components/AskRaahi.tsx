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
  clearOnAsk = false,
  onAsk,
}: {
  initialText?: string;
  isLoading: boolean;
  compact?: boolean;
  /** In the conversation the words move onto the trail, so the box empties for the next turn. */
  clearOnAsk?: boolean;
  onAsk: (text: string) => void;
}) {
  const { t, lang } = useI18n();
  const [text, setText] = useState(initialText);
  const [voice, setVoice] = useState<VoiceState>("idle");
  const [voiceError, setVoiceError] = useState<VoiceErrorKind>();
  const [voiceDetail, setVoiceDetail] = useState<string>();
  const [focused, setFocused] = useState(false);
  const recording = useRef<Recording | null>(null);
  const browserStop = useRef<(() => void) | null>(null);
  const stopTapped = useRef(false);
  // Which way still works on this device: the browser's recognizer first, the server's Whisper after.
  const browserVoice = useRef(true);
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
    if (clean && !isLoading) {
      onAsk(clean);
      if (clearOnAsk) setText("");
    }
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
    setVoiceDetail(error instanceof VoiceError ? error.detail : String(error));
  }

  // Loudness drives the mic ring (a CSS variable, so React doesn't re-render 10 times a second).
  const setLevel = (level: number) => box.current?.style.setProperty("--level", level.toFixed(3));

  /** The server's way: record, then Whisper inside the app. */
  async function recordForServer() {
    try {
      recording.current = await startRecording(setLevel, () => void finishRecording());
      setVoice("listening");
    } catch (error) {
      failed(error);
    }
  }

  async function finishRecording() {
    const current = recording.current;
    recording.current = null;
    if (!current) return;
    setVoice("transcribing");
    try {
      const pcm = await current.stop();
      heard(await transcribe(pcm, lang, API_BASE));
    } catch (error) {
      if (error instanceof VoiceError && error.kind === "unavailable") serverVoice.current = false;
      failed(error);
    }
  }

  /**
   * The browser's way, with the words appearing in the box as they are recognised. The microphone is recorded
   * at the same time, so when the browser hears nothing (its service is silent, says "no-speech", or ends with
   * no words) the same recording goes to the server's Whisper: the person never has to say it twice.
   */
  function recognizeHere() {
    const before = text;
    let browserActive = true;
    let backup: Recording | null = null;
    let backupStarting: Promise<Recording | null> = Promise.resolve(null);
    let doneSpeaking = false;
    // Started synchronously, inside the tap (Safari needs that for its recognizer).
    const run = recognizeInBrowser(lang, (words) => setText(words));
    browserStop.current = run.stop;
    setVoice("listening");
    if (serverVoice.current && canRecord()) {
      backupStarting = startRecording(setLevel, () => {
        // The person stopped speaking. If the browser has written nothing by now, stop waiting for it.
        doneSpeaking = true;
        if (browserActive) run.stop();
        else if (recording.current === backup) void finishRecording();
      }).then(
        (r) => (backup = r),
        () => null, // no backup recording: the browser's recognizer still works on its own
      );
    }
    run.result
      .then(
        async (said) => {
          browserActive = false;
          (await backupStarting)?.cancel();
          heard(said);
        },
        async (error) => {
          browserActive = false;
          setText(before);
          const recorded = await backupStarting;
          if (error instanceof VoiceError && error.kind === "unavailable") browserVoice.current = false;
          if (!recorded) return failed(error);
          // The browser heard nothing: let Whisper read what was recorded. If the browser gave up while the
          // person may still be talking, keep listening until they pause (or tap the mic), then send it.
          recording.current = recorded;
          if (doneSpeaking || stopTapped.current) void finishRecording();
        },
      )
      .finally(() => {
        browserStop.current = null;
      });
  }

  async function toggleVoice() {
    setVoiceError(undefined);
    setVoiceDetail(undefined);
    if (voice === "listening") {
      stopTapped.current = true;
      if (recording.current) void finishRecording();
      else browserStop.current?.();
      return;
    }
    if (voice === "transcribing") return;
    stopTapped.current = false;
    if (browserVoice.current && browserRecognition()) return recognizeHere();
    if (serverVoice.current && canRecord()) return recordForServer();
    failed(new VoiceError("unavailable", "no way to recognise speech in this browser"));
  }

  const voiceMessage = voiceError
    ? {
        unsupported: t.voiceUnsupported,
        denied: t.voiceDenied,
        "no-mic": t.voiceNoMic,
        "no-speech": t.voiceNoSpeech,
        unavailable: t.voiceUnavailable,
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
          {!listening && voice === "idle" && voiceMessage && voiceDetail && <small> ({voiceDetail})</small>}
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
