from src.events.project_events import ProjectCreatedEvent
import uuid
from datetime import datetime

# Test event data exactly as it comes from Kafka (all strings)
event_data = {
    'event_id': '2f99fe1b-c532-4d04-b6e3-019b773d996c',
    'timestamp': '2025-05-31T06:35:50.955181',
    'event_type': 'ProjectCreatedEvent',
    'project_id': '3ed18cc8-73f7-4991-934e-35b04ee56cb7',
    'project_name': 'Ultimate SAGA Test',
    'initial_status': 'initiated'
}

try:
    event = ProjectCreatedEvent(**event_data)
    print('Event deserialization successful')
    print(f'Event: {event}')
    print(f'Event ID type: {type(event.event_id)}')
    print(f'Project ID type: {type(event.project_id)}')
    print(f'Timestamp type: {type(event.timestamp)}')
except Exception as e:
    print(f'Error: {e}')
    import traceback
    traceback.print_exc() 