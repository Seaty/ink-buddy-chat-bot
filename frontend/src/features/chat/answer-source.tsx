export function AnswerSource({ model }: { model?: string | null }) {
  const label = !model || model === "catalog_template"
    ? "Catalog Template"
    : model === "catalog_policy" ? "กฎระบบ" : "AI";
  return <small aria-label="แหล่งคำตอบ">{label}</small>;
}
