export function AnswerSource({ model }: { model?: string | null }) {
  const label =
    model === "vision_catalog"
      ? "Vision"
      : !model || model === "catalog_template"
        ? "Catalog Template"
        : model === "catalog_policy"
          ? "กฎระบบ"
          : "AI";
  return (
    <small className="answer-source" aria-label="แหล่งคำตอบ">
      {label}
    </small>
  );
}
