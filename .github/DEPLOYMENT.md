# Production Deployment Guide

## GitHub Actions Workflow

The production deployment workflow (`deploy-prod.yml`) has two stages:
1. **Build Stage**: Automatically builds and pushes Docker image to ACR (runs on push)
2. **Deploy Stage**: Requires **manual approval** before deploying to production

When code is pushed to main/master/production branch, the workflow will:
- ✅ Automatically build the Docker image
- ✅ Push the image to Azure Container Registry
- ⏸️ **Wait for manual approval** before deploying to production

## Required GitHub Secrets

Configure the following secrets in your GitHub repository settings (Settings → Secrets and variables → Actions):

### Azure Authentication Secrets

1. **AZURE_CLIENT_ID**
   - Azure Service Principal Client ID
   - Used for ACR login and Azure authentication

2. **AZURE_CLIENT_SECRET**
   - Azure Service Principal Client Secret
   - Used for ACR login and Azure authentication

3. **AZURE_TENANT_ID**
   - Azure Tenant ID
   - Used for Azure authentication

4. **AZURE_SUBSCRIPTION_ID**
   - Azure Subscription ID
   - Used for Azure Web App deployment

## How to Get Azure Credentials

### Option 1: Using Azure CLI

```bash
# Login to Azure
az login

# Create a service principal (if not exists)
az ad sp create-for-rbac --name "github-actions-rivollo-prod" \
  --role contributor \
  --scopes /subscriptions/{subscription-id} \
  --sdk-auth

# The output will contain:
# - clientId (use as AZURE_CLIENT_ID)
# - clientSecret (use as AZURE_CLIENT_SECRET)
# - tenantId (use as AZURE_TENANT_ID)
# - subscriptionId (use as AZURE_SUBSCRIPTION_ID)
```

### Option 2: Using Azure Portal

1. Go to Azure Portal → Azure Active Directory → App registrations
2. Create a new registration or use existing
3. Go to Certificates & secrets → Create a new client secret
4. Note down:
   - Application (client) ID → `AZURE_CLIENT_ID`
   - Directory (tenant) ID → `AZURE_TENANT_ID`
   - Client secret value → `AZURE_CLIENT_SECRET`
   - Subscription ID → `AZURE_SUBSCRIPTION_ID` (from Subscriptions)

## Setting Up Manual Approval

Before the workflow can work, you need to configure the `production` environment with required reviewers:

1. Go to your repository → **Settings** → **Environments**
2. Click **New environment** (or edit existing "production" environment)
3. Name it: `production`
4. Under **Required reviewers**, add the users/teams who should approve deployments
5. (Optional) Set a **Wait timer** if you want a delay before deployment
6. Click **Save protection rules**

### Required Reviewers

Add users or teams who can approve production deployments. These reviewers will receive notifications when a deployment is pending approval.

## Workflow Triggers

The workflow runs automatically on:
- Push to `main` branch
- Push to `master` branch
- Push to `production` branch
- Manual trigger via GitHub Actions UI (workflow_dispatch)

## Deployment Process

### Automatic Build

When code is pushed:
1. ✅ Workflow starts automatically
2. ✅ Builds Docker image
3. ✅ Pushes image to ACR
4. ⏸️ **Pauses and waits for approval**

### Manual Approval

When the build completes, you'll see:
1. Go to **Actions** tab in GitHub
2. Find the running workflow
3. You'll see a "Review deployments" button
4. Click it to see the pending deployment
5. Review the changes and image details
6. Click **Approve and deploy** or **Reject**

### Manual Deployment

You can also manually trigger the entire workflow:

1. Go to GitHub Actions tab
2. Select "Deploy to Production" workflow
3. Click "Run workflow"
4. Optionally specify a custom Docker image tag
5. Click "Run workflow"
6. After build completes, approve the deployment

## Image Tagging

- **Automatic (on push)**: Uses short commit SHA (7 characters)
- **Manual**: Uses the tag you specify (default: `latest`)
- **Always**: Also tags as `latest` for easy reference

## Deployment Stages

### Stage 1: Build (Automatic)
1. ✅ Checkout code
2. ✅ Set up Docker Buildx
3. ✅ Log in to Azure Container Registry (ACR)
4. ✅ Build Docker image with caching
5. ✅ Push image to ACR with tags
6. ⏸️ **Wait for approval**

### Stage 2: Deploy (Requires Approval)
1. ⏳ **Manual approval required** (via GitHub UI)
2. ✅ Log in to Azure
3. ✅ Deploy to Azure Web App
4. ✅ Deployment summary

## Environment Variables

The workflow uses these environment variables (configured in the workflow file):

- `AZURE_WEBAPP_NAME`: `api-service-production`
- `ACR_LOGIN_SERVER`: `rivolloprodacr.azurecr.io`
- `IMAGE_NAME`: `rivollo-prod-portal-api`
- `REGISTRY_NAME`: `rivolloprodacr`

## Troubleshooting

### Authentication Errors

- Verify all Azure secrets are correctly set in GitHub
- Check that the service principal has proper permissions:
  - Contributor role on the subscription/resource group
  - AcrPush role on the ACR registry

### Build Errors

- Check Dockerfile syntax
- Verify all dependencies in `pyproject.toml` and `uv.lock`
- Check build logs in GitHub Actions

### Deployment Errors

- Verify Web App name matches `AZURE_WEBAPP_NAME`
- Check that the Web App is configured to use the correct ACR
- Verify the image tag exists in ACR

## Azure Web App Configuration

Ensure your Azure Web App is configured with:

- **Container Registry**: `rivolloprodacr.azurecr.io`
- **Image**: `rivollo-prod-portal-api:latest` (or specific tag)
- **Port**: `8080` (as defined in Dockerfile)
- **Environment Variables**: Set required app settings (DATABASE_URL, JWT_SECRET, etc.)

## Approval Notifications

When a deployment is pending approval:
- Reviewers will receive email notifications
- GitHub will show a banner in the Actions tab
- The workflow run will show "Waiting for approval" status

## Monitoring

After deployment, monitor:
- GitHub Actions workflow logs
- Azure Web App logs
- Application health endpoints: `/health`, `/health/ready`, `/health/live`

## Troubleshooting Approval Issues

### Approval Button Not Showing

- Verify the `production` environment exists in repository settings
- Check that you're added as a required reviewer
- Ensure you have the necessary repository permissions

### Cannot Approve Deployment

- Verify you're logged into GitHub
- Check that you're in the list of required reviewers
- Ensure the workflow hasn't been cancelled

