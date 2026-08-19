export interface ExperimentSummary {
  id: string;
  name: string | null;
  mission_id: string | null;
  started_at_ms: number | null;
  ended_at_ms: number | null;
  leader_id: string | null;
  follower_id: string | null;
  llm_enabled: number;
  llm_provider: string | null;
  git_commit: string | null;
  software_version: string | null;
  status: string;
}

export interface ExperimentMetrics {
  tracking_rmse_m: number | null;
  mean_tracking_error_m: number | null;
  max_tracking_error_m: number | null;
  p95_tracking_error_m: number | null;
  mean_separation_m: number | null;
  max_separation_m: number | null;
  mean_latency_ms: number | null;
  max_latency_ms: number | null;
  mission_duration_s: number | null;
  warning_count: number;
  critical_event_count: number;
  role_switch_count: number;
  mean_stabilization_time_s: number | null;
  llm_recommendation_count: number;
  mean_llm_latency_ms: number | null;
}

export interface ExperimentDetail {
  experiment: ExperimentSummary;
  metrics: ExperimentMetrics;
}

export interface CoordinationSampleRow {
  id: number;
  experiment_id: string;
  timestamp_ms: number;
  state_json: string;
}
