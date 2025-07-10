#!/bin/bash
# setup.sh - Setup script for NudDee SaaS

echo "🚀 Setting up NudDee SaaS..."

# Check if Python 3 is installed
if ! command -v python3 &> /dev/null; then
    echo "❌ Python 3 is required but not installed."
    exit 1
fi

# Create virtual environment
if [ ! -d "venv" ]; then
    echo "📦 Creating virtual environment..."
    python3 -m venv venv
fi

# Activate virtual environment
echo "🔄 Activating virtual environment..."
source venv/bin/activate

# Upgrade pip
echo "⬆️ Upgrading pip..."
pip install --upgrade pip

pipreqs .

# Install requirements
if [ -f "requirements.txt" ]; then
    echo "📋 Installing requirements..."
    pip install -r requirements.txt
else
    echo "❌ requirements.txt not found!"
    exit 1
fi

# Create .env file if it doesn't exist
if [ ! -f ".env" ]; then
    echo "⚙️ Creating .env file..."
    cp .env.example .env
    echo "✏️ Please edit .env file with your configuration"
fi

# Create necessary directories
echo "📁 Creating directories..."
mkdir -p uploads
mkdir -p logs
mkdir -p backups/teamup

# Initialize database
echo "💾 Initializing database..."
python manage.py db-cmd init

# Check configuration
echo "🔧 Checking configuration..."
python manage.py dev check

echo "✅ Setup complete!"
echo ""
echo "Next steps:"
echo "1. Edit .env file with your API keys and configuration"
echo "2. Run: python manage.py db-cmd seed (for sample data)"
echo "3. Run: python manage.py dev run (to start development server)"
echo ""
echo "For production deployment:"
echo "1. Set FLASK_ENV=production in .env"
echo "2. Configure proper database (PostgreSQL recommended)"
echo "3. Set up reverse proxy (nginx)"
echo "4. Use gunicorn: gunicorn -w 4 -b 0.0.0.0:5000 run:app"