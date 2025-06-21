param(
    [Parameter(Mandatory=$true)]
    [string]$WorkspacePath
)

# Get the folder name to use as repo name
$RepoName = Split-Path $WorkspacePath -Leaf

# Change to the workspace directory
Set-Location $WorkspacePath

# Initialize git if not already initialized
if (-not (Test-Path "$WorkspacePath/.git")) {
    git init
}

# Add all files and commit
if (-not (git status --porcelain)) {
    Write-Host "No changes to commit."
} else {
    git add .
    git commit -m "Initial commit"
}

# Create GitHub repo and push using gh CLI
$ghRepo = "dstaulcu/$RepoName"

# Check if remote already exists
$remote = git remote get-url origin 2>$null
if (-not $remote) {
    gh repo create $ghRepo --public --source=. --remote=origin --push
} else {
    Write-Host "Remote 'origin' already exists. Skipping repo creation."
    git push -u origin main
}
