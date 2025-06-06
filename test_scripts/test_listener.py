import asyncio
from src.config.event_bus import get_event_bus
from src.listeners.project_events_listener import start_listening

async def test_listener():
    try:
        event_bus = await get_event_bus()
        print('Event bus connected successfully')
        # Don't actually start listening, just test the setup
        print('Listener setup test completed')
    except Exception as e:
        print(f'Error: {e}')
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(test_listener()) 