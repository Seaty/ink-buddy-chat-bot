import type { ProductReference } from "@/lib/types";

const publicUrl = (url?: string | null) =>
  Boolean(url && /^https?:\/\//i.test(url));
function Price({ product: p }: { product: ProductReference }) {
  if (p.price == null)
    return <span className="product-price unavailable">ยังไม่มีราคา</span>;
  const amount = Number(p.price);
  return (
    <span className="product-price">
      {Number.isFinite(amount)
        ? amount.toLocaleString("th-TH", { maximumFractionDigits: 2 })
        : p.price}
      <span className="product-currency">
        {p.currency === "THB" ? "บาท" : p.currency}
      </span>
    </span>
  );
}
export function ProductReferenceCard({
  product: p,
  variant = false,
  position,
}: {
  product: ProductReference;
  variant?: boolean;
  position?: number;
}) {
  return (
    <div className={`product-card ${variant ? "is-variant" : ""}`}>
      <div className="product-card-topline">
        <span className="product-kind">
          {variant
            ? "สีอื่นของรุ่นเดียวกัน"
            : position
              ? `ตัวเลือกที่ ${position}`
              : "ตัวเลือกสำหรับคุณ"}
        </span>
        <span aria-hidden="true" className="product-symbol">
          ✎
        </span>
      </div>
      <h3 className="product-title">{p.name}</h3>
      <div className="product-pricing">
        <Price product={p} />
        {p.selling_unit && (
          <span className="product-unit">
            / {p.selling_unit}
            {p.pack_quantity && p.pack_quantity > 1
              ? ` (${p.pack_quantity} ชิ้น)`
              : ""}
          </span>
        )}
      </div>
      {(p.ink_color || p.body_color) && (
        <div className="product-attributes">
          {p.ink_color && (
            <span>
              หมึก<span>{p.ink_color}</span>
            </span>
          )}
          {p.body_color && (
            <span>
              ด้าม<span>{p.body_color}</span>
            </span>
          )}
        </div>
      )}
      {p.availability && (
        <p className="product-availability">
          สถานะตามข้อมูลสินค้า: {p.availability}
        </p>
      )}
      {(p.price_basis || p.sku) && (
        <details className="product-details">
          <summary>รายละเอียดเพิ่มเติม</summary>
          {p.sku && <p>รหัสสินค้า: {p.sku}</p>}
          {p.price_basis === "excludes_vat" && (
            <p>ราคาไม่รวม VAT ตามข้อมูลที่ใช้ในโปรเจกต์</p>
          )}
          {p.price_verification?.startsWith("user_assumed") && (
            <p>ฐานภาษีเป็นสมมติฐานสำหรับส่งงาน</p>
          )}
        </details>
      )}
      {(publicUrl(p.source_ref) || publicUrl(p.price_source_ref)) && (
        <div className="product-sources">
          {publicUrl(p.source_ref) && (
            <a href={p.source_ref!} target="_blank" rel="noopener noreferrer">
              แหล่งข้อมูลสินค้า<span aria-hidden="true">↗</span>
            </a>
          )}
          {publicUrl(p.price_source_ref) && (
            <a
              href={p.price_source_ref!}
              target="_blank"
              rel="noopener noreferrer"
            >
              แหล่งข้อมูลราคา<span aria-hidden="true">↗</span>
            </a>
          )}
        </div>
      )}
      {p.variants?.length ? (
        <section
          className="product-variants"
          aria-label="สีอื่นของรุ่นเดียวกัน"
        >
          <div className="variant-heading">
            <span aria-hidden="true">◉</span> สีอื่นที่เลือกได้
            <span className="variant-count">{p.variants.length}</span>
          </div>
          {p.variants.map((v) => (
            <ProductReferenceCard key={v.id} product={v} variant />
          ))}
        </section>
      ) : null}
    </div>
  );
}
