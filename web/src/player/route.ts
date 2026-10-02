// Which path the TV's mix takes (docs/ARCHITECTURE.md, "Tom"): straight to the speakers in the original key, through
// the Rubber Band only while the key is changed. Pure rules, so the tests run without a browser; the engine applies
// the steps to the audio graph.

/** The Rubber Band's delay with the R3 engine, in samples (measured; the same at 44.1 and 48 kHz). The direct path
 *  waits as long, so the lyrics keep one clock on both paths. */
export const SHIFTER_LATENCY_FRAMES = 4096;
/** How long the Rubber Band takes in audio before it is heard: its delay plus a margin, so its stale tail from the
 *  last time it ran is never heard. */
export const WARMUP_S = 0.2;
/** The crossfade between the two paths. */
export const FADE_S = 0.05;

export type Step = {
  /** Feed the mix to the Rubber Band now. */
  connect?: boolean;
  /** Crossfade to this path, starting at this AudioContext time. */
  fade?: { to: "direct" | "shifted"; at: number };
  /** Stop feeding the Rubber Band at this AudioContext time, once the fade to the direct path is over. Pass the token
   *  back to `disconnected` then: a later change of mind voids it. */
  disconnect?: { at: number; token: number };
};

export class ShifterRoute {
  /** direct: the Rubber Band gets no audio. shifted: it is fed and heard (or about to be). leaving: still fed while
   *  the fade back to the direct path plays. */
  state: "direct" | "shifted" | "leaving" = "direct";
  private token = 0;

  /** The key changed: `shifted` says whether it is off the original. */
  want(shifted: boolean, now: number): Step {
    if (shifted) {
      if (this.state === "direct") {
        this.state = "shifted";
        return { connect: true, fade: { to: "shifted", at: now + WARMUP_S } };
      }
      if (this.state === "leaving") {
        this.state = "shifted";
        this.token++; // the Rubber Band never stopped: back to it at once, and keep feeding it
        return { fade: { to: "shifted", at: now } };
      }
      return {};
    }
    if (this.state === "shifted") {
      this.state = "leaving";
      return { fade: { to: "direct", at: now }, disconnect: { at: now + FADE_S, token: ++this.token } };
    }
    return {};
  }

  /** The disconnect's time came: true when it still stands. */
  disconnected(token: number): boolean {
    if (this.state !== "leaving" || token !== this.token) return false;
    this.state = "direct";
    return true;
  }
}
