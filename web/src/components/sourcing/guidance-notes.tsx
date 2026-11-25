import { ArrowDown, ArrowUp, Ban } from "lucide-react";
import type { RankGuidance } from "@/lib/api/sourcing";
import { cn } from "@/lib/cn";

/** c5 + c6 — vì sao AI đẩy một món lên hay hạ xuống: nguyên tắc của chị và gu đã học. */
export function GuidanceNotes({ g, className }: { g: RankGuidance; className?: string }) {
  return (
    <ul className={cn("flex flex-col gap-1 text-[13px]", className)} aria-label="Nguyên tắc và gu của chị">
      {g.notes.map((n) => {
        const down = n.delta < 0;
        const Icon = n.kind === "principle" ? Ban : down ? ArrowDown : ArrowUp;
        return (
          <li key={n.text} className={cn("flex items-start gap-1.5 [text-wrap:pretty]", down ? "text-seal" : n.delta > 0 ? "text-auto" : "text-ink-2")}>
            <Icon className="mt-0.5 size-3.5 shrink-0" aria-hidden />
            <span>
              {n.text}
              {n.delta ? <span className="tabular-nums"> ({n.delta > 0 ? `+${n.delta}` : `−${Math.abs(n.delta)}`})</span> : null}
            </span>
          </li>
        );
      })}
      {g.base_score !== null ? (
        <li className="text-[12px] text-ink-3 tabular-nums">
          Điểm AI {g.base_score} → {Math.max(0, Math.min(100, g.base_score + g.delta))} sau khi tính nguyên tắc và gu
        </li>
      ) : null}
    </ul>
  );
}
