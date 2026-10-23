#!/usr/bin/env python3
"""
Paisa - Personal Finance Tracker
Run this file to start the application.
"""
import sys
import webbrowser
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent))

from src.app import app


def main():
    """Start the Paisa application."""
    print("=" * 50)
    print("  💰 Paisa - Personal Finance Tracker")
    print("=" * 50)
    print()
    print("Starting server at http://localhost:5000")
    print("Press Ctrl+C to stop")
    print()
    
    # Open browser automatically
    webbrowser.open('http://localhost:5000')
    
    # Run the app
    app.run(
        host='127.0.0.1',
        port=5000,
        debug=True,
        use_reloader=False  # Disabled to prevent reload issues during uploads
    )


if __name__ == '__main__':
    main()
