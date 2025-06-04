# src/config/kafka_event_bus.py

"""
Kafka Event Bus Implementation.
Concrete implementation of EventBus using Apache Kafka.
"""

import json
import logging
import uuid
import datetime
from decimal import Decimal
from typing import Any, Dict, Callable
from aiokafka import AIOKafkaProducer, AIOKafkaConsumer
from src.events.event_bus_interface import EventBus
from src.config.settings import settings

logger = logging.getLogger(__name__)


class CustomJSONEncoder(json.JSONEncoder):
    """Custom JSON encoder that handles UUID, datetime, and other common types."""
    
    def default(self, obj):
        if isinstance(obj, uuid.UUID):
            return str(obj)
        elif isinstance(obj, datetime.datetime):
            return obj.isoformat()
        elif isinstance(obj, datetime.date):
            return obj.isoformat()
        elif isinstance(obj, Decimal):
            return float(obj)
        elif hasattr(obj, '__dict__'):
            # Handle objects with __dict__ (like Enums or custom classes)
            if hasattr(obj, 'value'):  # For Enum objects
                return obj.value
            return obj.__dict__
        return super().default(obj)


def json_serializer(value: Any) -> bytes:
    """Custom JSON serializer for Kafka messages."""
    return json.dumps(value, cls=CustomJSONEncoder).encode('utf-8')


class KafkaEventBus(EventBus):
    """Kafka implementation of the EventBus interface."""
    
    def __init__(self):
        self.producer: AIOKafkaProducer = None
        self.consumers: Dict[str, AIOKafkaConsumer] = {}
        self.bootstrap_servers = settings.KAFKA_BOOTSTRAP_SERVERS
        
    async def connect(self) -> None:
        """Establish connection to Kafka."""
        try:
            # Initialize producer with custom JSON serializer
            self.producer = AIOKafkaProducer(
                bootstrap_servers=self.bootstrap_servers,
                value_serializer=json_serializer,
                client_id=settings.KAFKA_CLIENT_ID,
                request_timeout_ms=30000,
                linger_ms=settings.KAFKA_LINGER_MS
            )
            await self.producer.start()
            logger.info(f"Kafka Producer connected to {self.bootstrap_servers}")
            
        except Exception as e:
            logger.error(f"Failed to connect Kafka producer: {e}")
            raise
    
    async def disconnect(self) -> None:
        """Close connection to Kafka."""
        try:
            if self.producer:
                await self.producer.stop()
                logger.info("Kafka Producer disconnected")
            
            for topic, consumer in self.consumers.items():
                await consumer.stop()
                logger.info(f"Kafka Consumer for topic '{topic}' disconnected")
            
            self.consumers.clear()
            
        except Exception as e:
            logger.error(f"Error disconnecting Kafka: {e}")
    
    async def publish(self, topic: str, message: Dict[str, Any]) -> None:
        """Publish a message to a Kafka topic."""
        try:
            if not self.producer:
                raise RuntimeError("Kafka producer not connected. Call connect() first.")
            
            # Send message and await the result to get metadata
            record_metadata = await self.producer.send_and_wait(topic, message)
            
            # Log detailed success information
            logger.info(f"Message published to topic '{topic}' partition {record_metadata.partition} offset {record_metadata.offset}")
            logger.debug(f"Message content: {message}")
            
        except Exception as e:
            logger.error(f"Failed to publish message to topic '{topic}': {e}")
            raise
    
    async def subscribe(self, topic: str, callback: Callable) -> None:
        """Subscribe to a Kafka topic with a callback function."""
        try:
            consumer = AIOKafkaConsumer(
                topic,
                bootstrap_servers=self.bootstrap_servers,
                group_id=settings.KAFKA_CONSUMER_GROUP_ID,
                value_deserializer=lambda m: json.loads(m.decode('utf-8')),
                client_id=f"{settings.KAFKA_CLIENT_ID}-consumer"
            )
            
            await consumer.start()
            self.consumers[topic] = consumer
            logger.info(f"Kafka Consumer subscribed to topic '{topic}'")
            
            # Start consuming messages
            async for message in consumer:
                try:
                    await callback(message.value)
                except Exception as e:
                    logger.error(f"Error processing message from topic '{topic}': {e}")
                    
        except Exception as e:
            logger.error(f"Failed to subscribe to topic '{topic}': {e}")
            raise
    
    async def create_topic(self, topic_name: str) -> None:
        """Create a Kafka topic if it doesn't exist."""
        # Note: In production, topics are usually created by Kafka admin tools
        # This is a placeholder for topic creation logic
        logger.info(f"Topic creation requested for '{topic_name}' (handled by Kafka auto-creation)")
        pass
    
    def get_consumer(self, topic, group_id: str):
        """
        Returns a consumer instance for direct iteration (for background listeners).
        topic can be either a string or a list of strings.
        """
        # Handle both single topic (string) and multiple topics (list)
        if isinstance(topic, str):
            topics = [topic]
            consumer_key = f"{topic}-{group_id}"
        else:
            topics = topic  # It's already a list
            consumer_key = f"{'-'.join(sorted(topics))}-{group_id}"
        
        if consumer_key in self.consumers:
            return self.consumers[consumer_key]
        
        # Create a new consumer for background listening
        consumer = AIOKafkaConsumer(
            *topics,  # Unpack the topics list
            bootstrap_servers=self.bootstrap_servers,
            group_id=group_id,
            value_deserializer=lambda m: json.loads(m.decode('utf-8')),
            client_id=f"{settings.KAFKA_CLIENT_ID}-{group_id}",
            auto_offset_reset='earliest'  # Start from beginning for new consumer groups
        )
        self.consumers[consumer_key] = consumer
        return consumer