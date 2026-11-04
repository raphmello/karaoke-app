// The library's list in Sala → Adicionar and Painel → Acervo (docs/specs/02-scrollbar-lista-musicas): grouped by
// artist under headers that stay on top while their group shows, the letter's badge on the first artist of each
// letter, and the A–Z index over the right edge to jump to a letter. A search or a filter shows a flat list instead,
// without headers or index. On the phones (Touch), bigger targets and an index with only the letters there are.
import { createContext, type ReactNode, useContext, useEffect, useRef, useState } from "react";
import type { Song } from "../../api";
import { type ArtistGroup, landing, LETTERS } from "../../lib/library";

/** The phones' screens: touch targets of 44 px, 16 px fields, the compact index and the bottom sheet. */
export const Touch = createContext(false);

const BUBBLE_MS = 700;

/** The scrolling area under a fixed search field: the list, and the index while it is grouped. */
export function LibraryScroll({
  groups,
  children,
  scroller,
}: {
  groups: ArtistGroup[] | null; // null: a flat list (a search or a filter)
  children: ReactNode;
  scroller?: React.RefObject<HTMLDivElement | null>;
}) {
  const own = useRef<HTMLDivElement>(null);
  const area = scroller ?? own;
  const present = [...new Set((groups ?? []).map((group) => group.letter))];
  const indexed = present.length > 0;
  const [active, setActive] = useState<string | null>(null);
  const follow = () => {
    const el = area.current;
    if (!el || !indexed) return;
    if (el.scrollTop > 0 && el.scrollTop + el.clientHeight >= el.scrollHeight - 2) {
      return setActive(present[present.length - 1]); // at the end, the last letter there is
    }
    let current = present[0];
    for (const section of el.querySelectorAll<HTMLElement>("[data-letter]")) {
      if (section.offsetTop > el.scrollTop + 1) break;
      current = section.dataset.letter!;
    }
    setActive(current);
  };
  useEffect(follow); // the list changed (a song added, renamed or removed): the active letter follows
  const jump = (letter: string) => {
    const target = landing(letter, present);
    const section = target && area.current?.querySelector<HTMLElement>(`[data-letter="${target}"]`);
    if (!section || !area.current) return target;
    area.current.scrollTop = section.offsetTop;
    setActive(target);
    return target;
  };
  return (
    <div className="relative flex min-h-0 flex-1">
      <div
        ref={area}
        onScroll={follow}
        className={`relative flex min-h-0 flex-1 flex-col gap-1.5 overflow-y-auto pb-4 pl-[14px] ${
          indexed ? "menu-no-scrollbar pr-[34px]" : "menu-thin-scrollbar pr-[14px]"
        }`}
      >
        {children}
      </div>
      {indexed && <LetterIndex present={present} active={active} onJump={jump} />}
    </div>
  );
}

/** The A–Z strip: press or drag to jump; a bubble shows the letter while dragging. A pointer shortcut only, hidden
 *  from the keyboard and screen readers (the list itself stays navigable). */
function LetterIndex({
  present,
  active,
  onJump,
}: {
  present: string[];
  active: string | null;
  onJump: (letter: string) => string | null;
}) {
  const touch = useContext(Touch);
  const letters = touch ? present : LETTERS;
  const strip = useRef<HTMLDivElement>(null);
  const [bubble, setBubble] = useState<{ letter: string; y: number } | null>(null);
  const [dragging, setDragging] = useState(false);
  const timer = useRef(0);
  useEffect(() => () => window.clearTimeout(timer.current), []);
  const at = (clientY: number) => {
    const items = [...(strip.current?.querySelectorAll<HTMLElement>("[data-index]") ?? [])];
    const found = items.find((item) => clientY < item.getBoundingClientRect().bottom) ?? items[items.length - 1];
    return found ? { letter: found.dataset.index!, y: found.offsetTop + found.offsetHeight / 2 } : null;
  };
  const press = (clientY: number) => {
    const hit = at(clientY);
    if (!hit) return;
    const target = onJump(hit.letter);
    window.clearTimeout(timer.current);
    if (target) setBubble({ letter: target, y: hit.y });
  };
  const release = () => {
    setDragging(false);
    timer.current = window.setTimeout(() => setBubble(null), BUBBLE_MS);
  };
  return (
    <div
      ref={strip}
      aria-hidden="true"
      // above the artists' sticky headers (z-10), which the bubble, left of the strip, would otherwise slip under
      className={`absolute top-0 right-0 bottom-0 z-20 flex touch-none flex-col justify-center py-1.5 select-none ${
        touch ? "w-8" : "w-[26px] right-1"
      }`}
      onPointerDown={(event) => {
        event.preventDefault();
        event.currentTarget.setPointerCapture(event.pointerId);
        setDragging(true);
        press(event.clientY);
      }}
      onPointerMove={(event) => dragging && press(event.clientY)}
      onPointerUp={release}
      onPointerCancel={release}
    >
      {letters.map((letter) => (
        <span
          key={letter}
          data-index={letter}
          className={`flex min-h-0 flex-1 cursor-pointer items-center justify-center ${
            touch ? "max-h-[30px] text-[12px]" : "max-h-4 text-[11px]"
          }`}
        >
          <span
            className={`rounded-full px-1.5 leading-[15px] ${
              letter === active
                ? "bg-(--menu-accent) font-medium text-(--menu-on-accent)"
                : present.includes(letter)
                  ? "text-(--menu-text-2)"
                  : "text-[#4f4f58]"
            }`}
          >
            {letter}
          </span>
        </span>
      ))}
      {bubble && (
        <span
          className={`pointer-events-none absolute flex items-center justify-center bg-(--menu-accent) font-medium text-(--menu-on-accent) shadow-[0_6px_24px_rgba(0,0,0,.5)] ${
            touch ? "right-11 h-16 w-16 rounded-[16px] text-[32px]" : "right-8 h-[52px] w-[52px] rounded-[14px] text-[26px]"
          }`}
          style={{ top: bubble.y - (touch ? 32 : 26) }}
        >
          {bubble.letter}
        </span>
      )}
    </div>
  );
}

/** The groups: each artist's header (the letter's badge on the first of each letter, the count) over its songs. */
export function ArtistGroups({ groups, row }: { groups: ArtistGroup[]; row: (song: Song) => ReactNode }) {
  const touch = useContext(Touch);
  return groups.map((group, index) => {
    const first = index === 0 || groups[index - 1].letter !== group.letter;
    const count = group.songs.length;
    return (
      <section
        key={`${group.key}|${group.name}`}
        data-letter={first ? group.letter : undefined}
        aria-label={`${group.name}, ${count} música${count === 1 ? "" : "s"}`}
        className="flex flex-col"
      >
        <h3
          // the shadow paints the panel's color 8 px above the header: a row never shows between it and the search
          // field, whatever the browser does with the sticky edge (Safari left such a band); in the middle of the
          // list it falls on the gap between rows
          className={`sticky top-0 z-10 flex items-center gap-2 bg-(--menu-panel) pt-2 pb-1 font-medium text-(--menu-text-2) shadow-[0_-8px_0_var(--menu-panel)] ${
            touch ? "text-[13px]" : "text-[12px]"
          }`}
        >
          <span
            aria-hidden="true"
            className={`flex shrink-0 items-center justify-center rounded-md text-(--menu-accent) ${touch ? "h-[22px] w-[22px] text-[13px]" : "h-5 w-5 text-[12px]"} ${
              first ? "bg-(--menu-accent-soft)" : ""
            }`}
          >
            {first ? group.letter : ""}
          </span>
          <span className="truncate">{group.name}</span>
          <span className="shrink-0 font-normal text-(--menu-text-off)">· {count}</span>
        </h3>
        {group.songs.map(row)}
      </section>
    );
  });
}
