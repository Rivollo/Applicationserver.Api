import json
import logging
import asyncio
import uuid

from azure.servicebus.aio import ServiceBusClient
from azure.servicebus import ServiceBusMessage
from azure.servicebus.exceptions import (
    ServiceBusError,
    ServiceBusAuthenticationError,
    ServiceBusConnectionError,
)

from app.core.config import settings

logger = logging.getLogger(__name__)

SERVICE_BUS_TIMEOUT = 30


class ServiceBusPublisher:
    @staticmethod
    async def publish(payload: dict) -> bool:
        # Config validation
        if not settings.SERVICEBUS_CONNECTION_STRING:
            logger.warning("Service Bus connection string not configured")
            return False

        if not settings.SERVICEBUS_QUEUE_NAME:
            logger.warning("Service Bus queue name not configured")
            return False

        message_id = None

        try:
            async def _send_message():
                nonlocal message_id
                message_id = str(uuid.uuid4())

                logger.info("Service Bus client created")
                async with ServiceBusClient.from_connection_string(
                    conn_str=settings.SERVICEBUS_CONNECTION_STRING,
                    logging_enable=False,
                ) as client:

                    logger.info("Queue sender created")
                    async with client.get_queue_sender(
                        queue_name=settings.SERVICEBUS_QUEUE_NAME
                    ) as sender:

                        message = ServiceBusMessage(
                            json.dumps(payload, default=str),
                            content_type="application/json",
                            subject="product-image-processing",
                            message_id=message_id,
                            application_properties={
                                "product_id": payload.get("product_id"),
                                "timestamp": payload.get("timestamp"),
                            },
                        )

                        logger.info("Sending message")
                        await sender.send_messages(message)

                logger.info("Message sent")
                return message_id

            await asyncio.wait_for(_send_message(), timeout=SERVICE_BUS_TIMEOUT)
            logger.info(
                f"Message published (product_id={payload.get('product_id')})"
            )
            return True

        except asyncio.TimeoutError:
            logger.error("Service Bus publish timed out")
            return False

        except ServiceBusAuthenticationError:
            logger.error("Service Bus authentication failed")
            return False

        except ServiceBusConnectionError:
            logger.error("Service Bus connection failed")
            return False

        except ServiceBusError:
            logger.error("Service Bus error")
            return False

        except TypeError:
            logger.error("Invalid payload for JSON serialization")
            return False

        except Exception:
            logger.exception("Unexpected Service Bus error")
            return False
