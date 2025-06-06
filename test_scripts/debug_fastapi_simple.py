#!/usr/bin/env python3

import sys
import os
sys.path.insert(0, '.')

# Set environment variable to avoid issues
os.environ['DEBUG'] = 'True'

try:
    print("1. Importing FastAPI...")
    from fastapi import FastAPI
    
    print("2. Creating simple app...")
    app = FastAPI(title="Test App")
    
    @app.get("/")
    async def root():
        return {"message": "Hello World"}
    
    @app.get("/health")
    async def health():
        return {"status": "healthy"}
    
    print("3. Starting uvicorn server...")
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8000, log_level="info")
    
except Exception as e:
    print(f"❌ Error: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1) 