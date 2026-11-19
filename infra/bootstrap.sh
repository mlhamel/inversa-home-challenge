#!/usr/bin/env bash
# One-time project bootstrap — run with a billing-enabled account (Owner), not the deployer.
#   PROJECT_ID=inversa-home-challenge REGION=northamerica-northeast1 ./infra/bootstrap.sh
set -euo pipefail

PROJECT_ID="${PROJECT_ID:-inversa-home-challenge}"
REGION="${REGION:-northamerica-northeast1}"
TFSTATE_BUCKET="${PROJECT_ID}-tfstate"
AR_REPO="inversa"
DEPLOY_SA_ID="inversa-deployer"
POOL_ID="github"
PROVIDER_ID="github-actions"

GITHUB_REPO="$(git remote get-url origin | sed -E 's#^.*github\.com[:/]##; s#\.git$##')"

step() { echo "==> $*"; }
already() { [ "$1" -eq 0 ]; }

gcloud config set project "$PROJECT_ID"

step "enabling APIs"
gcloud services enable \
  cloudresourcemanager.googleapis.com \
  serviceusage.googleapis.com \
  iam.googleapis.com \
  run.googleapis.com \
  storage.googleapis.com \
  cloudscheduler.googleapis.com \
  artifactregistry.googleapis.com \
  secretmanager.googleapis.com \
  iamcredentials.googleapis.com \
  sts.googleapis.com

step "tfstate bucket gs://$TFSTATE_BUCKET (versioned)"
if ! gcloud storage buckets describe "gs://$TFSTATE_BUCKET" >/dev/null 2>&1; then
  gcloud storage buckets create "gs://$TFSTATE_BUCKET" \
    --location="$REGION" --uniform-bucket-level-access
  gcloud storage buckets update "gs://$TFSTATE_BUCKET" --versioning
else
  echo "exists, skipping"
fi

step "artifact registry repo $AR_REPO"
gcloud artifacts repositories describe "$AR_REPO" --location="$REGION" >/dev/null 2>&1 \
  || gcloud artifacts repositories create "$AR_REPO" \
    --repository-format=docker --location="$REGION"

step "workload identity pool $POOL_ID / provider $PROVIDER_ID ($GITHUB_REPO, refs/heads/main only)"
gcloud iam workload-identity-pools describe "$POOL_ID" --location=global >/dev/null 2>&1 \
  || gcloud iam workload-identity-pools create "$POOL_ID" \
    --location=global --display-name="GitHub Actions pool"

gcloud iam workload-identity-pools providers describe "$PROVIDER_ID" \
  --location=global --workload-identity-pool="$POOL_ID" >/dev/null 2>&1 \
  || gcloud iam workload-identity-pools providers create-oidc "$PROVIDER_ID" \
    --location=global \
    --workload-identity-pool="$POOL_ID" \
    --issuer-uri="https://token.actions.githubusercontent.com" \
    --attribute-mapping="google.subject=assertion.sub,attribute.repository=assertion.repository,attribute.ref=assertion.ref" \
    --attribute-condition="assertion.repository == \"$GITHUB_REPO\" && assertion.ref == \"refs/heads/main\""

step "deployer service account $DEPLOY_SA_ID"
DEPLOY_SA_EMAIL="$DEPLOY_SA_ID@$PROJECT_ID.iam.gserviceaccount.com"
gcloud iam service-accounts describe "$DEPLOY_SA_EMAIL" >/dev/null 2>&1 \
  || gcloud iam service-accounts create "$DEPLOY_SA_ID" \
    --display-name="Inversa deployer: pushes images and applies Terraform"

for role in \
  roles/run.admin \
  roles/cloudscheduler.admin \
  roles/artifactregistry.writer \
  roles/storage.admin \
  roles/secretmanager.admin \
  roles/serviceusage.serviceUsageAdmin \
  roles/resourcemanager.projectIamAdmin \
  roles/iam.serviceAccountAdmin \
  roles/iam.serviceAccountUser; do
  step "grant $role to $DEPLOY_SA_EMAIL"
  gcloud projects add-iam-policy-binding "$PROJECT_ID" \
    --member="serviceAccount:$DEPLOY_SA_EMAIL" --role="$role" --quiet >/dev/null
  echo "granted"
done

step "allow WIF pool to impersonate $DEPLOY_SA_EMAIL"
PROJECT_NUMBER="$(gcloud projects describe "$PROJECT_ID" --format='value(projectNumber)')"
EXPECTED_MEMBER="principalSet://iam.googleapis.com/projects/$PROJECT_NUMBER/locations/global/workloadIdentityPools/$POOL_ID/attribute.repository/$GITHUB_REPO"
POLICY_MEMBERS="$(gcloud iam service-accounts get-iam-policy "$DEPLOY_SA_EMAIL" \
  --project="$PROJECT_ID" --format='value(bindings.members)')"
if grep -qxF -- "$EXPECTED_MEMBER" <<< "$POLICY_MEMBERS"; then
  echo "already granted, skipping"
else
  gcloud iam service-accounts add-iam-policy-binding "$DEPLOY_SA_EMAIL" \
    --project="$PROJECT_ID" \
    --role="roles/iam.workloadIdentityUser" \
    --member="$EXPECTED_MEMBER" \
    --quiet >/dev/null
  echo "granted"
fi

PROVIDER_NAME="$(gcloud iam workload-identity-pools providers describe "$PROVIDER_ID" \
  --location=global --workload-identity-pool="$POOL_ID" --format='value(name)')"

step "repository configuration (set with gh, from the repo root)"
echo "  gh variable set GCP_WIF_PROVIDER   --body '$PROVIDER_NAME'"
echo "  gh variable set GCP_DEPLOY_SA      --body '$DEPLOY_SA_EMAIL'"
echo "  gh secret set FIRMS_MAP_KEY        --body '<NASA FIRMS MAP_KEY>'"
echo "  gh secret set OPENAQ_API_KEY       --body '<OpenAQ API key>'"
echo "  gh secret set AGENT_API_KEY        --body '<LLM API key>'"
echo "  gh variable set AGENT_MODEL        --body 'openai:gpt-4o-mini'   # optional override"
echo
echo "then: make infra-init && make infra-plan && make infra-apply   # or just merge to main"
