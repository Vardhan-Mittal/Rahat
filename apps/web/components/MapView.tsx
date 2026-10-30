"use client";

import { useEffect, useRef, useState } from "react";
import type { Map as MLMap, GeoJSONSource, LngLatBoundsLike, MapLayerMouseEvent } from "maplibre-gl";
import type { GdacsEvent, MapLayers, Place, SachetAlert } from "@/lib/types";
import { LEVEL_COLOR, ist } from "@/lib/format";

type Props = {
  places: Place[];
  sachet: SachetAlert[];
  gdacs: GdacsEvent[];
  layers: MapLayers;
  focus: { lat: number; lon: number; key: number } | null;
  onSelect: (id: string) => void;
  onRadar: (state: "live" | "down", note: string) => void;
};

const EMPTY: GeoJSON.FeatureCollection = { type: "FeatureCollection", features: [] };
const reduceMotion = () => typeof window !== "undefined" && window.matchMedia("(prefers-reduced-motion: reduce)").matches;

function circlePolygon(lat: number, lon: number, km: number, n = 48): GeoJSON.Polygon {
  const ring: number[][] = [];
  for (let i = 0; i <= n; i++) {
    const a = (i / n) * 2 * Math.PI;
    ring.push([lon + (km / (111.32 * Math.cos((lat * Math.PI) / 180))) * Math.cos(a), lat + (km / 110.57) * Math.sin(a)]);
  }
  return { type: "Polygon", coordinates: [ring] };
}

export default function MapView({ places, sachet, gdacs, layers, focus, onSelect, onRadar }: Props) {
  const el = useRef<HTMLDivElement>(null);
  const map = useRef<MLMap | null>(null);
  const [ready, setReady] = useState(false);
  const [frames, setFrames] = useState<{ time: number }[]>([]);
  const [frame, setFrame] = useState(0);
  const [playing, setPlaying] = useState(true);
  const onSelectRef = useRef(onSelect);
  useEffect(() => {
    onSelectRef.current = onSelect;
  }, [onSelect]);

  // create the map once
  useEffect(() => {
    let cancelled = false;
    (async () => {
      const maplibregl = await import("maplibre-gl");
      maplibregl.setWorkerUrl("/maplibre-gl-worker.mjs");
      if (cancelled || !el.current) return;
      const m = new maplibregl.Map({
        container: el.current,
        center: [83, 22],
        zoom: 4.1,
        minZoom: 3,
        maxZoom: 16,
        attributionControl: { compact: true },
        style: {
          version: 8,
          sources: {
            sat: { type: "raster", tileSize: 256, maxzoom: 18, attribution: "Imagery © Esri, Maxar, Earthstar Geographics",
              tiles: ["https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}"] },
            lbl: { type: "raster", tileSize: 256, maxzoom: 18, attribution: "Labels © Esri",
              tiles: ["https://server.arcgisonline.com/ArcGIS/rest/services/Reference/World_Boundaries_and_Places/MapServer/tile/{z}/{y}/{x}"] },
          },
          layers: [
            { id: "bg", type: "background", paint: { "background-color": "#060B16" } },
            { id: "sat", type: "raster", source: "sat", paint: { "raster-saturation": -0.45, "raster-brightness-max": 0.42, "raster-contrast": 0.12 } },
            { id: "lbl", type: "raster", source: "lbl", paint: { "raster-opacity": 0.85 } },
          ],
        },
      });
      m.addControl(new maplibregl.NavigationControl({ showCompass: false }), "bottom-right");
      map.current = m;

      m.on("load", async () => {
        const add = (id: string) => m.addSource(id, { type: "geojson", data: EMPTY });
        ["sachet", "zone", "route", "facilities", "places", "origin"].forEach(add);
        m.addLayer({ id: "sachet-fill", type: "fill", source: "sachet", paint: { "fill-color": ["get", "c"], "fill-opacity": 0.07 } });
        m.addLayer({ id: "sachet-line", type: "line", source: "sachet", paint: { "line-color": ["get", "c"], "line-width": 1, "line-opacity": 0.55 } });
        m.addLayer({ id: "zone-fill", type: "fill", source: "zone", paint: { "fill-color": ["get", "c"], "fill-opacity": 0.09 } });
        m.addLayer({ id: "zone-line", type: "line", source: "zone", paint: { "line-color": ["get", "c"], "line-width": 1.5, "line-dasharray": [3, 2] } });
        m.addLayer({ id: "route-case", type: "line", source: "route", layout: { "line-cap": "round", "line-join": "round" }, paint: { "line-color": "#ffffff", "line-width": 8, "line-opacity": 0.9 } });
        m.addLayer({ id: "route", type: "line", source: "route", layout: { "line-cap": "round", "line-join": "round" }, paint: { "line-color": "#1D7BFF", "line-width": 4.5 } });
        m.addLayer({ id: "facilities", type: "circle", source: "facilities", paint: {
          "circle-radius": ["case", ["boolean", ["get", "shelter"], false], 9, ["boolean", ["get", "exposed"], false], 5, 4],
          "circle-color": ["case", ["boolean", ["get", "shelter"], false], "#22C55E", ["==", ["get", "kind"], "hospital"], "#FF6B81", "#9AD0FF"],
          "circle-stroke-color": ["case", ["boolean", ["get", "exposed"], false], "#EF4444", "#06101F"],
          "circle-stroke-width": ["case", ["boolean", ["get", "shelter"], false], 3, ["boolean", ["get", "exposed"], false], 2, 1] } });
        m.addLayer({ id: "places-halo", type: "circle", source: "places", paint: { "circle-radius": ["interpolate", ["linear"], ["zoom"], 3, 10, 8, 18], "circle-color": ["get", "c"], "circle-opacity": 0.22, "circle-blur": 0.4 } });
        m.addLayer({ id: "places", type: "circle", source: "places", paint: { "circle-radius": ["interpolate", ["linear"], ["zoom"], 3, 4, 8, 7], "circle-color": ["get", "c"], "circle-stroke-color": "#06101F", "circle-stroke-width": 1.5 } });
        m.addLayer({ id: "origin", type: "circle", source: "origin", paint: { "circle-radius": 7, "circle-color": "#FB923C", "circle-stroke-color": "#fff", "circle-stroke-width": 2.5 } });

        m.on("click", "places", (e: MapLayerMouseEvent) => { const id = e.features?.[0]?.properties?.id; if (id) onSelectRef.current(String(id)); });
        const popup = (layer: string, html: (p: Record<string, unknown>) => string) =>
          m.on("click", layer, (e: MapLayerMouseEvent) => {
            const p = e.features?.[0]?.properties;
            if (p) new maplibregl.Popup({ closeButton: false }).setLngLat(e.lngLat).setHTML(html(p)).addTo(m);
          });
        const esc = (s: unknown) => String(s ?? "").replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" })[c]!);
        popup("facilities", (p) => `<b>${esc(p.name)}</b><br><span class="mono" style="color:var(--dim)">${esc(p.kind)}${p.elev != null && p.elev !== "null" ? ` · ${esc(p.elev)} m` : ""}${p.exposed ? " · inside zone" : ""}${p.shelter ? " · chosen shelter" : ""}</span>`);
        popup("sachet-fill", (p) => `<b>${esc(p.type)}</b><br>${esc(p.area)}<br><span class="mono" style="color:var(--dim)">${esc(p.source)} · NDMA SACHET</span>`);
        for (const l of ["places", "facilities"]) {
          m.on("mouseenter", l, () => (m.getCanvas().style.cursor = "pointer"));
          m.on("mouseleave", l, () => (m.getCanvas().style.cursor = ""));
        }

        // live rain radar (RainViewer): one raster layer per frame, toggled by opacity
        try {
          const r = await fetch("https://api.rainviewer.com/public/weather-maps.json");
          const d = await r.json();
          const fr = [...(d.radar?.past ?? []), ...(d.radar?.nowcast ?? [])] as { time: number; path: string }[];
          fr.forEach((f, i) => {
            m.addSource(`rv${i}`, { type: "raster", tileSize: 256, maxzoom: 7, attribution: "Radar © RainViewer", tiles: [`${d.host}${f.path}/256/{z}/{x}/{y}/2/1_1.png`] });
            m.addLayer({ id: `rv${i}`, type: "raster", source: `rv${i}`, paint: { "raster-opacity": 0 } }, "sachet-fill");
          });
          setFrames(fr);
          setFrame(fr.length - 1);
          onRadar("live", `${fr.length} frames`);
        } catch (e) {
          onRadar("down", String(e));
        }
        setPlaying(!reduceMotion());
        setReady(true);
      });
    })();
    return () => {
      cancelled = true;
      map.current?.remove();
      map.current = null;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // radar frame visibility + playback
  useEffect(() => {
    const m = map.current;
    if (!ready || !m) return;
    frames.forEach((_, i) => m.getLayer(`rv${i}`) && m.setPaintProperty(`rv${i}`, "raster-opacity", i === frame ? 0.72 : 0));
  }, [frame, frames, ready]);
  useEffect(() => {
    if (!playing || frames.length < 2) return;
    let hold = 0;
    const id = setInterval(() => {
      setFrame((f) => {
        if (f === frames.length - 1 && hold++ < 3) return f;
        hold = 0;
        return (f + 1) % frames.length;
      });
    }, 550);
    return () => clearInterval(id);
  }, [playing, frames]);

  // data layers
  const setData = (id: string, data: GeoJSON.FeatureCollection | GeoJSON.Feature) =>
    (map.current?.getSource(id) as GeoJSONSource | undefined)?.setData(data);

  useEffect(() => {
    if (!ready) return;
    setData("places", { type: "FeatureCollection", features: places.map((p) => ({ type: "Feature", properties: { id: p.id, c: LEVEL_COLOR[p.level] }, geometry: { type: "Point", coordinates: [p.lon, p.lat] } })) });
  }, [places, ready]);

  useEffect(() => {
    if (!ready) return;
    setData("sachet", { type: "FeatureCollection", features: sachet.map((a) => ({ type: "Feature", properties: { c: LEVEL_COLOR[a.level], type: a.type, area: a.area, source: a.source }, geometry: circlePolygon(a.lat, a.lon, Math.min(a.radius_km, 250)) })) });
  }, [sachet, ready]);

  useEffect(() => {
    const m = map.current;
    if (!ready || !m) return;
    const markers: { remove: () => void }[] = [];
    (async () => {
      const maplibregl = await import("maplibre-gl");
      for (const g of gdacs) {
        const dot = document.createElement("div");
        dot.className = "cyclone";
        dot.setAttribute("aria-label", g.name);
        markers.push(new maplibregl.Marker({ element: dot }).setLngLat([g.lon, g.lat])
          .setPopup(new maplibregl.Popup({ closeButton: false }).setText(`${g.name} · GDACS ${g.level} alert`)).addTo(m));
      }
    })();
    return () => markers.forEach((mk) => mk.remove());
  }, [gdacs, ready]);

  useEffect(() => {
    if (!ready) return;
    const zone = layers.zone as GeoJSON.FeatureCollection | undefined;
    setData("zone", zone ? { ...zone, features: zone.features.map((f) => ({ ...f, properties: { ...f.properties, c: LEVEL_COLOR[(f.properties?.level as keyof typeof LEVEL_COLOR) ?? "unknown"] } })) } : EMPTY);
    setData("origin", layers.origin ?? EMPTY);
    setData("facilities", layers.facilities ?? EMPTY);
  }, [layers.zone, layers.origin, layers.facilities, ready]);

  // route: draw progressively, then frame it
  useEffect(() => {
    const m = map.current;
    if (!ready || !m) return;
    const route = layers.route as GeoJSON.Feature<GeoJSON.LineString> | undefined;
    if (!route) { setData("route", EMPTY); return; }
    const coords = route.geometry.coordinates;
    let i = reduceMotion() ? coords.length : 2;
    let raf = 0;
    const tick = () => {
      setData("route", { type: "Feature", properties: {}, geometry: { type: "LineString", coordinates: coords.slice(0, i) } });
      if (i < coords.length) { i += Math.max(1, Math.round(coords.length / 60)); raf = requestAnimationFrame(tick); }
    };
    tick();
    let w = 180, e = -180, s = 90, n = -90;
    for (const [x, y] of coords) { w = Math.min(w, x); e = Math.max(e, x); s = Math.min(s, y); n = Math.max(n, y); }
    const wide = window.innerWidth > 900;
    m.fitBounds([[w, s], [e, n]] as LngLatBoundsLike, { padding: wide ? { top: 110, bottom: 130, left: 360, right: 450 } : 40, maxZoom: 15, duration: 900 });
    return () => cancelAnimationFrame(raf);
  }, [layers.route, ready]);

  useEffect(() => {
    if (ready && focus) map.current?.flyTo({ center: [focus.lon, focus.lat], zoom: 12.3, speed: 1.3 });
  }, [focus, ready]);

  const t0 = frames[0] ? ist(new Date(frames[0].time * 1000)) : "–";
  const tn = frames[frame] ? ist(new Date(frames[frame].time * 1000)) + (frame === frames.length - 1 ? " latest" : "") : "radar loading";

  return (
    <>
      <div ref={el} className="map" aria-label="Live map of India with rain radar, official alerts and the response plan" />
      <div className="dock" role="group" aria-label="Rain radar timeline">
        <button className="play" onClick={() => setPlaying((p) => !p)} aria-label={playing ? "Pause radar" : "Play radar"}>
          {playing ? (
            <svg width="14" height="14" viewBox="0 0 14 14" fill="currentColor" aria-hidden="true"><rect x="2" y="1" width="3.5" height="12" rx="1" /><rect x="8.5" y="1" width="3.5" height="12" rx="1" /></svg>
          ) : (
            <svg width="14" height="14" viewBox="0 0 14 14" fill="currentColor" aria-hidden="true"><path d="M3 1.5v11l9-5.5z" /></svg>
          )}
        </button>
        <div>
          <input type="range" id="radar-frame" min={0} max={Math.max(0, frames.length - 1)} step={1} value={frame}
            onChange={(e) => { setPlaying(false); setFrame(+e.target.value); }} aria-label="Radar frame" />
          <div className="ticks"><span>{t0}</span><span style={{ color: "var(--ink)" }}>{tn}</span></div>
        </div>
        <div className="legend"><span>Rain</span><i /></div>
      </div>
    </>
  );
}
