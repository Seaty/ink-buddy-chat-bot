"use client";
import { useEffect, useState } from "react";
import { api, errorText } from "@/lib/api";

export function MessageImage({ imageId }: { imageId: string }) {
  const [url, setUrl] = useState("");
  const [error, setError] = useState("");
  const [version, setVersion] = useState(0);
  useEffect(() => {
    let active = true;
    let objectUrl = "";
    setUrl("");
    setError("");
    api
      .imageContent(imageId)
      .then((blob) => {
        if (active) {
          objectUrl = URL.createObjectURL(blob);
          setUrl(objectUrl);
        }
      })
      .catch((e) => {
        if (active) setError(errorText(e));
      });
    return () => {
      active = false;
      if (objectUrl) URL.revokeObjectURL(objectUrl);
    };
  }, [imageId, version]);
  return url ? (
    <img className="message-image" src={url} alt="รูปที่แนบกับข้อความ" />
  ) : error ? (
    <div className="image-load-error">
      <span>{error}</span>
      <button onClick={() => setVersion((v) => v + 1)}>โหลดรูปใหม่</button>
    </div>
  ) : (
    <p className="muted text-sm" role="status">
      กำลังโหลดรูป…
    </p>
  );
}
