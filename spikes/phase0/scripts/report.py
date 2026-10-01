"""Step 5: build the results tables (Markdown) and the local evidence page (HTML with audio players).

The evidence page lives in work/, next to the audio it plays, and is never committed.
"""
from __future__ import annotations

import argparse
import json
import statistics

from common import RESULTS, SONGS, WORK, load_songs, read_json

SEP_LABELS = {
    "bs_roformer": "BS-RoFormer (padrão)",
    "bs_roformer_fast": "BS-RoFormer rápido",
    "bs_roformer_o1": "BS-RoFormer ultrarrápido",
    "melband_roformer": "MelBand RoFormer (padrão)",
    "melband_roformer_fast": "MelBand RoFormer rápido",
    "melband_roformer_o1": "MelBand RoFormer ultrarrápido",
    "htdemucs_ft": "htdemucs_ft",
}
MODEL_LABELS = {
    "model_bs_roformer_ep_317_sdr_12.9755.ckpt": "BS-RoFormer",
    "vocals_mel_band_roformer.ckpt": "MelBand RoFormer",
}
PRECISION_LABELS = {"fp32": "float32", "autocast": "autocast (fp16)", "fp16": "float16 nativo"}


def settings(variant: dict) -> str:
    if "overlap" not in variant and "precision" not in variant:
        return "padrão do modelo"
    return f"sobreposição {variant.get('overlap')}, {PRECISION_LABELS.get(variant.get('precision'), variant.get('precision'))}"
SYNC_LABELS = {
    "atual": "atual (música inteira)",
    "lrc_uniform": "LRC + palavras distribuídas",
    "lrc_stable": "LRC + stable-ts por linha",
    "lrc_ctc": "LRC + CTC por linha",
}
ALIGN_LABELS = {
    "turbo_vocals": "turbo · voz isolada",
    "turbo_vocals_vad": "turbo · voz isolada · VAD",
    "fw_large_v3_vocals": "large-v3 · voz isolada",
    "fw_large_v3_vocals_vad": "large-v3 · voz isolada · VAD",
    "turbo_mix": "turbo · mix original (controle)",
}


def table(headers: list[str], rows: list[list]) -> str:
    out = ["| " + " | ".join(headers) + " |", "| " + " | ".join("---" for _ in headers) + " |"]
    out += ["| " + " | ".join(str(c) for c in row) + " |" for row in rows]
    return "\n".join(out)


def mean(values) -> float | None:
    values = [v for v in values if v is not None]
    return statistics.fmean(values) if values else None


def fmt(value, digits: int = 1, suffix: str = "") -> str:
    return "—" if value is None else f"{value:.{digits}f}{suffix}"


def pct(value) -> str:
    return "—" if value is None else f"{value * 100:.0f}%"


def environment_section(env: dict) -> str:
    if not env:
        return "_env.json ausente_"
    gpu = env["gpu"]
    rows = [
        ["GPU", f"{gpu['name']} ({gpu['total_mib']} MiB), driver {gpu['driver']}"],
        ["PyTorch / CUDA / cuDNN", f"{env['packages'].get('torch')} / {env['torch_cuda']} / {env['cudnn']}"],
    ]
    rows += [[name, version or "—"] for name, version in env["packages"].items() if name != "torch"]
    rows += [[name, version] for name, version in env["tools"].items()]
    return table(["Item", "Versão"], rows)


def fetch_section(fetch: dict) -> str:
    rows = []
    for slug, f in fetch.items():
        if "video" not in f:
            rows.append([slug, "—", "—", "—", "—", f.get("error", "—"), "—", "—", "—"])
            continue
        d, lr, get = f.get("download", {}), f["lrclib"], f["lrclib_get"]
        rows.append([
            f"{f['artist']} — {f['title']}",
            f"[{f['video']['id']}](https://www.youtube.com/watch?v={f['video']['id']})",
            fmt(f["audio_s"], 0, " s"),
            f"{lr['sung_lines']} linhas",
            fmt(lr["duration_diff_s"], 1, " s"),
            "sim" if get["has_synced"] else f"não (HTTP {get['status']})",
            fmt(d.get("metadata_s"), 1, " s"),
            fmt(get["elapsed_s"], 2, " s"),
            fmt((d.get("download_s") or 0) + (d.get("convert_s") or 0), 1, " s"),
        ])
    return table(
        ["Música", "Vídeo", "Duração", "Letra sincronizada", "Dif. duração vídeo × letra", "Achada por /api/get",
         "Metadados", "Busca da letra", "Download + WAV"],
        rows,
    )


def speed_section(speed: dict) -> str:
    if not speed:
        return "_não executado_"
    rows = []
    for r in speed["rows"]:
        rows.append([
            MODEL_LABELS.get(r["model"], r["model"]),
            r["overlap"],
            PRECISION_LABELS.get(r["precision"], r["precision"]),
            fmt(r.get("separate_s"), 1, " s") if "error" not in r else "falhou",
            fmt(r.get("realtime_factor"), 1, "×"),
            f"{r['vram_process_mib']} MiB" if "vram_process_mib" in r else "—",
            fmt(r.get("db_vs_reference"), 1, " dB"),
        ])
    return (
        f"Trecho de {speed['seconds']:.0f} s de `{speed['song']}`. A última coluna compara o instrumental com o da "
        "configuração mais lenta do mesmo modelo (sobreposição 4, float32): quanto maior, mais parecido.\n\n"
        + table(["Modelo", "Sobreposição", "Precisão", "Tempo", "Velocidade × tempo real", "VRAM do processo",
                 "Fidelidade à referência"], rows)
    )


def musdb_section(musdb: dict) -> str:
    if not musdb:
        return "_não executado_"
    from separate import VARIANTS

    rows = [
        [SEP_LABELS.get(k, k), settings(VARIANTS.get(k, {})), fmt(m["instrumental"]["median"], 2, " dB"),
         fmt(m["vocals"]["median"], 2, " dB")]
        for k, m in musdb.items()
    ]
    first = next(iter(musdb.values()))
    return (
        f"SDR (relação sinal/distorção) contra os stems verdadeiros, em {first['instrumental']['n']} trechos de 7 s "
        f"do conjunto de teste do MUSDB18 ({first['vocals']['n']} com voz). Quanto maior, melhor.\n\n"
        + table(["Variante", "Configuração", "SDR instrumental (mediana)", "SDR voz (mediana)"], rows)
    )


def separation_section(sep: dict) -> str:
    rows = []
    for key, r in sep.items():
        songs = r["songs"].values()
        rows.append([
            SEP_LABELS.get(key, key),
            settings(r),
            fmt(r["load_s"], 1, " s"),
            fmt(mean(s["separate_s"] for s in songs), 1, " s"),
            fmt(mean(s["realtime_factor"] for s in songs), 1, "×"),
            f"{r['vram_process_mib']} MiB",
        ])
    summary = table(
        ["Variante", "Configuração", "Carregar", "Separar (média/música)", "Velocidade × tempo real",
         "VRAM do processo (pico)"],
        rows,
    )
    slugs = list(dict.fromkeys(slug for r in sep.values() for slug in r["songs"]))
    per_song = table(
        ["Música"] + [SEP_LABELS.get(k, k) for k in sep],
        [[slug] + [fmt(sep[k]["songs"].get(slug, {}).get("separate_s"), 1, " s") for k in sep] for slug in slugs],
    )
    return summary + "\n\nTempo de separação por música:\n\n" + per_song


def alignment_section(align: dict) -> str:
    rows = []
    for variant, r in align.items():
        ok = [s for s in r["songs"].values() if "align_s" in s]
        failed = len(r["songs"]) - len(ok)
        total_lines = sum(s["lines"] for s in ok)
        rows.append([
            ALIGN_LABELS.get(variant, variant),
            fmt(r.get("load_s"), 1, " s"),
            fmt(mean(s["align_s"] for s in ok), 1, " s"),
            f"{r.get('vram_process_mib', '—')} MiB",
            fmt(statistics.median(s["median_err_s"] for s in ok), 2, " s") if ok else "—",
            pct(sum(s["within_0_5s"] * s["lines"] for s in ok) / total_lines) if total_lines else "—",
            pct(sum(s["within_1_0s"] * s["lines"] for s in ok) / total_lines) if total_lines else "—",
            f"{sum(s['lines_over_2s'] for s in ok)} de {total_lines}",
            failed,
        ])
    summary = table(
        ["Variante", "Carregar", "Alinhar (média/música)", "VRAM do processo (pico)", "Erro mediano",
         "Linhas ≤ 0,5 s", "Linhas ≤ 1 s", "Linhas com erro > 2 s", "Falhas"],
        rows,
    )
    slugs = list(dict.fromkeys(slug for r in align.values() for slug in r["songs"]))
    per_song = table(
        ["Música"] + [ALIGN_LABELS.get(v, v) for v in align],
        [
            [slug] + [
                (f"{pct(s['within_0_5s'])} · {s['lines_over_2s']} > 2 s" if "within_0_5s" in s else "falhou")
                for s in (align[v]["songs"].get(slug, {}) for v in align)
            ]
            for slug in slugs
        ],
    )
    drift = table(
        ["Música", "Deslocamento vídeo × LRC", "Deriva de velocidade do LRC"],
        [
            [slug, fmt(s["offset_s"], 1, " s"), fmt(s["drift_pct"], 2, "%")]
            for slug, s in next(iter(align.values()))["songs"].items() if "offset_s" in s
        ],
    )
    return (
        "Erro = distância entre o início alinhado de cada linha e o tempo do LRC, depois de ajustar uma reta "
        "(deslocamento e escala) que descarta linhas a mais de 2 s.\n\n" + summary
        + "\n\nPor música (linhas ≤ 0,5 s · linhas com erro > 2 s):\n\n" + per_song
        + "\n\nDiferenças entre o vídeo e a letra do LRCLIB que o alinhamento absorve (variante "
        + f"{ALIGN_LABELS.get(next(iter(align)), next(iter(align)))}):\n\n" + drift
    )


def sync_section(sync: dict) -> str:
    if not sync:
        return "_não executado_"
    per_song = table(
        ["Música", "Linhas", "Linhas que o alinhamento atual deslocava > 1 s", "> 2 s", "Deriva do LRC",
         "Concordância stable-ts × CTC (palavras ≤ 0,2 s)"],
        [
            [slug, r["lines"], r["fit"]["lines_moved_over_1s"], r["fit"]["lines_moved_over_2s"],
             fmt(r["fit"]["drift_pct"], 2, "%"), pct(r.get("stable_ctc_agreement_0_2s"))]
            for slug, r in sync.items()
        ],
    )
    variants = [v for v in ("lrc_stable", "lrc_ctc") if all(v in r["variants"] for r in sync.values())]
    total_lines = sum(r["lines"] for r in sync.values())
    per_variant = table(
        ["Variante", "Tempo médio por música", "Linhas sem alinhamento de palavras (plano B)"],
        [
            [SYNC_LABELS[v], fmt(mean(r["variants"][v]["seconds"] for r in sync.values()), 1, " s"),
             f"{sum(r['variants'][v]['fallback_lines'] for r in sync.values())} de {total_lines}"]
            for v in variants
        ],
    )
    return (
        "As linhas começam no tempo do LRC, levado para o relógio do áudio pela reta ajustada contra o alinhamento da "
        "música inteira; as palavras são alinhadas dentro da janela de cada linha. Sem gabarito palavra por palavra, "
        "a concordância entre os dois alinhadores independentes é o indicador objetivo; o veredito é de ouvido.\n\n"
        + per_song + "\n\n" + per_variant
    )


def pitch_section(pitch: dict) -> str:
    rows = []
    for slug, r in pitch.items():
        steps = {s["semitones"]: s for s in r["steps"]}
        diffs = [abs(s[k]) for s in r["steps"] for k in ("instrumental_duration_diff_ms", "vocals_duration_diff_ms")]
        rows.append([
            slug,
            fmt(r["audio_s"], 0, " s"),
            fmt(steps.get(-4, {}).get("total_s"), 1, " s"),
            fmt(steps.get(4, {}).get("total_s"), 1, " s"),
            fmt(max(diffs), 1, " ms"),
        ])
    out = (
        "Motor R3 (`--fine`), os dois stems um após o outro, na CPU (i5-12400F).\n\n"
        + table(["Música", "Duração", "−4 semitons (2 stems)", "+4 semitons (2 stems)", "Maior diferença de duração"], rows)
    )
    options = read_json(RESULTS / "pitch_options.json", {})
    if options:
        out += (
            f"\n\nAlternativas mais rápidas, em `{options['song']}` ({options['audio_s']:.0f} s) a +{options['semitones']} "
            "semitons:\n\n"
            + table(
                ["Opção", "Tempo", "Diferença de duração"],
                [[r["option"], fmt(r["wall_s"], 1, " s"), fmt(r["duration_diff_ms"], 1, " ms")] for r in options["rows"]],
            )
        )
    return out


def end_to_end_section(fetch: dict, sep: dict, align: dict, sep_key: str, variant: str) -> str:
    if sep_key not in sep or variant not in align:
        return "_dados insuficientes_"
    rows, totals, ratios = [], [], []
    for slug, f in fetch.items():
        s = sep[sep_key]["songs"].get(slug)
        a = align[variant]["songs"].get(slug)
        if "download" not in f or not s or not a or "align_s" not in a:
            continue
        d = f["download"]
        stages = [
            d["metadata_s"] + f["lrclib_get"]["elapsed_s"],
            d["download_s"] + d["convert_s"],
            sep[sep_key]["load_s"] + s["separate_s"],
            align[variant]["load_s"] + a["align_s"],
            s["encode_opus_s"],
        ]
        total = sum(stages)
        totals.append(total)
        ratios.append(total / f["audio_s"])
        rows.append([slug, fmt(f["audio_s"], 0, " s")] + [fmt(x, 1, " s") for x in stages] + [fmt(total, 1, " s")])
    rows.append(["**média**", "", "", "", "", "", "", f"**{fmt(mean(totals), 1, ' s')}**"])
    return (
        f"Combinação: {SEP_LABELS.get(sep_key, sep_key)} + {ALIGN_LABELS.get(variant, variant)}, carregando cada "
        f"modelo a cada job (um modelo por vez na GPU de 8 GB).\n\n"
        + table(["Música", "Duração", "Metadados + letra", "Download", "Separação (com carga)", "Alinhamento (com carga)",
                 "Opus", "Total"], rows)
        + f"\n\nO processamento leva em média {fmt(mean(ratios) * 100, 0, '%')} da duração da música."
    )


def evidence_data(songs: list[dict], fetch: dict, sep: dict, align: dict, pitch: dict) -> list[dict]:
    data = []
    for song in songs:
        slug = song["slug"]
        folder = SONGS / slug
        if not (folder / "play" / "source.opus").exists():
            continue
        base = f"../songs/{slug}/play"
        alignments = {}
        for variant in align:
            path = folder / "align" / variant / "aligned.json"
            if path.exists():
                alignments[ALIGN_LABELS.get(variant, variant)] = read_json(path)["lines"]
        sync = {}
        for variant, label in SYNC_LABELS.items():
            path = folder / "sync" / variant / "aligned.json"
            if path.exists():
                sync[label] = read_json(path)["lines"]
        data.append({
            "slug": slug,
            "title": f"{song['artist']} — {song['title']}",
            "video": fetch.get(slug, {}).get("video", {}).get("id"),
            "instrumental": [{"label": "Original", "src": f"{base}/source.opus"}]
            + [{"label": SEP_LABELS.get(k, k), "src": f"{base}/inst_{k}.opus"} for k in sep if (folder / "play" / f"inst_{k}.opus").exists()],
            "vocals": [{"label": SEP_LABELS.get(k, k), "src": f"{base}/vocals_{k}.opus"} for k in sep if (folder / "play" / f"vocals_{k}.opus").exists()],
            "pitch": (
                [{"label": "Tom original", "src": f"{base}/inst_{pitch[slug]['stem_model']}.opus"},
                 {"label": "−4", "src": f"{base}/inst_pitch-4.opus"}, {"label": "+4", "src": f"{base}/inst_pitch+4.opus"}]
                + ([{"label": "+4 (R2, rápido)", "src": f"{base}/inst_pitch+4_r2.opus"}]
                   if (folder / "play" / "inst_pitch+4_r2.opus").exists() else [])
                if slug in pitch else []
            ),
            "mix": f"{base}/source.opus",
            "alignments": alignments,
            "sync": sync,
        })
    return data


PAGE = """<!doctype html>
<html lang="pt-BR">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Spike fase 0 · evidências</title>
<style>
  :root { --bg:#111418; --card:#1a1f26; --ink:#e8eaed; --muted:#9aa0a6; --line:#2c333d; --accent:#f5c518; }
  * { box-sizing:border-box; }
  body { margin:0; background:var(--bg); color:var(--ink); font:15px/1.5 system-ui, sans-serif; }
  main { max-width:960px; margin:0 auto; padding:24px 16px 80px; }
  h1 { font-size:22px; margin:0 0 4px; } h2 { font-size:18px; margin:0 0 12px; } h3 { font-size:14px; color:var(--muted); margin:16px 0 8px; text-transform:uppercase; letter-spacing:.04em; }
  .card { background:var(--card); border:1px solid var(--line); border-radius:10px; padding:16px; margin:20px 0; }
  .muted { color:var(--muted); } a { color:var(--accent); }
  .ab { display:flex; flex-wrap:wrap; gap:8px; align-items:center; }
  button, select { background:#242b35; color:var(--ink); border:1px solid var(--line); border-radius:6px; padding:6px 10px; font:inherit; cursor:pointer; }
  button.on { border-color:var(--accent); color:var(--accent); }
  .bar { display:flex; gap:8px; align-items:center; margin-top:8px; } .bar input[type=range] { flex:1; }
  .rate { display:flex; flex-wrap:wrap; gap:12px; margin-top:8px; font-size:13px; } .rate label { color:var(--muted); }
  .karaoke { background:#0b0d10; border-radius:8px; padding:24px 16px; text-align:center; min-height:150px; }
  .k-prev, .k-next { color:var(--muted); font-size:16px; min-height:24px; }
  .k-dots { color:var(--accent); font-size:18px; letter-spacing:6px; min-height:24px; }
  .k-cur { font-size:26px; font-weight:600; margin:10px 0; min-height:38px; }
  .w { -webkit-background-clip:text; background-clip:text; color:transparent; }
  .k-meta { font-size:12px; color:var(--muted); margin-top:8px; }
  textarea { width:100%; height:140px; background:#0b0d10; color:var(--ink); border:1px solid var(--line); border-radius:6px; }
</style>
</head>
<body>
<main>
  <h1>Spike fase 0 · evidências</h1>
  <p class="muted">Compare os modelos de ouvido: ao trocar de botão, o áudio continua do mesmo ponto. As notas ficam salvas neste navegador; no fim, use “Exportar notas” e cole o resultado na conversa.</p>
  <div id="songs"></div>
  <div class="card"><h2>Exportar notas</h2><button id="export">Exportar notas</button><textarea id="out" readonly></textarea></div>
</main>
<script>
const DATA = __DATA__;
const store = {
  get(k) { try { return localStorage.getItem(k); } catch { return null; } },
  set(k, v) { try { localStorage.setItem(k, v); } catch {} },
};
const fmt = t => `${Math.floor(t / 60)}:${String(Math.floor(t % 60)).padStart(2, "0")}`;
let playing = null;  // only one player sounds at a time

function abPlayer(sources, onTime) {
  const wrap = document.createElement("div");
  const row = document.createElement("div"); row.className = "ab";
  const bar = document.createElement("div"); bar.className = "bar";
  const play = document.createElement("button"); play.textContent = "▶";
  const seek = document.createElement("input"); seek.type = "range"; seek.min = 0; seek.max = 1000; seek.value = 0;
  const time = document.createElement("span"); time.className = "muted"; time.textContent = "0:00";
  bar.append(play, seek, time);
  const audios = sources.map(s => { const a = new Audio(s.src); a.preload = "none"; return a; });
  let cur = 0;
  const buttons = sources.map((s, i) => {
    const b = document.createElement("button"); b.textContent = s.label;
    b.onclick = () => {
      const from = audios[cur], to = audios[i], t = from.currentTime, was = !from.paused;
      from.pause(); cur = i; to.currentTime = t; if (was) start();
      buttons.forEach((x, j) => x.classList.toggle("on", j === i));
    };
    row.append(b); return b;
  });
  buttons[0].classList.add("on");
  const start = () => { if (playing && playing !== api) playing.pause(); playing = api; audios[cur].play(); play.textContent = "❚❚"; };
  const api = { pause() { audios[cur].pause(); play.textContent = "▶"; }, current: () => audios[cur] };
  play.onclick = () => audios[cur].paused ? start() : api.pause();
  seek.oninput = () => { const a = audios[cur]; if (Number.isFinite(a.duration)) a.currentTime = seek.value / 1000 * a.duration; };
  audios.forEach(a => a.addEventListener("timeupdate", () => {
    if (a !== audios[cur]) return;
    if (Number.isFinite(a.duration)) seek.value = a.currentTime / a.duration * 1000;
    time.textContent = fmt(a.currentTime);
  }));
  if (onTime) { const tick = () => { onTime(audios[cur].currentTime); requestAnimationFrame(tick); }; requestAnimationFrame(tick); }
  wrap.append(row, bar);
  return wrap;
}

function ratings(slug, group, labels, options) {
  const box = document.createElement("div"); box.className = "rate";
  labels.forEach(label => {
    const key = `spike:${slug}:${group}:${label}`;
    const l = document.createElement("label"); l.textContent = label + " ";
    const s = document.createElement("select");
    ["—", ...options].forEach(o => { const opt = document.createElement("option"); opt.textContent = o; s.append(opt); });
    s.value = store.get(key) || "—";
    s.onchange = () => store.set(key, s.value);
    l.append(s); box.append(l);
  });
  return box;
}

const LEAD = 1.0;       // a line may appear this many seconds before it is sung...
const COUNTDOWN = 3.0;  // ...and after a break this long, dots count down to it

function karaoke(song) {
  const sets = song.sync && Object.keys(song.sync).length ? song.sync : song.alignments;
  const group = sets === song.sync ? "sincronizacao" : "alinhamento";
  const variants = Object.keys(sets);
  const box = document.createElement("div");
  if (!variants.length) { box.textContent = "Sem alinhamento."; return box; }
  const pick = document.createElement("select");
  variants.forEach(v => { const o = document.createElement("option"); o.textContent = v; pick.append(o); });
  const screen = document.createElement("div"); screen.className = "karaoke";
  const dots = document.createElement("div"); dots.className = "k-dots";
  const prev = document.createElement("div"); prev.className = "k-prev";
  const cur = document.createElement("div"); cur.className = "k-cur";
  const next = document.createElement("div"); next.className = "k-next";
  const meta = document.createElement("div"); meta.className = "k-meta";
  screen.append(dots, prev, cur, next, meta);
  let shown = -2, spans = [];
  const words = line => line.words.map(w => w.w).join(" ");
  const render = t => {
    const ls = sets[pick.value];
    // the line on screen: the last one within LEAD of starting, unless the one before is still being sung
    let k = -1; for (let j = 0; j < ls.length; j++) { if (ls[j].start - LEAD <= t) k = j; else break; }
    let i = k;
    if (k > 0 && t < ls[k].start && t < ls[k - 1].end) i = k - 1;
    if (i !== shown) {
      shown = i;
      prev.textContent = i > 0 ? words(ls[i - 1]) : "";
      next.textContent = i + 1 < ls.length ? words(ls[i + 1]) : "";
      cur.replaceChildren(); spans = [];
      if (i >= 0) ls[i].words.forEach((w, j) => {
        const s = document.createElement("span"); s.className = "w"; s.textContent = w.w;
        cur.append(s); if (j < ls[i].words.length - 1) cur.append(" "); spans.push([s, w]);
      });
      meta.textContent = i >= 0
        ? `início ${ls[i].start.toFixed(2)} s · LRC ${ls[i].lrc_t.toFixed(2)} s${ls[i].low_confidence ? " · baixa confiança: linha inteira" : ""}`
        : "";
    }
    const up = ls.findIndex(l => l.start > t);
    const gap = up < 0 ? 0 : ls[up].start - (up > 0 ? ls[up - 1].end : 0);
    const left = up < 0 ? 99 : ls[up].start - t;
    dots.textContent = gap >= COUNTDOWN && left <= COUNTDOWN ? "● ".repeat(Math.ceil(left)).trim() : "";
    const whole = i >= 0 && ls[i].low_confidence;
    spans.forEach(([s, w]) => {
      const p = whole ? (t >= ls[i].start ? 100 : 0) : Math.max(0, Math.min(1, (t - w.s) / Math.max(w.e - w.s, 0.01))) * 100;
      s.style.backgroundImage = `linear-gradient(90deg, var(--accent) ${p}%, var(--ink) ${p}%)`;
    });
  };
  pick.onchange = () => { shown = -2; };
  const player = abPlayer([{ label: "Mix original", src: song.mix }, ...song.instrumental.slice(1, 2)], render);
  box.append(pick, player, screen, ratings(song.slug, group, variants, ["bom", "aceitável", "ruim"]));
  return box;
}

const root = document.getElementById("songs");
DATA.forEach(song => {
  const card = document.createElement("section"); card.className = "card";
  const h = document.createElement("h2"); h.textContent = song.title; card.append(h);
  if (song.video) { const a = document.createElement("a"); a.href = `https://www.youtube.com/watch?v=${song.video}`; a.textContent = `youtube ${song.video}`; a.target = "_blank"; card.append(a); }
  const add = (title, el) => { const t = document.createElement("h3"); t.textContent = title; card.append(t, el); };
  add("Instrumental (voz removida)", abPlayer(song.instrumental));
  card.append(ratings(song.slug, "instrumental", song.instrumental.slice(1).map(s => s.label), ["1 voz forte", "2", "3", "4", "5 limpo"]));
  if (song.vocals.length) add("Voz isolada (usada no alinhamento)", abPlayer(song.vocals));
  if (song.pitch.length) {
    add("Tom ±4 semitons (Rubber Band R3)", abPlayer(song.pitch));
    card.append(ratings(song.slug, "tom", ["−4", "+4"], ["natural", "aceitável", "artificial"]));
  }
  add("Prévia do karaokê", karaoke(song));
  root.append(card);
});
document.getElementById("export").onclick = () => {
  const notes = {};
  for (let i = 0; i < localStorage.length; i++) { const k = localStorage.key(i); if (k.startsWith("spike:")) notes[k.slice(6)] = localStorage.getItem(k); }
  document.getElementById("out").value = JSON.stringify(notes, null, 1);
};
</script>
</body>
</html>
"""


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--sep", default="bs_roformer_fast", help="separation variant for the end-to-end table")
    parser.add_argument("--align", default="turbo_vocals", help="alignment variant for the end-to-end table")
    args = parser.parse_args()

    env = read_json(RESULTS / "env.json", {})
    fetch = read_json(RESULTS / "fetch.json", {})
    sep = read_json(RESULTS / "separation.json", {})
    musdb = read_json(RESULTS / "musdb.json", {})
    speed = read_json(RESULTS / "speed.json", {})
    align = read_json(RESULTS / "alignment.json", {})
    pitch = read_json(RESULTS / "pitch.json", {})

    sections = [
        ("Ambiente", environment_section(env)),
        ("Busca, letra e download", fetch_section(fetch)),
        ("Separação: velocidade por configuração", speed_section(speed)),
        ("Separação: qualidade no MUSDB18", musdb_section(musdb)),
        ("Separação: as 6 músicas", separation_section(sep) if sep else "_não executado_"),
        ("Alinhamento da letra", alignment_section(align) if align else "_não executado_"),
        ("Sincronização: LRC como esqueleto (spike 0b)", sync_section(read_json(RESULTS / "sync.json", {}))),
        ("Mudança de tom", pitch_section(pitch) if pitch else "_não executado_"),
        ("Tempo total por música", end_to_end_section(fetch, sep, align, args.sep, args.align)),
    ]
    tables = "\n\n".join(f"## {title}\n\n{body}" for title, body in sections)
    (RESULTS / "tables.md").write_text(tables + "\n", encoding="utf-8")

    data = evidence_data(load_songs(), fetch, sep, align, pitch)
    page = PAGE.replace("__DATA__", json.dumps(data, ensure_ascii=False).replace("</", "<\\/"))
    (WORK / "evidence").mkdir(parents=True, exist_ok=True)
    (WORK / "evidence" / "index.html").write_text(page, encoding="utf-8")
    print(f"wrote {RESULTS / 'tables.md'} and {WORK / 'evidence' / 'index.html'} ({len(data)} songs)")


if __name__ == "__main__":
    main()
