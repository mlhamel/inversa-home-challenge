variable "project_id" {
  type        = string
  description = "GCP project hosting all Inversa resources."
  default     = "inversa-home-challenge"
}

variable "region" {
  type        = string
  description = "Region shared by the datalake bucket, Artifact Registry, Cloud Run, and Scheduler."
  default     = "northamerica-northeast1"
}

variable "bbox" {
  type        = string
  description = "Study area 'min_lon,min_lat,max_lon,max_lat' fed as REGION_CALIFORNIA to the ingestion and API services."
  default     = "-124.4,36.0,-115.4,42.0"
}

variable "nw_india_bbox" {
  type        = string
  description = "Study area 'min_lon,min_lat,max_lon,max_lat' fed as REGION_NW_INDIA to the ingestion and API services (Punjab–Haryana–Delhi NCR)."
  default     = "74.0,28.2,77.8,31.5"
}

variable "firms_map_key" {
  type        = string
  description = "NASA FIRMS MAP_KEY for the ingestion job."
  default     = ""
  sensitive   = true
}

variable "openaq_api_key" {
  type        = string
  description = "OpenAQ API key for the ingestion job."
  default     = ""
  sensitive   = true
}

variable "agent_api_key" {
  type        = string
  description = "LLM API key used by the PydanticAI agent in web-api."
  default     = ""
  sensitive   = true
}

variable "agent_model" {
  type        = string
  description = "Agent model override (AGENT_MODEL); empty keeps the API default openai:gpt-4o-mini."
  default     = ""
}

variable "agent_base_url" {
  type        = string
  description = "Agent OpenAI-compatible base URL (AGENT_BASE_URL); empty keeps the provider default endpoint."
  default     = ""
}

variable "backend_image" {
  type        = string
  description = "Container image for web-api; empty falls back to the Artifact Registry backend:latest."
  default     = ""
}

variable "frontend_image" {
  type        = string
  description = "Container image for web-ui; empty falls back to the Artifact Registry frontend:latest."
  default     = ""
}

variable "ingestion_image" {
  type        = string
  description = "Container image for ingestion-job; empty falls back to the Artifact Registry ingestion:latest."
  default     = ""
}

variable "web_ui_htpasswd" {
  sensitive   = true
  type        = string
  description = "Basic-auth line gating the demo web-ui: 'demo:<apr1 hash>' from `openssl passwd -apr1 '<password>'`. The built-in default is a throwaway public demo credential (password inversa-demo-2026); override via TF_VAR_web_ui_htpasswd for anything non-throwaway."
  default     = "demo:$apr1$inversa0$VrmCcnUmiKkPG2KuOaybc/"
}
