# Quickstart script for duplicate_media_finder
# 1. Create conda environment if it doesn't exist
# 2. Activate environment
# 3. Install requirements
# 4. Launch Streamlit app
#
# NOTE: If you see an error that 'conda' is not installed or not in PATH,
# please run this script from an Anaconda/Miniconda PowerShell prompt where 'conda' is available.

$envName = "duplicate_media_finder_env_p3.9"
$pythonVersion = "3.9"

# Check if conda is available
try {
    $condaCmd = Get-Command conda -ErrorAction Stop
} catch {
    Write-Error "Conda is not installed or not in PATH. Please install Anaconda or Miniconda and ensure 'conda' is available in your PATH. Alternatively, run this script from an Anaconda/Miniconda PowerShell prompt."
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
