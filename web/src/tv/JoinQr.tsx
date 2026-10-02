// The QR the phones read: <origin>/j/<code>. The origin is the TV's own, unless the TV runs on localhost, which a
// phone can't reach: then PUBLIC_BASE_URL (docs/ARCHITECTURE.md, "Como alguém entra").
import QRCode from "qrcode";
import { useEffect, useState } from "react";
import type { ActiveRoom } from "../api";

export function joinUrl(room: ActiveRoom): { url: string; unreachable: boolean } {
  const local = ["localhost", "127.0.0.1", "[::1]"].includes(location.hostname);
  const origin = local && room.public_base_url ? room.public_base_url : location.origin;
  return { url: `${origin}${room.join_path}`, unreachable: local && !room.public_base_url };
}

export function JoinQr({ room, size, caption }: { room: ActiveRoom; size: number; caption?: string }) {
  const { url, unreachable } = joinUrl(room);
  const [image, setImage] = useState<string | null>(null);
  useEffect(() => {
    QRCode.toDataURL(url, { margin: 1, width: size * 2 }).then(setImage, () => setImage(null));
  }, [url, size]);

  return (
    <div className="flex flex-col items-center gap-2 text-center">
      {caption && <p className="max-w-[12rem] text-sm font-semibold text-amber-300">{caption}</p>}
      {image && <img src={image} alt={`QR Code para ${url}`} width={size} height={size} className="rounded-lg" />}
      <p className="text-sm text-zinc-400">
        Sala <span className="font-bold tracking-widest text-zinc-100">{room.code}</span>
      </p>
      {unreachable && size > 100 && (
        <p className="max-w-xs text-xs text-amber-300">
          A TV está em localhost: defina PUBLIC_BASE_URL no .env para o QR funcionar nos celulares.
        </p>
      )}
    </div>
  );
}
