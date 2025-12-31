# How to Trigger Workflow from VSCode

## Prerequisites

1. **Workflow must be committed and pushed to GitHub**
   - The workflow file must exist in the repository on GitHub
   - It needs to be in the default branch (usually `main` or `master`)
   - Uncommitted local changes won't show up

2. **VSCode GitHub Actions Extension**
   - Install: "GitHub Actions" extension by GitHub
   - Make sure you're signed in to GitHub in VSCode

## Steps to Trigger

### Method 1: Using VSCode GitHub Actions Extension

1. **Open the GitHub Actions view:**
   - Click on the GitHub icon in the left sidebar
   - Or use Command Palette: `Ctrl+Shift+P` → "GitHub Actions: Focus on Actions View"

2. **Find your workflow:**
   - Look for "CI/CD - Docker to Azure Web App (Production)"
   - It should appear under "Workflows"

3. **Run the workflow:**
   - Right-click on the workflow name
   - Select "Run Workflow"
   - Or click the play button next to the workflow

### Method 2: Using Command Palette

1. Press `Ctrl+Shift+P` (or `Cmd+Shift+P` on Mac)
2. Type: `GitHub Actions: Run Workflow`
3. Select your workflow from the list
4. Choose the branch (usually `main`)

### Method 3: From GitHub Web Interface

1. Go to your repository on GitHub
2. Click on "Actions" tab
3. Find "CI/CD - Docker to Azure Web App (Production)" in the left sidebar
4. Click "Run workflow" button
5. Select branch and click "Run workflow"

## Troubleshooting

### Issue: Workflow not showing in VSCode

**Solution 1: Commit and push the workflow**
```bash
git add .github/workflows/deploy-prod.yml
git commit -m "Add production deployment workflow"
git push
```

**Solution 2: Refresh VSCode**
- Reload VSCode window: `Ctrl+Shift+P` → "Developer: Reload Window"
- Or restart VSCode

**Solution 3: Check if workflow is on default branch**
- The workflow must be on the default branch (usually `main`)
- If you're on a different branch, merge to main first

**Solution 4: Verify workflow syntax**
- Make sure `workflow_dispatch:` is present (line 9)
- Check for YAML syntax errors

**Solution 5: Check GitHub connection**
- Make sure you're signed in to GitHub in VSCode
- Check: Settings → Accounts → GitHub

### Issue: "Run Workflow" button not visible

- The workflow must have `workflow_dispatch:` trigger
- You must have write access to the repository
- The workflow file must be committed to the repository

### Issue: Extension not working

1. **Reinstall the extension:**
   - Uninstall "GitHub Actions" extension
   - Restart VSCode
   - Reinstall the extension

2. **Check extension settings:**
   - Open Settings
   - Search for "GitHub Actions"
   - Make sure it's enabled

## Alternative: Quick Test

If VSCode extension doesn't work, you can always:

1. **Push to trigger automatically:**
   ```bash
   git push origin main
   ```

2. **Use GitHub CLI (if installed):**
   ```bash
   gh workflow run "CI/CD - Docker to Azure Web App (Production).yml"
   ```

3. **Use GitHub Web UI:**
   - Go to Actions tab → Select workflow → Run workflow

## Verification

To verify the workflow is set up correctly:

1. Check the workflow file exists: `.github/workflows/deploy-prod.yml`
2. Verify `workflow_dispatch:` is on line 9
3. Commit and push to GitHub
4. Check GitHub Actions tab - you should see the workflow listed

