export interface TimelineRow {
  hour_bucket: string;
  active_fires_count: number;
  avg_pm25: number | null;
  max_pm25: number | null;
  active_stations: number;
  stale_stations: number;
}

export interface SnapshotFireRow {
  fire_id: string;
  observed_at: string;
  lat: number;
  lon: number;
  frp: number | null;
  confidence: string;
  satellite: string;
}

export interface SnapshotStationRow {
  station_id: string;
  station_name: string;
  lat: number;
  lon: number;
  pm25: number | null;
  quality_flag: string;
  observed_at: string;
}

export interface SnapshotWindRow {
  grid_id: string;
  observed_at: string;
  lat: number;
  lon: number;
  wind_speed_10m: number | null;
  wind_direction_10m: number | null;
  boundary_layer_height: number | null;
}

export interface Snapshot {
  fires: SnapshotFireRow[];
  stations: SnapshotStationRow[];
  wind: SnapshotWindRow[];
}
