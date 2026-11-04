// "Reprocessar" (docs/ARCHITECTURE.md, Painel → Acervo, and the queue's failed song): a few choices instead
// of the pipeline's stages, each saying what it redoes and about how long it takes. A choice shows the ones it
// already includes, "Tudo" takes them all (the video's data too), and a line says what will run. The API still gets
// stages, and redoes those that depend on them too.
import { useState } from "react";
import { STAGE_NAMES } from "../../lib/queue";
import { Icon, type IconName } from "./icons";
import { button, primary } from "./ui";

type ChoiceId = "letra" | "sincronia" | "fonetica" | "audio";
type Choice = { id: ChoiceId; icon: IconName; title: string; what: string; time: string; stages: string[]; includes: ChoiceId[] };

const CHOICES: Choice[] = [
  {
    id: "letra",
    icon: "lyrics",
    title: "Letra",
    what: "Busca a letra de novo e refaz a sincronia e a pronúncia.",
    time: "cerca de 1 min",
    stages: ["lyrics"],
    includes: ["sincronia", "fonetica"],
  },
  {
    id: "sincronia",
    icon: "clock",
    title: "Sincronia",
    what: "Sincroniza a letra com a voz de novo e refaz a pronúncia.",
    time: "menos de 1 min",
    stages: ["alignment"],
    includes: ["fonetica"],
  },
  {
    id: "fonetica",
    icon: "pencil",
    title: "Pronúncia",
    what: "Busca de novo a letra escrita como se fala, para cantar músicas em japonês, coreano, russo e outros alfabetos.",
    time: "segundos",
    stages: ["phonetic"],
    includes: [],
  },
  {
    id: "audio",
    icon: "headphones",
    title: "Áudio",
    what: "Baixa o vídeo de novo e separa a voz; refaz a sincronia, o tom e a pronúncia.",
    time: "alguns minutos",
    stages: ["download"],
    includes: ["sincronia", "fonetica"],
  },
];
const EVERY_STAGE = Object.keys(STAGE_NAMES);

/** The stages to send for what is marked: every one for "Tudo", else those of the marked choices. */
export function stagesOf(all: boolean, picked: ReadonlySet<ChoiceId>): string[] {
  if (all) return EVERY_STAGE;
  return [...new Set(CHOICES.filter((c) => picked.has(c.id)).flatMap((c) => c.stages))];
}

/** "Letra, Sincronia e Pronúncia": the choices that will run, said in Portuguese. */
function listed(names: string[]): string {
  return names.length < 2 ? (names[0] ?? "") : `${names.slice(0, -1).join(", ")} e ${names[names.length - 1]}`;
}

export function ReprocessForm({ onSubmit, onCancel }: { onSubmit: (stages: string[]) => void; onCancel?: () => void }) {
  const [all, setAll] = useState(false);
  const [picked, setPicked] = useState<Set<ChoiceId>>(new Set());
  const included = new Set(CHOICES.filter((c) => picked.has(c.id)).flatMap((c) => c.includes));
  const runs = all ? CHOICES : CHOICES.filter((c) => picked.has(c.id) || included.has(c.id));
  const stages = stagesOf(all, picked);
  // A choice another one already includes is not marked on its own; marking one takes in the ones it includes
  const toggle = (id: ChoiceId) =>
    setPicked((current) => {
      const next = new Set(current);
      if (next.has(id)) next.delete(id);
      else {
        next.add(id);
        for (const inner of CHOICES.find((c) => c.id === id)?.includes ?? []) next.delete(inner);
      }
      return next;
    });

  return (
    <div className="mt-2 flex flex-col gap-2 rounded-xl bg-(--menu-field) p-2.5">
      <Option
        icon="refresh"
        title="Tudo"
        what="Prepara a música inteira de novo, do começo."
        time="alguns minutos"
        state={all ? "on" : "off"}
        onClick={() => setAll(!all)}
      />
      <div className="flex flex-col gap-1.5">
        {CHOICES.map((choice) => (
          <Option
            key={choice.id}
            icon={choice.icon}
            title={choice.title}
            what={choice.what}
            time={choice.time}
            state={all || included.has(choice.id) ? "included" : picked.has(choice.id) ? "on" : "off"}
            onClick={() => !all && !included.has(choice.id) && toggle(choice.id)}
          />
        ))}
      </div>
      <p className="px-0.5 text-[12px] text-(--menu-text-3)" aria-live="polite">
        {all
          ? "Vai preparar tudo de novo."
          : runs.length
            ? `Vai refazer: ${listed(runs.map((c) => c.title))}.`
            : "Escolha o que refazer."}
      </p>
      <div className="flex gap-2">
        <button className={primary} disabled={stages.length === 0} onClick={() => onSubmit(stages)}>
          Reprocessar
        </button>
        {onCancel && (
          <button className={button} onClick={onCancel}>
            Cancelar
          </button>
        )}
      </div>
    </div>
  );
}

/** One choice: a card that is marked, included by another (or by "Tudo") or not marked. */
function Option({
  icon,
  title,
  what,
  time,
  state,
  onClick,
}: {
  icon: IconName;
  title: string;
  what: string;
  time: string;
  state: "on" | "included" | "off";
  onClick: () => void;
}) {
  const on = state !== "off";
  return (
    <button
      type="button"
      role="checkbox"
      aria-checked={on}
      aria-disabled={state === "included"}
      onClick={onClick}
      className={`flex items-start gap-2 rounded-[10px] border px-2.5 py-2 text-left transition-colors ${
        state === "on"
          ? "border-(--menu-accent) bg-(--menu-accent-soft)"
          : state === "included"
            ? "cursor-default border-(--menu-line) bg-(--menu-btn) opacity-70"
            : "border-(--menu-line) bg-(--menu-panel) hover:bg-(--menu-btn)"
      } focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-(--menu-accent)`}
    >
      <span className={`mt-0.5 shrink-0 ${state === "on" ? "text-(--menu-accent)" : "text-(--menu-text-3)"}`}>
        <Icon name={icon} className="h-[17px] w-[17px]" />
      </span>
      <span className="min-w-0 flex-1">
        <span className="flex flex-wrap items-baseline gap-x-1.5">
          <span className="font-medium">{title}</span>
          <span className="text-[11px] text-(--menu-text-3)">· {time}</span>
          {state === "included" && (
            <span className="rounded-[5px] bg-(--menu-thumb) px-1.5 text-[11px] text-(--menu-text-2)">incluída</span>
          )}
        </span>
        <span className="mt-0.5 block text-[12px] leading-snug text-(--menu-text-2)">{what}</span>
      </span>
      <span
        aria-hidden
        className={`mt-0.5 flex h-[18px] w-[18px] shrink-0 items-center justify-center rounded-[5px] border ${
          on ? "border-(--menu-accent) bg-(--menu-accent) text-(--menu-on-accent)" : "border-(--menu-input-line)"
        }`}
      >
        {on && (
          <svg viewBox="0 0 24 24" className="h-3 w-3" fill="none" stroke="currentColor" strokeWidth={3}>
            <path d="M5 12l5 5 9-10" />
          </svg>
        )}
      </span>
    </button>
  );
}
