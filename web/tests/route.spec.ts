import { expect, test } from "@playwright/test";
import { FADE_S, ShifterRoute, WARMUP_S } from "../src/player/route";

test("in the original key the Rubber Band gets no audio", () => {
  const route = new ShifterRoute();
  expect(route.want(false, 1)).toEqual({});
  expect(route.state).toBe("direct");
});

test("changing the key feeds the Rubber Band first and is heard after the warm-up", () => {
  const route = new ShifterRoute();
  expect(route.want(true, 10)).toEqual({ connect: true, fade: { to: "shifted", at: 10 + WARMUP_S } });
  expect(route.want(true, 11)).toEqual({}); // another half tone: same path
});

test("back to the original key, the fade plays before the Rubber Band stops getting audio", () => {
  const route = new ShifterRoute();
  route.want(true, 10);
  const step = route.want(false, 20);
  expect(step.fade).toEqual({ to: "direct", at: 20 });
  expect(step.disconnect?.at).toBe(20 + FADE_S);
  expect(route.disconnected(step.disconnect!.token)).toBe(true);
  expect(route.state).toBe("direct");
});

test("changing the key again during the fade back cancels the disconnect and needs no warm-up", () => {
  const route = new ShifterRoute();
  route.want(true, 10);
  const leave = route.want(false, 20);
  expect(route.want(true, 20.01)).toEqual({ fade: { to: "shifted", at: 20.01 } });
  expect(route.disconnected(leave.disconnect!.token)).toBe(false);
  expect(route.state).toBe("shifted");
});

test("back to the original key during the warm-up never lets the Rubber Band be heard", () => {
  const route = new ShifterRoute();
  route.want(true, 10);
  const step = route.want(false, 10.05); // the fade to the Rubber Band was due at 10.2
  expect(step.fade).toEqual({ to: "direct", at: 10.05 });
  expect(route.disconnected(step.disconnect!.token)).toBe(true);
});
