import { render, screen, cleanup } from "@testing-library/react";
import { describe, it, expect, afterEach } from "vitest";
import { ProductReferenceCard } from "../src/features/chat/product-reference";
import type { ProductReference } from "../src/lib/types";

const product: ProductReference = {id:"p1",sku:"sku",name:"Pen",price:"50",currency:"THB",availability:null,
  source_ref:"https://catalog.test/p",price_source_ref:"https://price.test/p",selling_unit:"ด้าม",price_basis:"excludes_vat"};
afterEach(cleanup);
describe("catalog references",()=>{
  it("separates product/price sources and alternative colors",()=>{
    render(<ProductReferenceCard product={{...product,variants:[{...product,id:"p2",name:"Pen red"}]}}/>);
    expect(screen.getAllByRole("link",{name:"แหล่งข้อมูลราคา"})[0].getAttribute("href")).toBe("https://price.test/p");
    expect(screen.getByLabelText("สีอื่นของรุ่นเดียวกัน")).toBeTruthy();
    expect(screen.getByText("Pen red")).toBeTruthy();
  });
  it("renders untrusted names as text and never links javascript",()=>{
    render(<ProductReferenceCard product={{...product,name:"<script>unsafe</script>",source_ref:"javascript:alert(1)",price_source_ref:null}}/>);
    expect(screen.getByText("<script>unsafe</script>")).toBeTruthy();
    expect(screen.queryByRole("link")).toBeNull();
  });
});
