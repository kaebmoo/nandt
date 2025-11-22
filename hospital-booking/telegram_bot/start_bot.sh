#!/bin/bash
# Quick start script for Telegram Bot
# Usage: ./start_bot.sh

set -e

echo "=========================================="
echo "🤖 Starting Hospital Booking Telegram Bot"
echo "=========================================="
echo ""

# Check if virtual environment exists
if [ -d "venv" ]; then
    echo "📦 Activating virtual environment..."
    source venv/bin/activate
else
    echo "⚠️  Virtual environment not found"
    echo "   Create one with: python -m venv venv"
    echo "   Then run: source venv/bin/activate"
    echo "   And: pip install -r requirements.txt"
    exit 1
fi

# Check if .env exists
if [ ! -f ".env" ]; then
    echo "❌ .env file not found"
    echo "   Copy .env.example and configure it:"
    echo "   cp .env.example .env"
    echo "   nano .env"
    exit 1
fi

# Run health check
echo "🏥 Running health check..."
python health_check.py

if [ $? -eq 0 ]; then
    echo ""
    echo "🚀 Starting bot..."
    echo "   Press Ctrl+C to stop"
    echo ""
    python bot.py
else
    echo ""
    echo "❌ Health check failed. Fix the issues and try again."
    exit 1
fi
