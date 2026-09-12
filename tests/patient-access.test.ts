import { readFileSync } from "node:fs";
import assert from "node:assert/strict";
import { test } from "node:test";
import { runInNewContext } from "node:vm";
import {
  Microphone,
  MicrophoneCancelledError,
} from "../src/lib/client/audio";
import {
  hasMicrophoneConsent,
  rememberMicrophoneConsent,
  shouldAutoAcquireMicrophone,
} from "../src/lib/client/microphone-access";
import { installGuidance } from "../src/components/home-screen-install";

class FakeTrack {
  stopCalls = 0;
  label = "Test microphone";
  private listeners = new Map<string, Array<() => void>>();

  stop() {
    this.stopCalls++;
  }

  getSettings() {
    return {
      sampleRate: 48000,
      echoCancellation: false,
      noiseSuppression: false,
      autoGainControl: false,
    };
  }

  addEventListener(name: string, listener: () => void) {
    const listeners = this.listeners.get(name) ?? [];
    listeners.push(listener);
    this.listeners.set(name, listeners);
  }

  emit(name: string) {
    for (const listener of this.listeners.get(name) ?? []) listener();
  }
}

class FakeStream {
  constructor(readonly track = new FakeTrack()) {}
  getAudioTracks() {
    return [this.track];
  }
  getTracks() {
    return [this.track];
  }
}

class FakeWorkletNode {
  static instances: FakeWorkletNode[] = [];
  disconnected = false;
  port = {
    onmessage: null as null | ((event: { data: any }) => void),
    sent: [] as any[],
    postMessage: (message: any) => this.port.sent.push(message),
  };

  constructor() {
    FakeWorkletNode.instances.push(this);
  }

  connect() {}
  disconnect() {
    this.disconnected = true;
  }
}

class FakeAudioContext {
  static resumeResults: Array<boolean | "pending"> = [];
  static instances: FakeAudioContext[] = [];
  state: AudioContextState;
  sampleRate = 48000;
  destination = {};
  onstatechange: null | (() => void) = null;
  resumeCalls = 0;
  closeCalls = 0;
  audioWorklet = { addModule: async () => {} };

  constructor() {
    this.state = FakeAudioContext.resumeResults.length ? "suspended" : "running";
    FakeAudioContext.instances.push(this);
  }

  async resume() {
    this.resumeCalls++;
    const runs = FakeAudioContext.resumeResults.shift() ?? true;
    if (runs === "pending") return new Promise<void>(() => {});
    if (runs) this.state = "running";
    this.onstatechange?.();
  }

  async close() {
    this.closeCalls++;
    this.state = "closed";
  }

  createMediaStreamSource() {
    return { connect: () => {} };
  }
}

function deferred<T>() {
  let resolve!: (value: T) => void;
  let reject!: (error: unknown) => void;
  const promise = new Promise<T>((res, rej) => {
    resolve = res;
    reject = rej;
  });
  return { promise, resolve, reject };
}

function installAudioGlobals(
  getUserMedia: () => Promise<FakeStream>,
): () => void {
  const originals = {
    navigator: Object.getOwnPropertyDescriptor(globalThis, "navigator"),
    AudioContext: Object.getOwnPropertyDescriptor(globalThis, "AudioContext"),
    AudioWorkletNode: Object.getOwnPropertyDescriptor(
      globalThis,
      "AudioWorkletNode",
    ),
  };
  Object.defineProperty(globalThis, "navigator", {
    configurable: true,
    value: { mediaDevices: { getUserMedia } },
  });
  Object.defineProperty(globalThis, "AudioContext", {
    configurable: true,
    value: FakeAudioContext,
  });
  Object.defineProperty(globalThis, "AudioWorkletNode", {
    configurable: true,
    value: FakeWorkletNode,
  });
  FakeAudioContext.instances = [];
  FakeAudioContext.resumeResults = [];
  FakeWorkletNode.instances = [];
  return () => {
    for (const [name, descriptor] of Object.entries(originals)) {
      if (descriptor) Object.defineProperty(globalThis, name, descriptor);
      else Reflect.deleteProperty(globalThis, name);
    }
  };
}

test("one microphone request is shared across concurrent enable attempts", async (t) => {
  const request = deferred<FakeStream>();
  let requestCount = 0;
  const restore = installAudioGlobals(() => {
    requestCount++;
    return request.promise;
  });
  t.after(restore);
  const microphone = new Microphone(() => {});
  const first = microphone.enable();
  const second = microphone.enable();
  assert.equal(requestCount, 1);
  request.resolve(new FakeStream());
  assert.deepEqual(await Promise.all([first, second]), ["ready", "ready"]);
  microphone.stop();
});

test("a stream resolving after background stop is discarded and never becomes ready", async (t) => {
  const request = deferred<FakeStream>();
  const restore = installAudioGlobals(() => request.promise);
  t.after(restore);
  const microphone = new Microphone(() => {});
  const enabling = microphone.enable();
  microphone.stop();
  const lateStream = new FakeStream();
  request.resolve(lateStream);
  await assert.rejects(enabling, MicrophoneCancelledError);
  assert.equal(lateStream.track.stopCalls, 1);
  assert.equal(FakeWorkletNode.instances.length, 0);
});

test("foreground return acquires one fresh stream after the background stream stopped", async (t) => {
  const streams = [new FakeStream(), new FakeStream()];
  let requestCount = 0;
  const restore = installAudioGlobals(async () => streams[requestCount++]);
  t.after(restore);
  const microphone = new Microphone(() => {});
  assert.equal(await microphone.enable(), "ready");
  microphone.stop();
  assert.equal(streams[0].track.stopCalls, 1);
  assert.equal(await microphone.enable(), "ready");
  assert.equal(requestCount, 2);
  assert.equal(streams[1].track.stopCalls, 0);
  microphone.stop();
});

test("track revocation stops capture access and reports interruption", async (t) => {
  const stream = new FakeStream();
  const restore = installAudioGlobals(async () => stream);
  t.after(restore);
  const states: string[] = [];
  const microphone = new Microphone((state) => states.push(state));
  assert.equal(await microphone.enable(), "ready");
  stream.track.emit("ended");
  assert.deepEqual(states, ["interrupted"]);
  assert.equal(stream.track.stopCalls, 1);
  await assert.rejects(
    microphone.capture(),
    /Enable the microphone before saving a moment/,
  );
});

test("a listening press resumes a gesture-blocked context before capture", async (t) => {
  const stream = new FakeStream();
  const restore = installAudioGlobals(async () => stream);
  t.after(restore);
  FakeAudioContext.resumeResults = [false, true];
  const states: string[] = [];
  const microphone = new Microphone((state) => states.push(state));
  assert.equal(await microphone.enable(), "gesture-required");
  const capture = microphone.capture();
  await new Promise<void>((resolve) => queueMicrotask(resolve));
  const node = FakeWorkletNode.instances[0];
  assert.deepEqual(node.port.sent, [{ type: "capture" }]);
  node.port.onmessage?.({
    data: {
      type: "complete",
      samples: new Float32Array([0.1, -0.1]),
      preSeconds: 0,
      postSeconds: 10,
    },
  });
  const result = await capture;
  assert.equal(result.capture.sampleRate, 48000);
  assert.equal(FakeAudioContext.instances[0].resumeCalls, 2);
  assert.deepEqual(states, []);
  microphone.stop();
});

test("remembered consent resumes only in the foreground and never overrides revocation", () => {
  assert.equal(
    shouldAutoAcquireMicrophone(true, "granted", "visible"),
    true,
  );
  assert.equal(
    shouldAutoAcquireMicrophone(true, "unsupported", "visible"),
    true,
  );
  assert.equal(
    shouldAutoAcquireMicrophone(true, "granted", "hidden"),
    false,
  );
  assert.equal(
    shouldAutoAcquireMicrophone(true, "denied", "visible"),
    false,
  );
  assert.equal(
    shouldAutoAcquireMicrophone(true, "prompt", "visible"),
    false,
  );
});

test("app consent is non-secret and scoped to the paired profile", () => {
  const values = new Map<string, string>();
  const storage = {
    getItem: (key: string) => values.get(key) ?? null,
    setItem: (key: string, value: string) => values.set(key, value),
    removeItem: (key: string) => values.delete(key),
  };
  rememberMicrophoneConsent("patient-a", storage);
  assert.equal(hasMicrophoneConsent("patient-a", storage), true);
  assert.equal(hasMicrophoneConsent("patient-b", storage), false);
  assert.deepEqual([...values.values()], ["yes"]);
});

test("install fallback distinguishes iOS Safari and keeps app identity secret-free", () => {
  assert.deepEqual(
    installGuidance(
      "Mozilla/5.0 (iPhone; CPU iPhone OS 26_0 like Mac OS X) AppleWebKit/605.1.15 Version/26.0 Mobile/15E148 Safari/604.1",
    ),
    [
      "Tap Share in Safari.",
      "Choose Add to Home Screen, then tap Add.",
    ],
  );
  assert.match(
    installGuidance(
      "Mozilla/5.0 (iPhone; CPU iPhone OS 26_0 like Mac OS X) AppleWebKit/605.1.15 CriOS/152.0 Mobile/15E148 Safari/604.1",
    )[0],
    /Safari/,
  );
  const manifest = JSON.parse(
    readFileSync("public/manifest.webmanifest", "utf8"),
  );
  assert.equal(manifest.id, "/app");
  assert.equal(manifest.start_url, "/app");
  assert.doesNotMatch(JSON.stringify(manifest), /token|capability|\/pair\//i);

  const serviceWorker = readFileSync("public/sw.js", "utf8");
  assert.match(serviceWorker, /url\.pathname\.startsWith\("\/api\/"\)/);
  assert.match(serviceWorker, /url\.pathname\.startsWith\("\/pair\/"\)/);
  const shell = serviceWorker.match(/const SHELL\s*=\s*\[([\s\S]*?)\];/)?.[1];
  assert.ok(shell);
  assert.doesNotMatch(shell, /"\/pair\//);
});


test("an unresolved autoplay resume cannot block the listening-button gesture path", async (t) => {
  const restore = installAudioGlobals(async () => new FakeStream());
  t.after(restore);
  FakeAudioContext.resumeResults = ["pending", true];
  const microphone = new Microphone(() => {});
  const state = await Promise.race([
    microphone.enable(),
    new Promise<string>((resolve) => setTimeout(() => resolve("blocked"), 100)),
  ]);
  assert.equal(state, "gesture-required");
  microphone.stop();
});

test("service worker handles public assets but never query-bearing requests or private routes", () => {
  const handlers = new Map<string, (event: any) => void>();
  const origin = "https://ihear.example";
  runInNewContext(readFileSync("public/sw.js", "utf8"), {
    URL,
    self: { location: { origin }, addEventListener: (name: string, handler: any) => handlers.set(name, handler) },
    fetch: async () => ({ ok: false }),
  });
  const handles = (path: string, method = "GET") => {
    let handled = false;
    handlers.get("fetch")!({ request: { url: origin + path, method }, respondWith: () => { handled = true; } });
    return handled;
  };
  for (const path of ["/app", "/app/pair", "/_next/static/chunk.js"]) assert.equal(handles(path), true);
  for (const path of ["/app?token=synthetic", "/app/pair?code=synthetic", "/_next/static/chunk.js?token=synthetic", "/pair/synthetic", "/api/events", "/app/events/synthetic"]) assert.equal(handles(path), false);
  assert.equal(handles("/app", "POST"), false);
});
