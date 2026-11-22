/**
 * Voice input, after Sprout (record in the browser, transcribe on the server):
 * the microphone is recorded with the Web Audio API, resampled to 16 kHz mono
 * 16-bit PCM here, and sent to /api/transcribe, where Whisper runs inside the
 * app (so speech stays on Databricks). Works wherever getUserMedia does
 * (Chrome, Edge, Safari, Firefox), unlike the browser's own speech API.
 *
 * Recording stops when the person taps again, after ~1.4 s of silence once
 * they have spoken, or at 20 s. The level callback drives the mic animation.
 * Where the server can't transcribe (demo build, voice off), the browser's
 * own speech recognition is used if it exists.
 */

const TARGET_RATE = 16000;
const MAX_SECONDS = 20;
const SILENCE_MS = 1400;
const SPEECH_RMS = 0.025;

export type VoiceErrorKind = "unsupported" | "denied" | "no-mic" | "no-speech" | "unavailable" | "failed";

export class VoiceError extends Error {
  kind: VoiceErrorKind;
  constructor(kind: VoiceErrorKind) {
    super(kind);
    this.kind = kind;
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

/** Start recording. `onLevel` gets 0-1 loudness; `onAutoStop` fires when silence or the time limit ends it. */
export async function startRecording(onLevel: (level: number) => void, onAutoStop: () => void): Promise<Recording> {
  if (!canRecord()) throw new VoiceError("unsupported");
  let stream: MediaStream;
  try {
    stream = await navigator.mediaDevices.getUserMedia({
      audio: { channelCount: 1, echoCancellation: true, noiseSuppression: true, autoGainControl: true },
    });
  } catch (error) {
    const name = (error as DOMException)?.name;
    // "unavailable" is kept for the server: a microphone problem is the person's to fix, so it says so.
    throw new VoiceError(name === "NotAllowedError" || name === "SecurityError" ? "denied" : "no-mic");
  }
  const context = new AudioContext();
  await context.resume();
  const source = context.createMediaStreamSource(stream);
  // ScriptProcessor is deprecated but works in every browser without a separate worklet file.
  const processor = context.createScriptProcessor(4096, 1, 1);
  const chunks: Float32Array[] = [];
  const started = performance.now();
  let spoke = false;
  let lastVoice = started;
  let ended = false;

  processor.onaudioprocess = (event) => {
    if (ended) return;
    const data = new Float32Array(event.inputBuffer.getChannelData(0));
    chunks.push(data);
    let sum = 0;
    for (let i = 0; i < data.length; i += 1) sum += data[i] * data[i];
    const rms = Math.sqrt(sum / data.length);
    onLevel(Math.min(1, rms * 9));
    const now = performance.now();
    if (rms > SPEECH_RMS) {
      spoke = true;
      lastVoice = now;
    }
    if ((spoke && now - lastVoice > SILENCE_MS) || now - started > MAX_SECONDS * 1000) onAutoStop();
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
      if (!spoke) throw new VoiceError("no-speech");
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
  if (response.status === 503 || response.status === 404) throw new VoiceError("unavailable");
  if (!response.ok) throw new VoiceError("failed");
  const body = (await response.json()) as { transcript?: string };
  const text = (body.transcript ?? "").trim();
  if (!text) throw new VoiceError("no-speech");
  return text;
}

/* ---- the browser's own speech recognition: the fallback when the server can't transcribe ---- */

interface BrowserRecognition {
  lang: string;
  interimResults: boolean;
  continuous: boolean;
  onresult: ((event: { results: ArrayLike<ArrayLike<{ transcript: string }>> }) => void) | null;
  onend: (() => void) | null;
  onerror: ((event: { error?: string }) => void) | null;
  start: () => void;
  stop: () => void;
}
type RecognitionCtor = new () => BrowserRecognition;

export function browserRecognition(): RecognitionCtor | undefined {
  if (typeof window === "undefined") return undefined;
  const w = window as unknown as { SpeechRecognition?: RecognitionCtor; webkitSpeechRecognition?: RecognitionCtor };
  return w.SpeechRecognition ?? w.webkitSpeechRecognition;
}

/** One utterance through the browser's recognizer (sends audio to the browser vendor). */
export function recognizeInBrowser(lang: "en" | "hi"): { result: Promise<string>; stop: () => void } {
  const Api = browserRecognition();
  if (!Api) return { result: Promise.reject(new VoiceError("unsupported")), stop: () => undefined };
  const r = new Api();
  r.lang = lang === "hi" ? "hi-IN" : "en-IN";
  r.interimResults = false;
  r.continuous = false;
  const result = new Promise<string>((resolve, reject) => {
    let said = "";
    r.onresult = (event) => {
      said = event.results[0]?.[0]?.transcript ?? "";
    };
    r.onerror = (event) =>
      reject(
        new VoiceError(
          event.error === "not-allowed" || event.error === "service-not-allowed"
            ? "denied"
            : event.error === "no-speech"
              ? "no-speech"
              : "unavailable",
        ),
      );
    r.onend = () => (said.trim() ? resolve(said.trim()) : reject(new VoiceError("no-speech")));
  });
  r.start();
  return { result, stop: () => r.stop() };
}
