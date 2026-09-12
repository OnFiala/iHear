export type CapturedAudio = {
  blob: Blob;
  capture: {
    sampleRate: number;
    preSeconds: number;
    postSeconds: number;
    trackSettings: MediaTrackSettings;
    sourceLabel: string;
    routing: "unknown";
    interrupted: boolean;
  };
};
export function encodeWav(samples: Float32Array, sampleRate: number): Blob {
  const buffer = new ArrayBuffer(44 + samples.length * 2),
    v = new DataView(buffer);
  const string = (offset: number, text: string) => {
    for (let i = 0; i < text.length; i++)
      v.setUint8(offset + i, text.charCodeAt(i));
  };
  string(0, "RIFF");
  v.setUint32(4, buffer.byteLength - 8, true);
  string(8, "WAVE");
  string(12, "fmt ");
  v.setUint32(16, 16, true);
  v.setUint16(20, 1, true);
  v.setUint16(22, 1, true);
  v.setUint32(24, sampleRate, true);
  v.setUint32(28, sampleRate * 2, true);
  v.setUint16(32, 2, true);
  v.setUint16(34, 16, true);
  string(36, "data");
  v.setUint32(40, samples.length * 2, true);
  for (let i = 0; i < samples.length; i++) {
    const x = Math.max(-1, Math.min(1, samples[i]));
    v.setInt16(44 + i * 2, x < 0 ? x * 32768 : x * 32767, true);
  }
  return new Blob([buffer], { type: "audio/wav" });
}

export type MicrophoneAvailability = "ready" | "gesture-required";

export class MicrophoneCancelledError extends Error {
  constructor() {
    super("Microphone setup was cancelled.");
    this.name = "MicrophoneCancelledError";
  }
}

type EnableAttempt = {
  generation: number;
  promise: Promise<MicrophoneAvailability>;
  context?: AudioContext;
  stream?: MediaStream;
};

export class Microphone {
  private context?: AudioContext;
  private stream?: MediaStream;
  private node?: AudioWorkletNode;
  private generation = 0;
  private enabling?: EnableAttempt;
  private captureStarting = false;
  private pending?: {
    resolve: (value: CapturedAudio) => void;
    reject: (error: Error) => void;
    timer: ReturnType<typeof setTimeout>;
  };
  constructor(
    private onInterrupted: (
      state: "gesture-required" | "interrupted",
    ) => void,
  ) {}

  enable(): Promise<MicrophoneAvailability> {
    if (
      this.context &&
      this.context.state !== "closed" &&
      this.stream &&
      this.node
    )
      return Promise.resolve(
        this.context.state === "running" ? "ready" : "gesture-required",
      );
    if (this.enabling) return this.enabling.promise;
    if (!navigator.mediaDevices?.getUserMedia)
      return Promise.reject(
        new Error("A microphone needs a secure HTTPS connection or localhost."),
      );
    const attempt = {
      generation: this.generation,
      promise: undefined as unknown as Promise<MicrophoneAvailability>,
    } satisfies EnableAttempt;
    attempt.promise = this.build(attempt).finally(() => {
      if (this.enabling === attempt) this.enabling = undefined;
    });
    this.enabling = attempt;
    return attempt.promise;
  }

  private cancelled(attempt: EnableAttempt): boolean {
    return attempt.generation !== this.generation;
  }

  private async build(
    attempt: EnableAttempt,
  ): Promise<MicrophoneAvailability> {
    const context = new AudioContext();
    attempt.context = context;
    let stream: MediaStream | undefined;
    try {
      // Autoplay may leave resume pending until a listening-button gesture.
      // Finish setup so that gesture remains available in the interface.
      if (context.state === "suspended")
        void context.resume().catch(() => {});
      if (this.cancelled(attempt)) throw new MicrophoneCancelledError();
      stream = await navigator.mediaDevices.getUserMedia({
        audio: {
          echoCancellation: false,
          noiseSuppression: false,
          autoGainControl: false,
          channelCount: 1,
        },
        video: false,
      });
      attempt.stream = stream;
      if (this.cancelled(attempt)) throw new MicrophoneCancelledError();
      await context.audioWorklet.addModule("/pcm-worklet.js");
      if (this.cancelled(attempt)) throw new MicrophoneCancelledError();
      const node = new AudioWorkletNode(context, "pcm-recorder");
      context.createMediaStreamSource(stream).connect(node);
      node.connect(context.destination);
      const track = stream.getAudioTracks()[0];
      if (!track) throw new Error("No microphone audio track was available.");

      this.context = context;
      this.stream = stream;
      this.node = node;
      attempt.context = undefined;
      attempt.stream = undefined;

      const interrupted = () => {
        if (this.stream !== stream) return;
        this.stop();
        this.onInterrupted("interrupted");
      };
      track.addEventListener("ended", interrupted);
      track.addEventListener("mute", interrupted);
      context.onstatechange = () => {
        if (this.context !== context || context.state === "closed") return;
        if (
          context.state === "suspended" ||
          context.state === ("interrupted" as AudioContextState)
        ) {
          if (this.pending) interrupted();
          else this.onInterrupted("gesture-required");
        }
      };
      node.port.onmessage = ({ data }) => {
        if (data.type === "complete" && this.pending) {
          const pending = this.pending;
          this.pending = undefined;
          clearTimeout(pending.timer);
          pending.resolve({
            blob: encodeWav(data.samples, context.sampleRate),
            capture: {
              sampleRate: context.sampleRate,
              preSeconds: data.preSeconds,
              postSeconds: data.postSeconds,
              trackSettings: track.getSettings(),
              sourceLabel: track.label || "Unknown microphone",
              routing: "unknown",
              interrupted: false,
            },
          });
        }
      };
      return context.state === "running" ? "ready" : "gesture-required";
    } catch (e) {
      stream?.getTracks().forEach((track) => track.stop());
      if (context.state !== "closed") await context.close().catch(() => {});
      if (e instanceof MicrophoneCancelledError || this.cancelled(attempt))
        throw new MicrophoneCancelledError();
      if (e instanceof DOMException) {
        if (e.name === "NotAllowedError")
          throw new Error(
            "Microphone permission was denied. Allow it in your browser settings, then try again.",
          );
        if (e.name === "NotFoundError")
          throw new Error(
            "No microphone was found. Check your device and try again.",
          );
      }
      throw e;
    }
  }

  capture(): Promise<CapturedAudio> {
    if (this.captureStarting || this.pending)
      return Promise.reject(new Error("A moment is already recording."));
    this.captureStarting = true;
    return this.beginCapture().finally(() => {
      this.captureStarting = false;
    });
  }

  private async beginCapture(): Promise<CapturedAudio> {
    const context = this.context;
    const node = this.node;
    if (!node || !context || !this.stream)
      return Promise.reject(
        new Error("Enable the microphone before saving a moment."),
      );
    if (context.state !== "running") {
      await context.resume().catch(() => {});
      const resumedState = context.state as AudioContextState;
      if (resumedState !== "running") {
        this.onInterrupted("gesture-required");
        throw new Error(
          "The microphone is paused. Tap a listening button again to resume it.",
        );
      }
    }
    return new Promise((resolve, reject) => {
      this.pending = {
        resolve,
        reject,
        timer: setTimeout(() => {
          this.stop();
          this.onInterrupted("interrupted");
        }, 15000),
      };
      node.port.postMessage({ type: "capture" });
    });
  }

  stop() {
    this.generation++;
    if (this.pending) {
      clearTimeout(this.pending.timer);
      this.pending.reject(
        new Error(
          "Recording was interrupted. Keep this screen open and try again.",
        ),
      );
      this.pending = undefined;
    }
    const context = this.context;
    this.context = undefined;
    if (context) {
      context.onstatechange = null;
      void context.close().catch(() => {});
    }
    this.stream?.getTracks().forEach((t) => t.stop());
    this.stream = undefined;
    this.node?.disconnect();
    this.node = undefined;
    const enabling = this.enabling;
    if (enabling) {
      enabling.stream?.getTracks().forEach((track) => track.stop());
      enabling.stream = undefined;
      const enablingContext = enabling.context;
      enabling.context = undefined;
      if (enablingContext && enablingContext.state !== "closed") {
        enablingContext.onstatechange = null;
        void enablingContext.close().catch(() => {});
      }
    }
  }
}
