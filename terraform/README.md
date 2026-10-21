# Terraform: Azure AKS for WalmartOpsDevOps

Provisions a resource group, an AKS cluster (autoscaling, Azure CNI with network policy, OIDC and workload identity enabled), a container registry with an AcrPull role assignment, and a Log Analytics workspace.

**Status:** validated in CI with `terraform init -backend=false` and `terraform validate`. It has **not** been applied to a live subscription, because a running AKS cluster costs money. Treat it as reviewed infrastructure code, not a deployed environment.

```powershell
cd terraform
terraform init
terraform plan -var "subscription_id=<your-subscription-id>"
# terraform apply ...   (creates billable resources)
# terraform destroy ... (when finished)
```

Remote state, separate environments and a CI-driven `plan` on pull requests are the natural next steps.