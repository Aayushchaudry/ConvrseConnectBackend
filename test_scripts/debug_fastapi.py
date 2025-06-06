#!/usr/bin/env python3

import sys
import asyncio
import traceback

sys.path.insert(0, '.')

try:
    print("1. Importing src.main...")
    from src.main import app
    print("✓ App imported successfully")
    
    print("2. Testing basic app functionality...")
    print(f"App type: {type(app)}")
    
    print("3. Starting uvicorn server...")
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8000, log_level="debug")
    
except Exception as e:
    print(f"❌ Error: {e}")
    traceback.print_exc()
    sys.exit(1) 