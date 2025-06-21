# Quickstart script for duplicate_media_finder
# 1. Create conda environment if it doesn't exist
# 2. Activate environment
# 3. Install requirements
# 4. Launch Streamlit app

$envName = "duplicate_media_finder_env_p3.9"
$pythonVersion = "3.9"

# Check if conda is available
if (-not (Get-Command conda -ErrorAction SilentlyContinue)) {
    Write-Error "Conda is not installed or not in PATH. Please install Anaconda or Miniconda."
    exit 1
}

# Check if environment exists
$envList = conda env list | Select-String $envName
if (-not $envList) {
    Write-Host "Creating conda environment: $envName with Python $pythonVersion..."
    conda create -y -n $envName python=$pythonVersion
} else {
    Write-Host "Conda environment $envName already exists."
}

# Activate environment
conda activate $envName

# Install requirements
pip install -r requirements.txt

# Launch Streamlit app
streamlit run app.py
