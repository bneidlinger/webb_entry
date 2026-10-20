import type { Route } from "next";

import { portraitAsset } from "@/lib/generated-portraits";
import { portraitForPlanet } from "@/lib/portrait-gallery";

export interface PortraitPreview {
  id: string;
  planet_id: string;
  created_at: string;
  image_url: string;
  thumbnail_url: string;
}

export function latestPortraitQuery(planetIds: string[]) {
  const params = new URLSearchParams();
  for (const id of new Set(planetIds)) params.append("planet_id", id);
  return `/latest?${params}`;
}

export function portraitPreview(name: string, saved?: PortraitPreview | null) {
  if (saved) return {
    href: `/exoplanets/generated/${saved.id}` as Route,
    image: portraitAsset(saved.thumbnail_url),
    label: "Latest generated image",
    saved: true,
  };
  const example = portraitForPlanet(name);
  return example ? {
    href: example.href,
    image: example.image,
    label: `Portrait example ${example.number}`,
    saved: false,
  } : null;
}
