// The TV's audio (docs/ARCHITECTURE.md, "Player da TV"): instrumental and guide voice start at the same instant of
// one AudioContext, are mixed, and the mix goes through a single Rubber Band (R3) that changes the key live.
import { createRubberBandNode, type RubberBandNode } from "rubberband-web";
import workletUrl from "../../node_modules/rubberband-web/public/rubberband-processor.js?url";
import type { Song } from "../api";

/** The delay Rubber Band R3 adds, measured in the phase 0 spike. */
export const SHIFTER_DELAY_S = 0.077;

type Buffers = { instrumental: AudioBuffer; vocals: AudioBuffer };

export class AudioEngine {
  private sources: AudioBufferSourceNode[] = [];
  private buffers: Buffers | null = null;
  private startedAt = 0; // ctx.currentTime when position 0 played (or would have)
  private offset = 0; // position while paused
  playing = false;

  private constructor(
    private readonly ctx: AudioContext,
    private readonly instrumental: GainNode,
    private readonly vocals: GainNode,
    private readonly shifter: RubberBandNode,
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
    mix.connect(shifter).connect(ctx.destination);
    return new AudioEngine(ctx, instrumental, vocals, shifter);
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

  /** The time the lyrics follow: what the speakers are playing now, after the shifter's and the output's delays
   *  and the manual adjustment (Bluetooth speakers lag). */
  lyricsTime(manualDelayS: number): number {
    return this.position() - SHIFTER_DELAY_S - (this.ctx.outputLatency || 0) - manualDelayS;
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
    this.shifter.setPitch(2 ** (semitones / 12));
  }

  setGuide(level: number): void {
    this.vocals.gain.value = level;
  }

  async close(): Promise<void> {
    this.stopSources();
    await this.ctx.close();
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
