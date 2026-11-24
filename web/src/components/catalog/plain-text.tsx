import { Fragment } from "react";

/**
 * Hiển thị mô tả dạng markdown đơn giản (đoạn văn, gạch đầu dòng, **đậm**) mà không cần thư viện,
 * và không chèn HTML thô (an toàn với nội dung AI viết).
 */
function inline(text: string) {
  const parts = text.split(/(\*\*[^*]+\*\*)/g);
  return parts.map((p, i) =>
    p.startsWith("**") && p.endsWith("**") ? <strong key={i}>{p.slice(2, -2)}</strong> : <Fragment key={i}>{p}</Fragment>,
  );
}

export function PlainText({ text, className }: { text: string; className?: string }) {
  const blocks = text.trim().split(/\n\s*\n/);
  return (
    <div className={className}>
      {blocks.map((block, i) => {
        const lines = block.split("\n").map((l) => l.trim()).filter(Boolean);
        if (lines.length && lines.every((l) => /^[-*•]\s+/.test(l))) {
          return (
            <ul key={i} className="my-2 list-disc space-y-1 pl-5">
              {lines.map((l, j) => (
                <li key={j}>{inline(l.replace(/^[-*•]\s+/, ""))}</li>
              ))}
            </ul>
          );
        }
        return (
          <p key={i} className="my-2 first:mt-0 last:mb-0">
            {lines.map((l, j) => (
              <Fragment key={j}>
                {j > 0 ? <br /> : null}
                {inline(l.replace(/^[-*•]\s+/, "• "))}
              </Fragment>
            ))}
          </p>
        );
      })}
    </div>
  );
}
