// The TV's audio (docs/ARCHITECTURE.md, "Player da TV"): instrumental and guide voice start at the same instant of
// one AudioContext and are mixed. In the original key the mix goes straight to the speakers, through a delay as long
// as the Rubber Band's; with the key changed it goes through a single Rubber Band (R3). On an iPhone mirrored to the
// TV, the R3 crackled even in the original key, which is the common case.
import { createRubberBandNode, type RubberBandNode } from "rubberband-web";
import workletUrl from "../../node_modules/rubberband-web/public/rubberband-processor.js?url";
import type { Song } from "../api";
import { FADE_S, SHIFTER_LATENCY_FRAMES, ShifterRoute, type Step } from "./route";

type Buffers = { instrumental: AudioBuffer; vocals: AudioBuffer };

export class AudioEngine {
  private sources: AudioBufferSourceNode[] = [];
  private buffers: Buffers | null = null;
  private startedAt = 0; // ctx.currentTime when position 0 played (or would have)
  private offset = 0; // position while paused
  playing = false;
  private readonly route = new ShifterRoute();

  private constructor(
    private readonly ctx: AudioContext,
    private readonly instrumental: GainNode,
    private readonly vocals: GainNode,
    private readonly mix: GainNode,
    private readonly shifter: RubberBandNode,
    private readonly direct: GainNode, // the two paths' volumes, crossfaded
    private readonly shifted: GainNode,
  ) {}

  /** Call from a click: browsers start audio only after the user interacts with the page. */
  static async create(): Promise<AudioEngine> {
    // iPhone: Web Audio plays on the "ringer" channel, muted by the silent switch, unless the page says it is a
    // media player (Safari 16.4+). Without this the TV ran, lyrics and all, with no sound.
    const session = (navigator as Navigator & { audioSession?: { type: string } }).audioSession;
    if (session) session.type = "playback";
    const ctx = new AudioContext();
    const shifter = await createRubberBandNode(ctx, workletUrl);
    shifter.setHighQuality(true); // the R3 engine
    const mix = ctx.createGain();
    const instrumental = ctx.createGain();
    const vocals = ctx.createGain();
    vocals.gain.value = 0; // guide voice off by default
    instrumental.connect(mix);
    vocals.connect(mix);
    const delay = ctx.createDelay(1);
    delay.delayTime.value = SHIFTER_LATENCY_FRAMES / ctx.sampleRate;
    const direct = ctx.createGain();
    const shifted = ctx.createGain();
    shifted.gain.value = 0;
    mix.connect(delay).connect(direct).connect(ctx.destination);
    shifter.connect(shifted).connect(ctx.destination); // fed by the mix only while the key is changed
    return new AudioEngine(ctx, instrumental, vocals, mix, shifter, direct, shifted);
  }

  async load(media: NonNullable<Song["media"]>): Promise<void> {
    this.stop();
    this.buffers = null;
    const decode = async (url: string) => {
      const response = await fetch(url);
      if (!response.ok) throw new Error(`${url}: ${response.status}`);
      return this.ctx.decodeAudioData(await response.arrayBuffer());
    };
    const [instrumental, vocals] = await Promise.all([decode(media.instrumental), decode(media.vocals)]);
    this.buffers = { instrumental, vocals };
    this.offset = 0;
  }

  get duration(): number {
    return this.buffers?.instrumental.duration ?? 0;
  }

  /** Where the music is, in seconds, as fed to the shifter. */
  position(): number {
    return this.playing ? this.ctx.currentTime - this.startedAt : this.offset;
  }

  /** The time the lyrics follow: what the speakers are playing now, after the path's delay (the same on both), the
   *  output's and the manual adjustment (Bluetooth speakers lag). */
  lyricsTime(manualDelayS: number): number {
    const pathDelay = SHIFTER_LATENCY_FRAMES / this.ctx.sampleRate;
    return this.position() - pathDelay - (this.ctx.outputLatency || 0) - manualDelayS;
  }

  async play(): Promise<void> {
    if (!this.buffers || this.playing) return;
    await this.ctx.resume();
    this.start(this.offset);
    this.playing = true;
  }

  pause(): void {
    if (!this.playing) return;
    this.offset = this.position();
    this.stopSources();
    this.playing = false;
  }

  seek(seconds: number): void {
    this.offset = Math.max(0, Math.min(seconds, this.duration));
    if (this.playing) this.start(this.offset);
  }

  stop(): void {
    this.stopSources();
    this.playing = false;
    this.offset = 0;
  }

  setSemitones(semitones: number): void {
    if (semitones !== 0) this.shifter.setPitch(2 ** (semitones / 12)); // back to 0, the fade-out keeps the last key
    this.apply(this.route.want(semitones !== 0, this.ctx.currentTime));
  }

  setGuide(level: number): void {
    this.vocals.gain.value = level;
  }

  async close(): Promise<void> {
    this.stopSources();
    await this.ctx.close();
  }

  private apply(step: Step): void {
    if (step.connect) this.mix.connect(this.shifter);
    if (step.fade) {
      const { to, at } = step.fade;
      // setTargetAtTime starts from wherever the volume is, so a fade cut short by another change stays smooth
      for (const [gain, level] of [[this.direct, to === "direct" ? 1 : 0], [this.shifted, to === "shifted" ? 1 : 0]] as const) {
        gain.gain.cancelScheduledValues(at);
        gain.gain.setTargetAtTime(level, at, FADE_S / 4);
      }
    }
    if (step.disconnect) {
      const { at, token } = step.disconnect;
      const wait = (at - this.ctx.currentTime) * 1000 + FADE_S * 1000; // the volume has settled by then
      setTimeout(() => {
        if (!this.route.disconnected(token)) return;
        try {
          this.mix.disconnect(this.shifter);
        } catch {
          // already apart
        }
      }, wait);
    }
  }

  private start(at: number): void {
    if (!this.buffers) return;
    this.stopSources();
    const when = this.ctx.currentTime + 0.05; // both stems start at the same future instant
    for (const [buffer, gain] of [
      [this.buffers.instrumental, this.instrumental],
      [this.buffers.vocals, this.vocals],
    ] as const) {
      const source = this.ctx.createBufferSource();
      source.buffer = buffer;
      source.connect(gain);
      source.start(when, at);
      this.sources.push(source);
    }
    this.startedAt = when - at;
  }

  private stopSources(): void {
    for (const source of this.sources) {
      try {
        source.stop();
      } catch {
        // never started
      }
      source.disconnect();
    }
    this.sources = [];
  }
}
