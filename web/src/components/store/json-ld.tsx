/** Dữ liệu có cấu trúc schema.org (e10) cho máy tìm kiếm và trợ lý mua sắm AI. */
export function JsonLd({ data }: { data: Record<string, unknown> | Record<string, unknown>[] }) {
  // Chặn đóng thẻ script sớm khi nội dung có "</".
  const json = JSON.stringify(data).replace(/</g, "\\u003c");
  return <script type="application/ld+json" dangerouslySetInnerHTML={{ __html: json }} />;
}
