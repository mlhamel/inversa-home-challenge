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
  description = "Ingestion bounding box 'min_lon,min_lat,max_lon,max_lat'."
  default     = "-124.4,36.0,-115.4,42.0"
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
