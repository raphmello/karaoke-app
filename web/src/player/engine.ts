// The TV's audio (docs/ARCHITECTURE.md, "Player da TV"): instrumental and guide voice start at the same instant of
// one AudioContext and are mixed. In the original key the mix goes straight to the speakers, through a delay as long
// as the Rubber Band's; with the key changed it goes through a single Rubber Band (R3). On an iPhone mirrored to the
// TV, the R3 crackled even in the original key, which is the common case.
//
// A phone suspends the page's audio when the tab goes to the background, and an iPhone may leave it stuck there:
// resume() never settles. The engine pauses when the audio stops under it, and "Tocar" builds a fresh AudioContext
// when the old one will not come back; the decoded stems carry over, so the song goes on from where it was.
import { createRubberBandNode, type RubberBandNode } from "rubberband-web";
import workletUrl from "../../node_modules/rubberband-web/public/rubberband-processor.js?url";
import type { Song } from "../api";
import { FADE_S, SHIFTER_LATENCY_FRAMES, ShifterRoute, type Step } from "./route";

type Buffers = { instrumental: AudioBuffer; vocals: AudioBuffer };

type Graph = {
  ctx: AudioContext;
  instrumental: GainNode;
  vocals: GainNode;
  mix: GainNode;
  shifter: RubberBandNode;
  direct: GainNode; // the two paths' volumes, crossfaded
  shifted: GainNode;
};

/** How long "Tocar" waits for a suspended AudioContext before replacing it. */
const RESUME_WAIT_MS = 1500;

async function build(ctx: AudioContext): Promise<Graph> {
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
  return { ctx, instrumental, vocals, mix, shifter, direct, shifted };
}

/** True once the context runs; false if it has not after the wait (an iPhone's resume() can hang forever). */
async function resumed(ctx: AudioContext): Promise<boolean> {
  const attempt = ctx.resume().then(
    () => true,
    () => false,
  );
  const timeout = new Promise<boolean>((done) => setTimeout(() => done(false), RESUME_WAIT_MS));
  return (await Promise.race([attempt, timeout])) && ctx.state === "running";
}

export class AudioEngine {
  private sources: AudioBufferSourceNode[] = [];
  private buffers: Buffers | null = null;
  private startedAt = 0; // ctx.currentTime when position 0 played (or would have)
  private offset = 0; // position while paused
  playing = false;
  private route = new ShifterRoute();
  private semitones = 0; // kept to set up a replacement context as the old one was
  private guide = 0;

  private constructor(private g: Graph) {
    this.watch();
    document.addEventListener("visibilitychange", () => this.check());
  }

  /** Call from a click, before any await: browsers start audio only from an interaction with the page. The TV's PIN
   *  screen calls it as the PIN is sent, so the same tap logs in and starts the audio. */
  static context(): AudioContext {
    // iPhone: Web Audio plays on the "ringer" channel, muted by the silent switch, unless the page says it is a
    // media player (Safari 16.4+). Without this the TV ran, lyrics and all, with no sound.
    const session = (navigator as Navigator & { audioSession?: { type: string } }).audioSession;
    if (session) session.type = "playback";
    const ctx = new AudioContext();
    void ctx.resume().catch(() => undefined);
    return ctx;
  }

  /** The engine on a context made by `context()`; without one, it makes it (so call it from a click too). */
  static async create(ctx: AudioContext = AudioEngine.context()): Promise<AudioEngine> {
    return new AudioEngine(await build(ctx));
  }

  async load(media: NonNullable<Song["media"]>): Promise<void> {
    this.stop();
    this.buffers = null;
    const decode = async (url: string) => {
      const response = await fetch(url);
      if (!response.ok) throw new Error(`${url}: ${response.status}`);
      return this.g.ctx.decodeAudioData(await response.arrayBuffer());
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
    return this.playing ? this.g.ctx.currentTime - this.startedAt : this.offset;
  }

  /** The time the lyrics follow: what the speakers are playing now, after the path's delay (the same on both), the
   *  output's and the manual adjustment (Bluetooth speakers lag). */
  lyricsTime(manualDelayS: number): number {
    const pathDelay = SHIFTER_LATENCY_FRAMES / this.g.ctx.sampleRate;
    return this.position() - pathDelay - (this.g.ctx.outputLatency || 0) - manualDelayS;
  }

  /** Plays from where it was. False when the audio could not be started (the button stays on "Tocar"). */
  async play(): Promise<boolean> {
    if (!this.buffers) return false;
    if (this.playing) return true;
    const state = this.g.ctx.state as AudioContextState | "interrupted";
    // A closed or interrupted context is replaced at once, while still inside the click that asked for it.
    if (state === "closed" || state === "interrupted") await this.replace();
    else if (state !== "running" && !(await resumed(this.g.ctx))) await this.replace();
    if (this.g.ctx.state !== "running" && !(await resumed(this.g.ctx))) return false;
    this.start(this.offset);
    this.playing = true;
    return true;
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
    this.semitones = semitones;
    // back to 0, the fade-out keeps the last key
    if (semitones !== 0) this.g.shifter.setPitch(2 ** (semitones / 12));
    this.apply(this.route.want(semitones !== 0, this.g.ctx.currentTime));
  }

  setGuide(level: number): void {
    this.guide = level;
    this.g.vocals.gain.value = level;
  }

  async close(): Promise<void> {
    this.stopSources();
    await this.g.ctx.close();
  }

  /** The audio stopped under the song (the tab went to the background, a call came in): pause, keeping the place. */
  private check(): void {
    if (this.playing && this.g.ctx.state !== "running") this.pause();
  }

  private watch(): void {
    const ctx = this.g.ctx;
    ctx.onstatechange = () => ctx === this.g.ctx && this.check();
  }

  /** A fresh AudioContext in place of one that will not come back. The new context is made before the first await,
   *  so it still counts as started by the click. */
  private async replace(): Promise<void> {
    const old = this.g.ctx;
    const ctx = new AudioContext();
    void ctx.resume().catch(() => undefined);
    old.onstatechange = null;
    this.stopSources();
    this.g = await build(ctx);
    this.watch();
    this.route = new ShifterRoute();
    this.setGuide(this.guide);
    this.setSemitones(this.semitones);
    void old.close().catch(() => undefined);
  }

  private apply(step: Step): void {
    const { mix, shifter, direct, shifted, ctx } = this.g;
    if (step.connect) mix.connect(shifter);
    if (step.fade) {
      const { to, at } = step.fade;
      // setTargetAtTime starts from wherever the volume is, so a fade cut short by another change stays smooth
      for (const [gain, level] of [[direct, to === "direct" ? 1 : 0], [shifted, to === "shifted" ? 1 : 0]] as const) {
        gain.gain.cancelScheduledValues(at);
        gain.gain.setTargetAtTime(level, at, FADE_S / 4);
      }
    }
    if (step.disconnect) {
      const { at, token } = step.disconnect;
      const route = this.route;
      const wait = (at - ctx.currentTime) * 1000 + FADE_S * 1000; // the volume has settled by then
      setTimeout(() => {
        if (route !== this.route || !route.disconnected(token)) return; // a replaced context's step is void
        try {
          mix.disconnect(shifter);
        } catch {
          // already apart
        }
      }, wait);
    }
  }

  private start(at: number): void {
    if (!this.buffers) return;
    this.stopSources();
    const ctx = this.g.ctx;
    const when = ctx.currentTime + 0.05; // both stems start at the same future instant
    for (const [buffer, gain] of [
      [this.buffers.instrumental, this.g.instrumental],
      [this.buffers.vocals, this.g.vocals],
    ] as const) {
      const source = ctx.createBufferSource();
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
