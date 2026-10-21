variable "subscription_id" {
  description = "Azure subscription ID to deploy into."
  type        = string
}

variable "location" {
  description = "Azure region."
  type        = string
  default     = "centralindia"
}

variable "name_prefix" {
  description = "Prefix used in resource names."
  type        = string
  default     = "walmartops"
}

variable "environment" {
  description = "Environment name (dev, staging, prod)."
  type        = string
  default     = "dev"
}

variable "node_vm_size" {
  description = "VM size for the AKS node pool."
  type        = string
  default     = "Standard_B2s"
}

variable "node_min_count" {
  description = "Minimum nodes (cluster autoscaler)."
  type        = number
  default     = 1
}

variable "node_max_count" {
  description = "Maximum nodes (cluster autoscaler)."
  type        = number
  default     = 3
}

variable "tags" {
  description = "Extra tags applied to all resources."
  type        = map(string)
  default     = {}
}