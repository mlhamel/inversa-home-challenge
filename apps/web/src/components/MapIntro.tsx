export default function MapIntro() {
  return (
    <aside
      aria-label="About the map"
      className="w-64 rounded-lg panel border px-3 py-2 text-xs text-white/70"
    >
      <p>
        Live wildfire detections (NASA FIRMS), downwind PM2.5 stations
        (OpenAQ), and surface wind (Open-Meteo) for the selected hour — scrub
        the timeline below, or ask the map a question.
      </p>
    </aside>
  );
}
