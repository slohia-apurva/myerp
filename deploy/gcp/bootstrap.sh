#!/usr/bin/env bash
# One-time setup of a MyERP Google Cloud project. Run it in Cloud Shell as a
# project Owner:
#
#   bash bootstrap.sh myerp-staging
#
# It is safe to run again: every step checks before creating.
#
# What it does:
#   1. Checks billing is linked.
#   2. Turns on the Google Cloud services MyERP uses.
#   3. Creates a bucket for Terraform state (versioned, in Mumbai).
#   4. Creates two service accounts:
#        myerp-deployer  used by GitHub Actions to push images and deploy
#        myerp-runtime   the identity the running app uses
#   5. Lets GitHub Actions act as myerp-deployer without any stored key
#      (Workload Identity Federation), and only for pushes to the main branch
#      of the slohia-apurva/myerp repository.
#   6. Prints the values to put into GitHub repository variables.
#
# It creates no database or servers, so it costs nothing on its own.
# Infrastructure (Cloud SQL, Cloud Run, Redis, storage) comes from Terraform.

set -euo pipefail

PROJECT_ID="${1:?Usage: bash bootstrap.sh <project-id>, e.g. myerp-staging}"
REGION="asia-south1"                # Mumbai
GITHUB_REPO="slohia-apurva/myerp"
GITHUB_REPO_ID="1445393911"         # numeric id: survives a repo rename, blocks look-alikes
POOL_ID="github"
PROVIDER_ID="github-actions"
DEPLOYER_SA="myerp-deployer"
RUNTIME_SA="myerp-runtime"
STATE_BUCKET="${PROJECT_ID}-tfstate"

say() { printf '\n==> %s\n' "$*"; }

say "Using project ${PROJECT_ID}"
gcloud config set project "${PROJECT_ID}" >/dev/null
PROJECT_NUMBER="$(gcloud projects describe "${PROJECT_ID}" --format='value(projectNumber)')"

say "Checking billing"
if [[ "$(gcloud billing projects describe "${PROJECT_ID}" --format='value(billingEnabled)')" != "True" ]]; then
  echo "Billing is not linked to ${PROJECT_ID}. Link it under Billing > Account management, then re-run."
  exit 1
fi

say "Turning on services (takes a minute or two)"
gcloud services enable \
  run.googleapis.com \
  sqladmin.googleapis.com \
  redis.googleapis.com \
  compute.googleapis.com \
  servicenetworking.googleapis.com \
  artifactregistry.googleapis.com \
  secretmanager.googleapis.com \
  iam.googleapis.com \
  iamcredentials.googleapis.com \
  sts.googleapis.com \
  cloudresourcemanager.googleapis.com \
  cloudscheduler.googleapis.com \
  certificatemanager.googleapis.com \
  logging.googleapis.com \
  monitoring.googleapis.com \
  storage.googleapis.com

say "Terraform state bucket gs://${STATE_BUCKET}"
if ! gcloud storage buckets describe "gs://${STATE_BUCKET}" >/dev/null 2>&1; then
  gcloud storage buckets create "gs://${STATE_BUCKET}" \
    --location="${REGION}" --uniform-bucket-level-access --public-access-prevention
fi
gcloud storage buckets update "gs://${STATE_BUCKET}" --versioning >/dev/null

ensure_sa() {
  local name="$1" display="$2"
  local email="${name}@${PROJECT_ID}.iam.gserviceaccount.com"
  if ! gcloud iam service-accounts describe "${email}" >/dev/null 2>&1; then
    gcloud iam service-accounts create "${name}" --display-name="${display}"
  fi
}

say "Service accounts"
ensure_sa "${DEPLOYER_SA}" "MyERP deployer (GitHub Actions)"
ensure_sa "${RUNTIME_SA}" "MyERP app runtime"
DEPLOYER_EMAIL="${DEPLOYER_SA}@${PROJECT_ID}.iam.gserviceaccount.com"
RUNTIME_EMAIL="${RUNTIME_SA}@${PROJECT_ID}.iam.gserviceaccount.com"

# Deployer: push images and roll out new revisions/jobs. It cannot change
# infrastructure, IAM or billing; those stay with Terraform run by an Owner.
for role in roles/run.developer roles/artifactregistry.writer; do
  gcloud projects add-iam-policy-binding "${PROJECT_ID}" \
    --member="serviceAccount:${DEPLOYER_EMAIL}" --role="${role}" \
    --condition=None >/dev/null
done
# The deployer may run things as the runtime account, and nothing else.
gcloud iam service-accounts add-iam-policy-binding "${RUNTIME_EMAIL}" \
  --member="serviceAccount:${DEPLOYER_EMAIL}" --role="roles/iam.serviceAccountUser" >/dev/null

# Runtime: reach Cloud SQL, read its own secrets, write logs and metrics.
for role in roles/cloudsql.client roles/secretmanager.secretAccessor \
            roles/logging.logWriter roles/monitoring.metricWriter; do
  gcloud projects add-iam-policy-binding "${PROJECT_ID}" \
    --member="serviceAccount:${RUNTIME_EMAIL}" --role="${role}" \
    --condition=None >/dev/null
done

say "Keyless GitHub access (Workload Identity Federation)"
if ! gcloud iam workload-identity-pools describe "${POOL_ID}" --location=global >/dev/null 2>&1; then
  gcloud iam workload-identity-pools create "${POOL_ID}" \
    --location=global --display-name="GitHub Actions"
fi
CONDITION="assertion.repository_id=='${GITHUB_REPO_ID}' && assertion.ref=='refs/heads/main'"
if ! gcloud iam workload-identity-pools providers describe "${PROVIDER_ID}" \
    --location=global --workload-identity-pool="${POOL_ID}" >/dev/null 2>&1; then
  gcloud iam workload-identity-pools providers create-oidc "${PROVIDER_ID}" \
    --location=global --workload-identity-pool="${POOL_ID}" \
    --display-name="myerp main branch" \
    --issuer-uri="https://token.actions.githubusercontent.com" \
    --attribute-mapping="google.subject=assertion.sub,attribute.repository=assertion.repository,attribute.repository_id=assertion.repository_id,attribute.ref=assertion.ref" \
    --attribute-condition="${CONDITION}"
fi
gcloud iam service-accounts add-iam-policy-binding "${DEPLOYER_EMAIL}" \
  --role="roles/iam.workloadIdentityUser" \
  --member="principalSet://iam.googleapis.com/projects/${PROJECT_NUMBER}/locations/global/workloadIdentityPools/${POOL_ID}/attribute.repository_id/${GITHUB_REPO_ID}" \
  >/dev/null

PROVIDER_NAME="projects/${PROJECT_NUMBER}/locations/global/workloadIdentityPools/${POOL_ID}/providers/${PROVIDER_ID}"

say "Done. Send these values back (they are not secrets):"
cat <<EOF

GCP_PROJECT_ID=${PROJECT_ID}
GCP_REGION=${REGION}
GCP_WIF_PROVIDER=${PROVIDER_NAME}
GCP_DEPLOYER_SA=${DEPLOYER_EMAIL}
GCP_RUNTIME_SA=${RUNTIME_EMAIL}
TF_STATE_BUCKET=${STATE_BUCKET}
EOF
