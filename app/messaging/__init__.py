"""RabbitMQ producer / consumer package."""
from app.messaging.producer import MessageProducer
from app.messaging.consumer import MessageConsumer

__all__ = ["MessageProducer", "MessageConsumer"]
