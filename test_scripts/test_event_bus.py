#!/usr/bin/env python3

import asyncio
import sys
import os

# Add the src directory to the path
sys.path.append(os.path.join(os.path.dirname(__file__), 'src'))

from src.config.event_bus import get_event_bus, close_event_bus

async def test_event_bus():
    try:
        print("Testing event bus initialization...")
        event_bus = await get_event_bus()
        print('✅ Event bus initialized successfully')
        await close_event_bus()
        print('✅ Event bus closed successfully')
        return True
    except Exception as e:
        print(f'❌ Event bus failed: {e}')
        return False

if __name__ == "__main__":
    result = asyncio.run(test_event_bus())
    exit(0 if result else 1) 