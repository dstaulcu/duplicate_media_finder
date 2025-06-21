param(
    [Parameter(Mandatory=$true)]
    [string]$WorkspacePath
)

# Change to the workspace directory
Set-Location $WorkspacePath

# Check if this is a git repo
if (-not (Test-Path "$WorkspacePath/.git")) {
    Write-Error "This directory is not a git repository."
    exit 1
}

# Add and commit any changes
if (-not (git status --porcelain)) {
    Write-Host "No changes to commit."
} else {
    git add .
    git commit -m "Update from update_github_repo.ps1 script"
}

# Push to remote if exists
$remote = git remote get-url origin 2>$null
if ($remote) {
    git push origin main
} else {
    Write-Host "No remote 'origin' found. Skipping push."
}
