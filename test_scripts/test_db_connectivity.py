#!/usr/bin/env python3

import asyncio
import sys
sys.path.insert(0, '.')

async def test_db():
    try:
        from src.config.database import engine
        print('✓ Database engine created successfully')
        
        # Test connection
        from sqlalchemy import text
        async with engine.begin() as conn:
            result = await conn.execute(text('SELECT 1'))
            print('✓ Database connection test: SUCCESS')
            return True
    except Exception as e:
        print(f'❌ Database connection test: FAILED - {e}')
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    success = asyncio.run(test_db())
    sys.exit(0 if success else 1) 