import { useState, type CSSProperties, type ReactNode } from "react";
import {
  FIRE_FILL_ALPHA,
  FIRE_FILL_COLOR,
  FIRE_LOW_CONFIDENCE_ALPHA,
  FIRE_OUTLINE_COLOR,
  OUTLIER_RING_COLOR,
  PM25_AQI_STOPS,
  PM25_NO_DATA_COLOR,
  STALE_RING_COLOR,
  STATION_OUTLINE_COLOR,
  WIND_COLOR,
} from "../lib/theme";

export default function MapLegend() {
  const [open, setOpen] = useState(true);

  return (
    <aside className="absolute bottom-[232px] left-3 z-20 w-64 text-xs">
      <button
        type="button"
        onClick={() => setOpen((value) => !value)}
        aria-expanded={open}
        aria-controls="legend-panel"
        className="flex w-full items-center justify-between rounded-lg panel border px-3 py-1.5 font-semibold hover:bg-white/10"
      >
        Legend
        <span className="text-white/50">{open ? "▾" : "▸"}</span>
      </button>
      {open ? (
        <div
          id="legend-panel"
          className="mt-1.5 max-h-[42dvh] space-y-3 overflow-y-auto rounded-lg panel border px-3 py-2.5"
        >
          <section>
            <h3 className="mb-1 font-semibold text-white/70">
              Air quality · PM2.5 (µg/m³)
            </h3>
            <ul className="space-y-1">
              {PM25_AQI_STOPS.map((stop) => (
                <LegendRow
                  key={stop.label}
                  swatch={
                    <Dot
                      style={{
                        backgroundColor: stop.color,
                        borderColor: rgbCss(STATION_OUTLINE_COLOR),
                      }}
                    />
                  }
                  label={stop.label}
                  detail={stop.range}
                />
              ))}
              <LegendRow
                swatch={<Dot style={{ backgroundColor: PM25_NO_DATA_COLOR, borderColor: rgbCss(STATION_OUTLINE_COLOR) }} />}
                label="No recent reading"
                detail="—"
              />
            </ul>
          </section>
          <section>
            <h3 className="mb-1 font-semibold text-white/70">Station flags</h3>
            <ul className="space-y-1">
              <LegendRow
                swatch={
                  <Dot
                    ring
                    style={{ borderColor: rgbCss(STALE_RING_COLOR) }}
                  />
                }
                label="Stale reading"
                detail="ring · > 2 h old"
              />
              <LegendRow
                swatch={
                  <Dot
                    ring
                    style={{ borderColor: rgbCss(OUTLIER_RING_COLOR) }}
                  />
                }
                label="Statistical outlier"
                detail="ring"
              />
            </ul>
          </section>
          <section>
            <h3 className="mb-1 font-semibold text-white/70">Other layers</h3>
            <ul className="space-y-1">
              <LegendRow
                swatch={
                  <Dot
                    style={{
                      backgroundColor: rgbaCss(
                        FIRE_FILL_COLOR,
                        FIRE_FILL_ALPHA / 255,
                      ),
                      borderColor: rgbCss(FIRE_OUTLINE_COLOR),
                    }}
                  />
                }
                label="Active fire"
                detail="NASA FIRMS"
              />
              <LegendRow
                swatch={
                  <Dot
                    style={{
                      backgroundColor: rgbaCss(
                        FIRE_FILL_COLOR,
                        FIRE_LOW_CONFIDENCE_ALPHA / 255,
                      ),
                      borderColor: rgbCss(FIRE_OUTLINE_COLOR),
                    }}
                  />
                }
                label="Fire · low confidence"
                detail="translucent"
              />
              <LegendRow
                swatch={<span className="text-base leading-none" style={{ color: rgbCss(WIND_COLOR) }}>➔</span>}
                label="Wind vector"
                detail="10 m"
              />
            </ul>
          </section>
        </div>
      ) : null}
    </aside>
  );
}

function LegendRow({
  swatch,
  label,
  detail,
}: {
  swatch: ReactNode;
  label: string;
  detail?: string;
}) {
  return (
    <li className="flex items-center gap-2">
      {swatch}
      <span>{label}</span>
      {detail ? (
        <span className="ml-auto shrink-0 text-white/45">{detail}</span>
      ) : null}
    </li>
  );
}

function Dot({ style, ring }: { style: CSSProperties; ring?: boolean }) {
  return (
    <span
      className={`inline-block shrink-0 rounded-full border ${
        ring ? "size-3 border-2" : "size-3"
      }`}
      style={style}
    />
  );
}

function rgbCss(color: readonly [number, number, number]): string {
  return `rgb(${color[0]}, ${color[1]}, ${color[2]})`;
}

function rgbaCss(
  color: readonly [number, number, number],
  alpha: number,
): string {
  return `rgba(${color[0]}, ${color[1]}, ${color[2]}, ${alpha})`;
}
