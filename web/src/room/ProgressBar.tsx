// A song being prepared (docs/ARCHITECTURE.md, "Progresso da preparação"): the bar follows the worker's progress, which comes about
// every second, and glides between one update and the next, so it never stands still; the stripes keep moving
// even when a stage has nothing new to say.
export function ProgressBar({ percent, className = "" }: { percent: number; className?: string }) {
  return (
    <div
      role="progressbar"
      aria-valuemin={0}
      aria-valuemax={100}
      aria-valuenow={percent}
      className={`h-1.5 overflow-hidden rounded-full bg-zinc-800 ${className}`}
    >
      <div
        className="progress-stripes h-full rounded-full bg-amber-400 transition-[width] duration-1000 ease-linear"
        style={{ width: `${Math.max(percent, 2)}%` }}
      />
    </div>
  );
}
