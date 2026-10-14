"use client";

import { useEffect, useState } from "react";
import { authenticatedResourceUrl } from "../lib/api";

export function ProtectedImage({
  url,
  alt,
}: {
  url?: string | null;
  alt: string;
}) {
  const [src, setSrc] = useState("");
  useEffect(() => {
    let objectUrl: string | undefined;
    let active = true;
    setSrc("");
    if (!url) return;
    authenticatedResourceUrl(url).then((loaded) => {
      if (loaded.startsWith("blob:")) objectUrl = loaded;
      if (active) setSrc(loaded);
    }).catch(() => setSrc(""));
    return () => {
      active = false;
      if (objectUrl) URL.revokeObjectURL(objectUrl);
    };
  }, [url]);
  return src ? <img src={src} alt={alt} /> : null;
}

export function ProtectedFileLink({
  url,
  children,
  className,
}: {
  url?: string | null;
  children: React.ReactNode;
  className?: string;
}) {
  const [error, setError] = useState("");
  return (
    <a
      className={className}
      href="#"
      onClick={async (event) => {
        event.preventDefault();
        if (!url) return;
        setError("");
        const popup = window.open("about:blank", "_blank");
        if (!popup) {
          setError("Разрешите всплывающие окна, чтобы открыть файл.");
          return;
        }
        popup.opener = null;
        try {
          const resourceUrl = await authenticatedResourceUrl(url);
          popup.location.href = resourceUrl;
          window.setTimeout(() => URL.revokeObjectURL(resourceUrl), 60_000);
        } catch {
          popup.close();
          setError("Не удалось открыть файл.");
        }
      }}
    >
      {children}
      {error && <span role="alert">{error}</span>}
    </a>
  );
}
