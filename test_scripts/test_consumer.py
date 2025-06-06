import asyncio
import json
from aiokafka import AIOKafkaConsumer
from src.config.settings import settings

async def test_consumer():
    try:
        consumer = AIOKafkaConsumer(
            'project.created',
            bootstrap_servers=settings.KAFKA_BOOTSTRAP_SERVERS,
            group_id='test-consumer-group',
            value_deserializer=lambda m: json.loads(m.decode('utf-8')),
            auto_offset_reset='earliest'  # Start from beginning
        )
        
        await consumer.start()
        print("Consumer started successfully")
        
        # Try to consume one message with timeout
        try:
            async for message in consumer:
                print(f"Received message: {message.value}")
                break  # Just get one message
        except Exception as e:
            print(f"Error consuming message: {e}")
        
        await consumer.stop()
        print("Consumer stopped")
        
    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(test_consumer()) 