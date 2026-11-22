/**
 * Voice input, two ways, used together:
 *
 * 1. The browser's own speech recognition (Chrome, Edge, Safari): it shows the words live as the person
 *    speaks, so they can see they are being heard, and handles Hindi (hi-IN) and Indian English (en-IN) well.
 * 2. Sprout's way: the microphone is recorded with the Web Audio API, resampled to 16 kHz mono 16-bit PCM,
 *    and sent to /api/transcribe (Whisper inside the app). Whatever was recorded is sent (Whisper decides
 *    whether there were words), so a quiet microphone is never rejected here.
 *
 * Either way the person decides when they are done: listening carries on through pauses until they tap the
 * mic again (60 s safety limit). The program never ends their turn because they paused.
 *
 * Where the browser has a recognizer, the page runs both at once: if the recognizer writes nothing (its
 * service is silent, reports "no-speech", or ends empty), the recording of the same words goes to Whisper,
 * so the person never has to repeat themselves. Without a recognizer (Firefox) only the recording is used.
 *
 * Every failure carries what went wrong (`detail`), so the page can say it.
 */

const TARGET_RATE = 16000;
// The person decides when they are done (they tap the mic again); this is only a safety limit.
const MAX_SECONDS = 60;
// How long the browser's recognizer may stay silent (no words at all) before we try the server instead.
const BROWSER_SILENT_MS = 7000;

export type VoiceErrorKind = "unsupported" | "denied" | "no-mic" | "no-speech" | "unavailable" | "failed";

export class VoiceError extends Error {
  kind: VoiceErrorKind;
  detail?: string;
  constructor(kind: VoiceErrorKind, detail?: string) {
    super(detail ? `${kind}: ${detail}` : kind);
    this.kind = kind;
    this.detail = detail;
  }
}

export interface Recording {
  /** Stop now and get the audio as 16 kHz mono 16-bit PCM. */
  stop: () => Promise<ArrayBuffer>;
  cancel: () => void;
}

export function canRecord() {
  return typeof navigator !== "undefined" && Boolean(navigator.mediaDevices?.getUserMedia) && typeof AudioContext !== "undefined";
}

function toPcm16(chunks: Float32Array[], rate: number): ArrayBuffer {
  const total = chunks.reduce((n, c) => n + c.length, 0);
  const ratio = rate / TARGET_RATE;
  const out = new Int16Array(Math.floor(total / ratio));
  // Average the source samples that fall into each output sample (a cheap low-pass while downsampling).
  let chunk = 0;
  let offset = 0;
  for (let i = 0; i < out.length; i += 1) {
    const end = Math.floor((i + 1) * ratio);
    let sum = 0;
    let count = 0;
    for (let k = Math.floor(i * ratio); k < end; k += 1) {
      while (chunk < chunks.length && k - offset >= chunks[chunk].length) {
        offset += chunks[chunk].length;
        chunk += 1;
      }
      if (chunk >= chunks.length) break;
      sum += chunks[chunk][k - offset];
      count += 1;
    }
    const v = count ? sum / count : 0;
    out[i] = Math.max(-1, Math.min(1, v)) * 0x7fff;
  }
  return out.buffer;
}

/**
 * Start recording. `onLevel` gets 0-1 loudness. Recording goes on through pauses until the person taps stop;
 * `onAutoStop` fires only at the safety limit (MAX_SECONDS).
 */
export async function startRecording(onLevel: (level: number) => void, onAutoStop: () => void): Promise<Recording> {
  if (!canRecord()) throw new VoiceError("unsupported");
  // Created before the permission prompt, while the tap still counts as a user gesture (Safari needs that).
  const context = new AudioContext();
  let stream: MediaStream;
  try {
    stream = await navigator.mediaDevices.getUserMedia({
      audio: { channelCount: 1, echoCancellation: true, noiseSuppression: true, autoGainControl: true },
    });
  } catch (error) {
    void context.close();
    const name = (error as DOMException)?.name;
    // "unavailable" is kept for the server: a microphone problem is the person's to fix, so it says so.
    throw new VoiceError(name === "NotAllowedError" || name === "SecurityError" ? "denied" : "no-mic", name);
  }
  await context.resume();
  const source = context.createMediaStreamSource(stream);
  // ScriptProcessor is deprecated but works in every browser without a separate worklet file.
  const processor = context.createScriptProcessor(4096, 1, 1);
  const chunks: Float32Array[] = [];
  const started = performance.now();
  let ended = false;

  processor.onaudioprocess = (event) => {
    if (ended) return;
    const data = new Float32Array(event.inputBuffer.getChannelData(0));
    chunks.push(data);
    let sum = 0;
    for (let i = 0; i < data.length; i += 1) sum += data[i] * data[i];
    const rms = Math.sqrt(sum / data.length);
    onLevel(Math.min(1, rms * 9));
    // Pauses never end the recording: only the person's tap, or the safety limit.
    if (performance.now() - started > MAX_SECONDS * 1000) onAutoStop();
  };
  source.connect(processor);
  processor.connect(context.destination);

  const close = () => {
    ended = true;
    processor.disconnect();
    source.disconnect();
    stream.getTracks().forEach((track) => track.stop());
    void context.close();
    onLevel(0);
  };
  return {
    stop: async () => {
      close();
      const seconds = chunks.reduce((n, c) => n + c.length, 0) / context.sampleRate;
      if (seconds < 0.6) throw new VoiceError("no-speech", "too short");
      return toPcm16(chunks, context.sampleRate);
    },
    cancel: close,
  };
}

/** Send the recording to the server's Whisper. Throws VoiceError("unavailable") when the server can't. */
export async function transcribe(pcm: ArrayBuffer, lang: "en" | "hi", apiBase = ""): Promise<string> {
  let response: Response;
  try {
    response = await fetch(`${apiBase}/api/transcribe?lang=${lang}`, {
      method: "POST",
      headers: { "Content-Type": "application/octet-stream" },
      body: pcm,
    });
  } catch {
    throw new VoiceError("unavailable");
  }
  const body = (await response.json().catch(() => ({}))) as {
    transcript?: string;
    detail?: { message?: string } | string;
  };
  const why = typeof body.detail === "string" ? body.detail : body.detail?.message;
  if (response.status === 503 || response.status === 404) throw new VoiceError("unavailable", why ?? `HTTP ${response.status}`);
  if (!response.ok) throw new VoiceError("failed", why ?? `HTTP ${response.status}`);
  const text = (body.transcript ?? "").trim();
  if (!text) throw new VoiceError("no-speech", "the server heard no words");
  return text;
}

/* ---- the browser's own speech recognition: live words; the recording above backs it up ---- */

interface BrowserRecognition {
  lang: string;
  interimResults: boolean;
  continuous: boolean;
  onresult: ((event: { results: ArrayLike<ArrayLike<{ transcript: string }>> }) => void) | null;
  onend: (() => void) | null;
  onerror: ((event: { error?: string }) => void) | null;
  start: () => void;
  stop: () => void;
  abort?: () => void;
}
type RecognitionCtor = new () => BrowserRecognition;

export function browserRecognition(): RecognitionCtor | undefined {
  if (typeof window === "undefined") return undefined;
  const w = window as unknown as { SpeechRecognition?: RecognitionCtor; webkitSpeechRecognition?: RecognitionCtor };
  return w.SpeechRecognition ?? w.webkitSpeechRecognition;
}

/**
 * One utterance through the browser's recognizer (audio goes to the browser vendor's service).
 * `onWords` gets the words so far, live, so the box fills in as the person speaks.
 */
export function recognizeInBrowser(
  lang: "en" | "hi",
  onWords: (text: string) => void = () => undefined,
): { result: Promise<string>; stop: () => void } {
  const Api = browserRecognition();
  if (!Api) return { result: Promise.reject(new VoiceError("unsupported")), stop: () => undefined };
  const r = new Api();
  r.lang = lang === "hi" ? "hi-IN" : "en-IN";
  r.interimResults = true;
  // Keep listening through pauses: the person taps the mic when they are done.
  r.continuous = true;
  let watchdog = 0;
  let stopped = false;
  const result = new Promise<string>((resolve, reject) => {
    let kept = ""; // words from earlier rounds, when the browser ended a round by itself and was restarted
    let said = "";
    let failed = false;
    // Some browsers (Brave, Chromium builds without Google's speech service) start the recognizer and then
    // never answer: no words and no error. If nothing is heard back in time, give up and let the page use the
    // recording it is making alongside (the server's Whisper reads it when the person taps stop).
    watchdog = window.setTimeout(() => {
      if (said.trim() || stopped) return;
      failed = true;
      (r.abort ?? r.stop).call(r);
      reject(new VoiceError("unavailable", "the browser's speech service did not answer"));
    }, BROWSER_SILENT_MS);
    r.onresult = (event) => {
      const round = Array.from(event.results as ArrayLike<ArrayLike<{ transcript: string }>>)
        .map((alternatives) => alternatives[0]?.transcript ?? "")
        .join("");
      said = [kept, round].filter((part) => part.trim()).join(" ").trim();
      onWords(said);
    };
    r.onerror = (event) => {
      const code = event.error ?? "unknown";
      // A pause ("no-speech") or a restart ("aborted") is not a failure while the person is still talking.
      if (!stopped && (code === "no-speech" || code === "aborted")) return;
      window.clearTimeout(watchdog);
      if (failed) return;
      failed = true;
      reject(
        new VoiceError(
          code === "not-allowed" || code === "service-not-allowed"
            ? "denied"
            : code === "no-speech"
              ? "no-speech"
              : code === "audio-capture"
                ? "no-mic"
                : "unavailable", // network, language-not-supported...: use the recording instead
          code,
        ),
      );
    };
    r.onend = () => {
      if (failed) return;
      if (!stopped) {
        // The browser ended the round by itself (a pause, its own time limit): carry on listening.
        kept = said;
        try {
          r.start();
          return;
        } catch {
          /* cannot restart: finish with what was heard */
        }
      }
      window.clearTimeout(watchdog);
      if (said.trim()) resolve(said.trim());
      else reject(new VoiceError("no-speech", "no words recognised"));
    };
  });
  try {
    r.start();
  } catch (error) {
    return { result: Promise.reject(new VoiceError("unavailable", String(error))), stop: () => undefined };
  }
  return {
    result,
    stop: () => {
      stopped = true;
      r.stop();
    },
  };
}
