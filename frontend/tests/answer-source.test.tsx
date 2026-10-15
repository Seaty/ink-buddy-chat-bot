import { render, screen, cleanup } from "@testing-library/react";
import { afterEach, expect, it } from "vitest";
import { AnswerSource } from "../src/features/chat/answer-source";
afterEach(cleanup);
it.each([["qwen/qwen3-14b", "AI"], ["catalog_policy", "กฎระบบ"], ["catalog_template", "Catalog Template"], [undefined, "Catalog Template"]])("labels %s correctly", (model, label) => {
  render(<AnswerSource model={model} />);
  expect(screen.getByLabelText("แหล่งคำตอบ")).toHaveTextContent(label!);
});
