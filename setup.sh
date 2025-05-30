#!/bin/bash

# Define the virtual environment directory
VENV_DIR=".venv"

# Create virtual environment
echo "Creating virtual environment..."
python -m venv $VENV_DIR

if [ $? -ne 0 ]; then
    echo "Failed to create virtual environment!"
    exit 1
fi

echo "Virtual environment created successfully: $VENV_DIR"

# Activate virtual environment (for Linux/macOS)
# For Windows, a different activation method is needed; this script primarily targets Unix-like environments
if [ -f "$VENV_DIR/bin/activate" ]; then
    echo "Activating virtual environment..."
    source "$VENV_DIR/bin/activate"
    echo "Virtual environment activated."
else
    echo "Virtual environment activation script not found. Please check your OS or if the virtual environment was created successfully."
    exit 1
fi

# Install uv in the virtual environment
echo "Installing uv in the virtual environment..."
pip install uv --index-url https://mirrors.cloud.tencent.com/pypi/simple/

if [ $? -ne 0 ]; then
    echo "Failed to install uv!"
    exit 1
fi

echo "uv installed successfully."


# Generate requirements.txt file
echo "Generating requirements.txt file..."
cat <<EOL > requirements.txt
fastmcp>=2.0.0
psutil>=7.0.0
pyside6>=6.8.2.1
EOL
echo "requirements.txt file generated."

# Install dependencies using uv via Tencent source
echo "Installing dependencies using uv via Tencent source..."
uv pip install -r requirements.txt --index-url https://mirrors.cloud.tencent.com/pypi/simple/

if [ $? -eq 0 ]; then
    echo "Project dependencies installed successfully!"
else
    echo "Failed to install project dependencies. Please check the error messages."
    exit 1
fi

echo "Environment configuration complete."
