"""Service Bus message sender for product processing."""

import json
import logging
import os
from typing import Optional

from azure.servicebus.aio import ServiceBusClient
from azure.servicebus import ServiceBusMessage

logger = logging.getLogger(__name__)


async def send_product_processing_message(
    product_id: str,
    user_id: str,
    blob_url: str,
    target_format: str,
    asset_id: int,
    mesh_asset_id: int,
    name: str,
) -> bool:
    """Send a product processing message to Azure Service Bus queue.
    
    Args:
        product_id: Product UUID as string
        user_id: User UUID as string
        blob_url: Blob URL of the uploaded image
        target_format: Target format (e.g., "glb", "obj")
        asset_id: Asset ID for original image
        mesh_asset_id: Asset ID for generated mesh
        name: Product name
        
    Returns:
        True if message sent successfully, False otherwise
    """
    connection_string = os.getenv("SERVICEBUS_CONNECTION_STRING")
    queue_name = os.getenv("SERVICEBUS_QUEUE_NAME", "ai-processing-queue")
    
    if not connection_string:
        logger.error("SERVICEBUS_CONNECTION_STRING not configured")
        return False
    
    try:
        # Create message in ProductProcessingMessage format
        message_data = {
            "product_id": product_id,
            "user_id": user_id,
            "blob_url": blob_url,
            "target_format": target_format,
            "asset_id": asset_id,
            "mesh_asset_id": mesh_asset_id,
            "name": name,
        }
        
        message_body = json.dumps(message_data)
        
        # Send to Service Bus
        async with ServiceBusClient.from_connection_string(connection_string) as client:
            async with client.get_queue_sender(queue_name) as sender:
                message = ServiceBusMessage(message_body)
                await sender.send_messages(message)
                logger.info(f"Sent product processing message to queue for product {product_id}")
                return True
                
    except Exception as e:
        logger.error(f"Failed to send message to Service Bus: {str(e)}")
        return False
