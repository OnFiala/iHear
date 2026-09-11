/* Audio is buffered only during an explicitly enabled foreground session. */
class PCMRecorder extends AudioWorkletProcessor {
  constructor() {
    super();
    this.ring = new Float32Array(Math.ceil(sampleRate * 5));
    this.cursor = 0;
    this.filled = 0;
    this.capture = null;
    this.port.onmessage = ({ data }) => {
      if (data.type === "capture" && !this.capture) {
        const pre = this.filled;
        const samples = new Float32Array(Math.round(sampleRate * 10));
        for (let i = 0; i < pre; i++)
          samples[i] =
            this.ring[
              (this.cursor - pre + i + this.ring.length) % this.ring.length
            ];
        this.capture = { samples, position: pre, pre };
        this.port.postMessage({
          type: "started",
          preSeconds: pre / sampleRate,
          postSeconds: 10 - pre / sampleRate,
        });
      }
    };
  }
  process(inputs, outputs) {
    const channels = inputs[0];
    if (!channels?.length || !channels[0]?.length) return true;
    const frames = channels[0].length;
    for (let i = 0; i < frames; i++) {
      let x = 0;
      for (const c of channels) x += c[i] || 0;
      x /= channels.length;
      this.ring[this.cursor] = x;
      this.cursor = (this.cursor + 1) % this.ring.length;
      this.filled = Math.min(this.filled + 1, this.ring.length);
      if (this.capture) {
        const c = this.capture;
        c.samples[c.position++] = x;
        if (c.position === c.samples.length) {
          this.port.postMessage(
            {
              type: "complete",
              samples: c.samples,
              preSeconds: c.pre / sampleRate,
              postSeconds: (c.samples.length - c.pre) / sampleRate,
            },
            [c.samples.buffer],
          );
          this.capture = null;
        }
      }
    }
    for (const output of outputs) for (const channel of output) channel.fill(0);
    return true;
  }
}
registerProcessor("pcm-recorder", PCMRecorder);
