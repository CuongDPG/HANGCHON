/**
 * Giọng với khách: trang sản phẩm không gọi người bán là «chị» (người bán xưng «mình», gọi khách «bạn»).
 * Cùng luật với backend (`catalog/textutil.seller_address_issues`, chặn khi đăng): bỏ qua lời trích trong ngoặc
 * «…» / “…” / "…" (lời khách) và chữ như «chịu». Ở đây chỉ để chị thấy và sửa ngay trên bản nháp.
 */

const CHI = /(?<![\p{L}\p{N}_])(?:(anh)\s*\/?\s*)?(chị)(?:\s+(em))?(?![\p{L}\p{N}_])/giu;
const QUOTED = /«[^»\n]*»|“[^”\n]*”|"[^"\n]*"/g;
const SENTENCE_END = /[.!?…\n]/g;

export type VoiceHit = { quote: string; suggestion: string };

function sameCase(word: string, like: string) {
  if (like.length > 1 && like === like.toUpperCase()) return word.toUpperCase();
  return like[0] === like[0].toUpperCase() ? word[0].toUpperCase() + word.slice(1) : word;
}

function fix(m: RegExpMatchArray) {
  if (m[1] || m[3]) return sameCase("bạn", m[0]); // «anh chị», «chị em» = gọi khách
  return sameCase("mình", m[2]); // người bán tự xưng
}

export function sellerAddressIssues(text: string | null | undefined): VoiceHit[] {
  if (!text) return [];
  const masked = text.replace(QUOTED, (q) => " ".repeat(q.length));
  const out: VoiceHit[] = [];
  const seen = new Set<number>();
  for (const m of masked.matchAll(CHI)) {
    const idx = m.index ?? 0;
    let start = 0;
    for (const e of text.slice(0, idx).matchAll(SENTENCE_END)) start = (e.index ?? 0) + 1;
    if (seen.has(start)) continue;
    seen.add(start);
    const rest = text.slice(idx + m[0].length).search(SENTENCE_END);
    const end = rest < 0 ? text.length : idx + m[0].length + rest + 1;
    const raw = text.slice(start, end);
    const lead = raw.length - raw.trimStart().length;
    const sentence = raw.trim();
    const maskedSentence = masked.slice(start + lead, start + lead + sentence.length);
    let suggestion = "";
    let last = 0;
    for (const mm of maskedSentence.matchAll(CHI)) {
      suggestion += sentence.slice(last, mm.index) + fix(mm);
      last = (mm.index ?? 0) + mm[0].length;
    }
    out.push({ quote: sentence, suggestion: suggestion + sentence.slice(last) });
  }
  return out;
}
