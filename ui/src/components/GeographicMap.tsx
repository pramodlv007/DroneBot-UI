import { useEffect, useRef } from "react";
import type maplibregl from "maplibre-gl";
import type { RobotState } from "@/types/robot";

// MapLibre is loaded dynamically so its ~200kb bundle only pays rent when
// GEOGRAPHIC mode is actually used. Basemap tiles come from OpenStreetMap
// (free, no API key, no proprietary Google Maps dependency — §5).
const OSM_STYLE: maplibregl.StyleSpecification = {
  version: 8,
  sources: {
    osm: {
      type: "raster",
      tiles: ["https://tile.openstreetmap.org/{z}/{x}/{y}.png"],
      tileSize: 256,
      attribution: "© OpenStreetMap contributors",
    },
  },
  layers: [{ id: "osm", type: "raster", source: "osm" }],
};

interface Props {
  robots: RobotState[];
}

export default function GeographicMap({ robots }: Props) {
  const containerRef = useRef<HTMLDivElement>(null);
  const mapRef = useRef<maplibregl.Map | null>(null);
  const markersRef = useRef<Record<string, maplibregl.Marker>>({});

  useEffect(() => {
    let cancelled = false;

    import("maplibre-gl").then((maplibregl) => {
      if (cancelled || !containerRef.current) return;
      const first = robots.find((r) => r.gps);
      mapRef.current = new maplibregl.Map({
        container: containerRef.current,
        style: OSM_STYLE,
        center: first?.gps ? [first.gps.longitude, first.gps.latitude] : [0, 0],
        zoom: first ? 18 : 2,
      });
      mapRef.current.addControl(new maplibregl.NavigationControl(), "top-right");
    });

    return () => {
      cancelled = true;
      mapRef.current?.remove();
      mapRef.current = null;
      markersRef.current = {};
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    const map = mapRef.current;
    if (!map) return;

    import("maplibre-gl").then((maplibregl) => {
      for (const robot of robots) {
        if (!robot.gps) continue;
        const lngLat: [number, number] = [robot.gps.longitude, robot.gps.latitude];
        let marker = markersRef.current[robot.robot_id];
        if (!marker) {
          const el = document.createElement("div");
          el.style.width = "14px";
          el.style.height = "14px";
          el.style.borderRadius = robot.robot_type === "UAV" ? "3px" : "50%";
          el.style.border = "2px solid #fff";
          el.style.background = robot.health === "CRITICAL" ? "#ff5470" : robot.health === "WARNING" ? "#f5b942" : "#4da3ff";
          marker = new maplibregl.Marker({ element: el }).setLngLat(lngLat).addTo(map);
          markersRef.current[robot.robot_id] = marker;
        } else {
          marker.setLngLat(lngLat);
        }
      }
    });
  }, [robots]);

  return <div ref={containerRef} style={{ width: "100%", height: "100%", borderRadius: 6, overflow: "hidden" }} />;
}
