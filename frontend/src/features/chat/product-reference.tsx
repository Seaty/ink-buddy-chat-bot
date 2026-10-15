import type { ProductReference } from "@/lib/types";

export function ProductReferenceCard({ product: p, variant = false }: { product: ProductReference; variant?: boolean }) {
  const publicUrl = (url?: string | null) => Boolean(url && /^https?:\/\//i.test(url));
  return <div className="card">
    {variant && <small>สีอื่นของรุ่นเดียวกัน</small>}
    <strong>{p.name}</strong>
    <p>{p.price !== null ? `${p.price} ${p.currency ?? ""}` : "ไม่มีข้อมูลราคา"}</p>
    {p.selling_unit && <p>หน่วยราคา: {p.selling_unit}{p.pack_quantity && p.pack_quantity > 1 ? ` (${p.pack_quantity} ชิ้น)` : ""}</p>}
    {p.ink_color && <p>สีหมึก: {p.ink_color}</p>}
    {p.body_color && <p>สีด้าม: {p.body_color}</p>}
    {p.price_basis === "excludes_vat" && <p>ราคาไม่รวม VAT ตาม catalog/demo</p>}
    {p.price_verification?.startsWith("user_assumed") && <small>ฐานภาษีเป็นสมมติฐานสำหรับส่งงาน</small>}
    {p.availability && <p>สถานะตาม catalog: {p.availability}</p>}
    {publicUrl(p.source_ref) && <p><a href={p.source_ref!} target="_blank" rel="noopener noreferrer">แหล่งข้อมูลสินค้า</a></p>}
    {publicUrl(p.price_source_ref) && <p><a href={p.price_source_ref!} target="_blank" rel="noopener noreferrer">แหล่งข้อมูลราคา</a></p>}
    {p.variants?.length ? <section aria-label="สีอื่นของรุ่นเดียวกัน">
      {p.variants.map(v => <ProductReferenceCard key={v.id} product={v} variant />)}
    </section> : null}
  </div>;
}
