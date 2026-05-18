#!/bin/bash

echo "🚀 Inventory Management System - Quick Start Script"
echo "=================================================="
echo ""

# Check Python installation
if ! command -v python3 &> /dev/null; then
    echo "❌ Python 3 is not installed. Please install Python 3.9 or higher."
    exit 1
fi

echo "✅ Python found: $(python3 --version)"
echo ""

# Navigate to backend
cd backend

# Create virtual environment if it doesn't exist
if [ ! -d "venv" ]; then
    echo "📦 Creating virtual environment..."
    python3 -m venv venv
    echo "✅ Virtual environment created"
else
    echo "✅ Virtual environment already exists"
fi

# Activate virtual environment
echo "🔧 Activating virtual environment..."
source venv/bin/activate || . venv/Scripts/activate

# Install dependencies
echo "📥 Installing dependencies..."
pip install -r requirements.txt --quiet

# Create .env if it doesn't exist
if [ ! -f ".env" ]; then
    echo "⚙️  Creating .env file..."
    cp .env.example .env
    echo "✅ .env file created with default settings"
else
    echo "✅ .env file already exists"
fi

# Create necessary directories
mkdir -p app/uploads app/models

echo ""
echo "✅ Setup Complete!"
echo ""
echo "🎯 Next Steps:"
echo "1. Start the backend server:"
echo "   uvicorn app.main:app --reload --host 127.0.0.1 --port 8000"
echo ""
echo "2. Open frontend/index.html in your browser"
echo ""
echo "3. Upload your CSV data and start analyzing!"
echo ""
echo "📚 API Documentation: http://127.0.0.1:8000/docs"
echo ""
