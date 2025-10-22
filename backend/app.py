#!/usr/bin/env python3
"""
FastAPI backend for Order Automation System
Production-ready e-commerce automation platform with Strands agents and Playwright MCP
"""

import os
import json
import asyncio
import logging
import signal
import sys
import csv
import io
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional
from contextlib import asynccontextmanager

from fastapi import (
    FastAPI,
    HTTPException,
    WebSocket,
    WebSocketDisconnect,
    BackgroundTasks,
    Response,
    File,
    UploadFile,
    Form,
)
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from enum import Enum

# Import our modules
from database import (
    DatabaseManager,
    Order,
    OrderStatus,
    OrderPriority,
    AutomationMethod,
)
from config import get_config_manager
from order_queue import OrderQueue, initialize_order_queue
from services.browser_service import BrowserService
from services.settings_service import SettingsService

# Configure logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

# Global instances
db_manager = None
order_queue = None
# config_manager = None  # Replaced by SettingsService

# Shutdown flag
shutdown_event = asyncio.Event()


def signal_handler(signum, frame):
    """Handle shutdown signals"""
    logger.info(f"Received signal {signum}, initiating graceful shutdown...")
    shutdown_event.set()
    
    # Start shutdown task with 5 second timeout
    asyncio.create_task(perform_graceful_shutdown())


async def perform_graceful_shutdown():
    """Perform graceful shutdown with aggressive timeout"""
    try:
        logger.info("Starting graceful shutdown process...")
        
        # Give 2 seconds for graceful shutdown
        logger.info("Starting 2-second graceful shutdown timer...")
        await asyncio.sleep(0.05)  # Minimal delay
        
        # Run all cleanup tasks in parallel with aggressive timeouts
        cleanup_tasks = []
        
        # Task 1: Stop order queue
        async def stop_order_queue():
            if 'order_queue' in globals() and order_queue:
                try:
                    logger.info("Stopping order queue...")
                    await asyncio.wait_for(order_queue.stop(), timeout=0.5)
                    logger.info("Order queue stopped")
                except asyncio.TimeoutError:
                    logger.warning("Order queue stop timed out")
                except Exception as e:
                    logger.error(f"Error stopping order queue: {e}")
        
        # Task 2: Cleanup browser sessions
        async def cleanup_browser_sessions():
            try:
                from services.browser_service import get_browser_service
                browser_service = get_browser_service()
                logger.info("Cleaning up browser sessions...")
                
                loop = asyncio.get_event_loop()
                await asyncio.wait_for(
                    loop.run_in_executor(None, browser_service.cleanup_all_sessions),
                    timeout=0.5
                )
                logger.info("Browser sessions cleaned up")
            except asyncio.TimeoutError:
                logger.warning("Browser cleanup timed out")
            except Exception as e:
                logger.error(f"Error cleaning up browser sessions: {e}")
        
        # Task 3: Close database connections
        async def close_database():
            if 'db_manager' in globals() and db_manager:
                try:
                    logger.info("Closing database connections...")
                    loop = asyncio.get_event_loop()
                    await asyncio.wait_for(
                        loop.run_in_executor(None, db_manager.close),
                        timeout=0.3
                    )
                    logger.info("Database connections closed")
                except asyncio.TimeoutError:
                    logger.warning("Database close timed out")
                except Exception as e:
                    logger.error(f"Error closing database: {e}")
        
        # Run all cleanup tasks in parallel with 1.5 second total timeout
        cleanup_tasks = [stop_order_queue(), cleanup_browser_sessions(), close_database()]
        try:
            await asyncio.wait_for(asyncio.gather(*cleanup_tasks, return_exceptions=True), timeout=1.5)
            logger.info("Parallel cleanup completed")
        except asyncio.TimeoutError:
            logger.warning("Parallel cleanup timed out, forcing shutdown")

        logger.info("Graceful shutdown completed in 1.5 seconds, exiting...")
        
        # Force exit after cleanup
        import os
        os._exit(0)
        
    except Exception as e:
        logger.error(f"Error during graceful shutdown: {e}")
        # Force exit even if cleanup fails
        import os
        os._exit(1)


# Register signal handlers
signal.signal(signal.SIGINT, signal_handler)
signal.signal(signal.SIGTERM, signal_handler)


def get_settings_service():
    """Get SettingsService instance"""
    return SettingsService(db_manager)


def get_browser_service_with_config():
    """Get BrowserService with current system config"""
    settings_service = get_settings_service()
    config = settings_service.get_system_config()
    return BrowserService(config, db_manager)


# WebSocket connection manager
class ConnectionManager:
    def __init__(self):
        self.active_connections: List[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)

    def disconnect(self, websocket: WebSocket):
        self.active_connections.remove(websocket)

    async def send_personal_message(self, message: str, websocket: WebSocket):
        await websocket.send_text(message)

    async def broadcast(self, message: str):
        dead_connections = []
        for connection in self.active_connections:
            try:
                await connection.send_text(message)
            except:
                # Mark dead connections for removal
                dead_connections.append(connection)

        # Remove dead connections safely
        for connection in dead_connections:
            if connection in self.active_connections:
                self.active_connections.remove(connection)


manager = ConnectionManager()


# Pydantic models for API
class ProductInfo(BaseModel):
    url: str
    name: str
    size: Optional[str] = None
    color: Optional[str] = None
    quantity: int = 1
    price: Optional[float] = None


class ShippingAddress(BaseModel):
    first_name: str
    last_name: str
    address_line_1: str
    city: str
    state: str
    postal_code: str
    country: str = "US"
    phone: Optional[str] = None


class PaymentInfo(BaseModel):
    payment_token: str
    cardholder_name: str


class CreateOrderRequest(BaseModel):
    retailer: str
    automation_method: str
    ai_model: Optional[str] = None
    product: ProductInfo
    customer_name: str
    customer_email: str
    shipping_address: ShippingAddress
    payment_info: Optional[PaymentInfo] = None
    priority: str = "normal"
    instructions: Optional[str] = None


class UpdateOrderRequest(BaseModel):
    status: Optional[str] = None
    human_review_notes: Optional[str] = None


# Removed - using dict instead for flexibility


# Application lifecycle
@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    global db_manager, order_queue

    try:
        # Initialize database
        db_manager = DatabaseManager()
        logger.info("Database initialized")

        # Configuration manager replaced by SettingsService (stateless)
        logger.info("Using stateless SettingsService for configuration")

        # Initialize order queue
        global order_queue
        order_queue = initialize_order_queue(db_manager)
        await order_queue.start()
        logger.info("Order queue started")

        yield

    except Exception as e:
        logger.error(f"Failed to initialize application: {e}")
        raise
    finally:
        # Shutdown
        logger.info("Starting graceful shutdown...")

        # Stop order queue first
        if order_queue:
            try:
                await order_queue.stop()
                logger.info("Order queue stopped")
            except Exception as e:
                logger.error(f"Error stopping order queue: {e}")

        # Cleanup browser sessions
        from services.browser_service import get_browser_service

        try:
            browser_service = get_browser_service()
            # Cleanup all sessions during shutdown
            browser_service.cleanup_all_sessions()
            logger.info("Browser sessions cleaned up")
        except Exception as e:
            logger.error(f"Error cleaning up browser sessions: {e}")

        # Close database connections
        if db_manager:
            try:
                db_manager.close()
                logger.info("Database connections closed")
            except Exception as e:
                logger.error(f"Error closing database: {e}")

        logger.info("Graceful shutdown completed")


# Create FastAPI app
app = FastAPI(
    title="Drishti AI Navigatorwith Amazon Bedrock AgentCore Browser",
    description="Drishti AI Navigator automation platform",
    version="1.0.0",
    lifespan=lifespan,
)

# CORS middleware - configure based on environment
allowed_origins = os.getenv("ALLOWED_ORIGINS", "http://localhost:3000,http://127.0.0.1:3000").split(",")
app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["Content-Type", "Authorization", "X-Requested-With"],
    max_age=3600,
)

# Mount static files for screenshots
screenshots_dir = os.path.join(os.path.dirname(__file__), "static", "screenshots")
os.makedirs(screenshots_dir, exist_ok=True)
app.mount(
    "/api/screenshots", StaticFiles(directory=screenshots_dir), name="screenshots"
)


# Removed duplicate live-view endpoint - using the one below that properly handles order status


# Broadcast helper
async def broadcast_update(data: Dict[str, Any]):
    """Broadcast update to all connected WebSocket clients"""
    message = json.dumps(data)
    await manager.broadcast(message)


# API Routes


@app.get("/")
async def root():
    return {"message": "Order Automation System API", "version": "1.0.0"}


@app.get("/favicon.ico")
async def favicon():
    """Return a simple favicon response"""
    return Response(status_code=204)


async def _health_check_logic():
    """Shared health check logic"""
    try:
        # Check database connection
        stats = db_manager.get_order_stats()

        # Check queue status
        queue_metrics = await order_queue.get_queue_metrics()

        # Check config manager
        config_manager = get_config_manager(db_manager)
        config_status = "loaded"
        try:
            system_config = config_manager.get_system_config()
            config_keys = list(system_config.keys())
        except Exception as e:
            config_status = f"error: {str(e)}"
            config_keys = []

        return {
            "status": "healthy",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "database": "connected",
            "queue_status": queue_metrics.queue_status.value,
            "total_orders": stats.get("total_orders", 0),
            "config_manager": {
                "status": config_status,
                "config_keys": config_keys,
                "db_integration": db_manager is not None,
            },
        }
    except Exception as e:
        logger.error(f"Health check failed: {e}")
        raise HTTPException(status_code=503, detail="Service unavailable")


@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return await _health_check_logic()


@app.get("/api/health")
async def api_health_check():
    """API health check endpoint"""
    return await _health_check_logic()


# Order Management
@app.post("/api/orders")
async def create_order(request: CreateOrderRequest, background_tasks: BackgroundTasks):
    """Create a new order"""
    try:
        logger.info(
            f"Received order creation request: retailer={request.retailer}, automation_method={request.automation_method}"
        )

        # Validate retailer and automation method
        settings_service = SettingsService(db_manager)
        retailer_urls = settings_service.get_retailer_urls(request.retailer)
        if not retailer_urls:
            raise HTTPException(
                status_code=400,
                detail=f"Retailer {request.retailer} is not configured. Please add retailer URLs in Settings.",
            )

        # Basic validation: if retailer URLs exist, configuration is valid
        # All automation methods (nova_act, strands) are supported for all retailers

        # Convert priority
        try:
            priority = OrderPriority(request.priority.upper())
        except ValueError:
            priority = OrderPriority.NORMAL

        # Convert automation method
        try:
            automation_method = AutomationMethod(request.automation_method)
        except ValueError:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid automation method: {request.automation_method}",
            )

        # Handle payment info - provide default if not provided
        payment_token = (
            request.payment_info.payment_token
            if request.payment_info
            else f'tok_demo_{datetime.now().strftime("%Y%m%d_%H%M%S")}'
        )

        # Set default AI model if not provided
        ai_model = request.ai_model
        if not ai_model:
            if request.automation_method == "nova_act":
                ai_model = "nova_act"
            else:  # strands
                ai_model = "us.anthropic.claude-sonnet-4-20250514-v1:0"

        # Create order
        order_id = await order_queue.add_order(
            retailer=request.retailer,
            automation_method=request.automation_method,
            ai_model=ai_model,
            product_name=request.product.name,
            product_url=request.product.url,
            customer_name=request.customer_name,
            customer_email=request.customer_email,
            shipping_address=request.shipping_address.dict(),
            product_size=request.product.size,
            product_color=request.product.color,
            product_price=request.product.price,
            payment_token=payment_token,
            priority=priority,
            instructions=request.instructions,
        )

        # Get created order
        order = db_manager.get_order(order_id)

        # Broadcast order creation
        await broadcast_update(
            {"type": "order_created", "order": order.to_dict() if order else None}
        )

        return {"order_id": order_id, "status": "created"}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to create order: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/orders")
async def get_orders(
    status: Optional[str] = None, retailer: Optional[str] = None
):
    """Get orders with optional filtering"""
    try:
        status_filter = [status] if status else None
        orders = db_manager.get_all_orders(
            status_filter=status_filter, retailer_filter=retailer
        )

        return {"orders": [order.to_dict() for order in orders], "total": len(orders)}

    except Exception as e:
        logger.error(f"Failed to get orders: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/orders/{order_id}")
async def get_order(order_id: str):
    """Get specific order"""
    try:
        order = db_manager.get_order(order_id)
        if not order:
            raise HTTPException(status_code=404, detail="Order not found")

        order_dict = order.to_dict()

        # Add formatted error information for failed orders
        if order.status == OrderStatus.FAILED and order.error_message:
            order_dict["error_details"] = {
                "message": order.error_message,
                "timestamp": order.updated_at.isoformat() if order.updated_at else None,
                "step": order.current_step or "Unknown step",
            }

        return order_dict

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get order {order_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.put("/api/orders/{order_id}")
async def update_order(order_id: str, request: UpdateOrderRequest):
    """Update order (for human review)"""
    try:
        order = db_manager.get_order(order_id)
        if not order:
            raise HTTPException(status_code=404, detail="Order not found")

        # Update order status if provided
        if request.status:
            try:
                status = OrderStatus(request.status.upper())
                db_manager.update_order_status(
                    order_id=order_id,
                    status=status,
                    human_review_notes=request.human_review_notes,
                )
            except ValueError:
                raise HTTPException(
                    status_code=400, detail=f"Invalid status: {request.status}"
                )

        # Get updated order
        updated_order = db_manager.get_order(order_id)

        # Broadcast update
        await broadcast_update(
            {
                "type": "order_updated",
                "order": updated_order.to_dict() if updated_order else None,
            }
        )

        return updated_order.to_dict() if updated_order else None

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to update order {order_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/orders/{order_id}/live-view")
async def get_order_live_view(order_id: str):
    """Get live view URL for an active order"""
    try:
        order = db_manager.get_order(order_id)
        if not order:
            raise HTTPException(status_code=404, detail="Order not found")

        # Return order info even if not processing - let frontend handle gracefully
        response_data = {
            "order_id": order_id,
            "status": order.status.value,
            "automation_method": (
                order.automation_method.value if order.automation_method else None
            ),
            "live_view_url": None,
            "live_view_available": False,
            "message": None,
        }

        # Only try to get live view if order is processing
        if order.status == OrderStatus.PROCESSING:
            try:
                # Get the active agent from the queue
                active_agent = await order_queue.get_active_agent(order_id)
                if active_agent and hasattr(active_agent, "get_live_view_url"):
                    try:
                        live_view_info = active_agent.get_live_view_url()
                        if (
                            live_view_info
                            and isinstance(live_view_info, dict)
                            and live_view_info.get("url")
                        ):
                            response_data.update(
                                {
                                    "live_view_url": live_view_info["url"],
                                    "live_view_session_id": live_view_info.get(
                                        "session_id", order_id
                                    ),
                                    "live_view_type": live_view_info.get("type", "dcv"),
                                    "live_view_headers": live_view_info.get("headers"),
                                    "live_view_available": True,
                                    "message": "Live view is available",
                                }
                            )
                        elif isinstance(live_view_info, str):
                            # Backward compatibility for string URLs
                            response_data.update(
                                {
                                    "live_view_url": live_view_info,
                                    "live_view_session_id": order_id,
                                    "live_view_type": "dcv",
                                    "live_view_available": True,
                                    "message": "Live view is available",
                                }
                            )
                        else:
                            response_data["message"] = (
                                "Live view not supported by this automation method"
                            )
                    except Exception as url_error:
                        logger.warning(
                            f"Failed to get live view URL for order {order_id}: {url_error}"
                        )
                        response_data["message"] = "Live view temporarily unavailable"
                else:
                    response_data["message"] = "No active agent found for this order"
            except Exception as agent_error:
                logger.warning(
                    f"Failed to get active agent for order {order_id}: {agent_error}"
                )
                response_data["message"] = "Agent information temporarily unavailable"
        else:
            response_data["message"] = (
                f"Live view only available for processing orders. Current status: {order.status.value}"
            )

        return response_data

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get live view for order {order_id}: {e}")
        # Return error info instead of raising exception
        return {
            "order_id": order_id,
            "status": "error",
            "live_view_url": None,
            "live_view_available": False,
            "message": f"Error retrieving live view: {str(e)}",
        }


@app.get("/api/debug/active-agents")
async def get_active_agents():
    """Debug endpoint to check active agents"""
    try:
        active_agents = {}
        for order_id, agent in order_queue.active_agents.items():
            active_agents[order_id] = {
                "type": type(agent).__name__,
                "has_get_presigned_url": hasattr(agent, "get_presigned_url"),
                "session_id": getattr(agent, "session_id", None),
            }
        return {
            "active_agents": active_agents,
            "processing_orders": list(order_queue.processing_orders.keys()),
        }
    except Exception as e:
        return {"error": str(e)}


@app.get("/api/orders/{order_id}/presigned-url")
async def get_presigned_url(order_id: str):
    """Get presigned URL for DCV connection via LiveViewService"""
    try:
        order = db_manager.get_order(order_id)
        if not order:
            raise HTTPException(status_code=404, detail="Order not found")

        # Get live view URL directly from agent
        try:
            from services.browser_service import get_browser_service

            # Get automation config for BrowserService
            settings_service = SettingsService(db_manager)
            config = settings_service.get_automation_config(
                order.automation_method.value
            )
            if not config:
                raise HTTPException(
                    status_code=500, detail="Automation configuration not found"
                )

            # Get browser service
            browser_service = get_browser_service(config, db_manager)

            # Get live view URL directly from browser service
            live_view_info = browser_service.get_live_view_url(order_id, expires=300)

            if not live_view_info.get("url"):
                raise HTTPException(
                    status_code=503,
                    detail=live_view_info.get("error", "Failed to get live view URL"),
                )

            return {
                "order_id": order_id,
                "sessionId": order_id,
                "presignedUrl": live_view_info["url"],
                "authToken": order_id,
                "expires": 300,
            }

        except HTTPException:
            raise
        except Exception as service_error:
            logger.error(f"LiveViewService error for order {order_id}: {service_error}")
            raise HTTPException(
                status_code=500, detail=f"Live view service error: {str(service_error)}"
            )
        else:
            raise HTTPException(
                status_code=400,
                detail=f"Presigned URL only available for processing orders. Current status: {order.status.value}",
            )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get presigned URL for order {order_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/orders/{order_id}/resume-nova-act")
async def resume_nova_act_after_captcha(order_id: str):
    """Resume Nova Act execution after CAPTCHA has been resolved manually"""
    try:
        order = db_manager.get_order(order_id)
        if not order:
            raise HTTPException(status_code=404, detail="Order not found")

        # Only available for Nova Act orders that require human intervention
        if order.automation_method != AutomationMethod.NOVA_ACT:
            raise HTTPException(
                status_code=400,
                detail="Nova Act resume only available for Nova Act orders",
            )

        if order.status != OrderStatus.REQUIRES_HUMAN:
            raise HTTPException(
                status_code=400,
                detail=f"Order must be in 'requires_human' status to resume. Current status: {order.status.value}",
            )

        # Get the active agent from the queue
        active_agent = await order_queue.get_active_agent(order_id)
        if not active_agent or not hasattr(active_agent, "resume_after_captcha"):
            raise HTTPException(
                status_code=400,
                detail="Nova Act agent not available or does not support resume functionality",
            )

        # Update order status to processing
        db_manager.update_order_status(order_id, OrderStatus.PROCESSING)

        # Broadcast status update
        await broadcast_update(
            {"type": "order_updated", "order": db_manager.get_order(order_id).to_dict()}
        )

        # Resume Nova Act execution
        try:
            result = await active_agent.resume_after_captcha(order)

            # Update order based on result
            if result.get("success"):
                db_manager.update_order_status(order_id, OrderStatus.COMPLETED)
                if result.get("confirmation_number"):
                    db_manager.update_order(
                        order_id, {"confirmation_number": result["confirmation_number"]}
                    )
            elif result.get("status") == "requires_human":
                db_manager.update_order_status(order_id, OrderStatus.REQUIRES_HUMAN)
            else:
                db_manager.update_order_status(order_id, OrderStatus.FAILED)
                if result.get("error"):
                    db_manager.update_order(order_id, {"error": result["error"]})

            # Broadcast final update
            await broadcast_update(
                {
                    "type": "order_updated",
                    "order": db_manager.get_order(order_id).to_dict(),
                }
            )

            return {
                "success": result.get("success", False),
                "status": result.get("status", "failed"),
                "message": result.get("result")
                or result.get("message")
                or result.get("error"),
                "order_id": order_id,
            }

        except Exception as resume_error:
            logger.error(
                f"Failed to resume Nova Act for order {order_id}: {resume_error}"
            )

            # Update order status back to requires_human
            db_manager.update_order_status(order_id, OrderStatus.REQUIRES_HUMAN)
            db_manager.update_order(
                order_id, {"error": f"Resume failed: {str(resume_error)}"}
            )

            await broadcast_update(
                {
                    "type": "order_updated",
                    "order": db_manager.get_order(order_id).to_dict(),
                }
            )

            raise HTTPException(
                status_code=500,
                detail=f"Failed to resume Nova Act: {str(resume_error)}",
            )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to resume Nova Act for order {order_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# Secret Vault API Endpoints (AWS Secrets Manager)
@app.get("/api/secrets")
async def get_secrets():
    """Get all secret vault entries from AWS Secrets Manager (passwords masked)"""
    try:
        from services.secrets_manager import get_secrets_manager
        
        secrets_manager = get_secrets_manager()
        secrets = secrets_manager.list_secrets(include_passwords=False)
        
        return {"secrets": secrets}
    except Exception as e:
        logger.error(f"Failed to get secrets from AWS Secrets Manager: {e}")
        # Return empty list instead of error to prevent frontend infinite loading
        return {"secrets": []}


@app.post("/api/secrets")
async def create_secret(secret_data: dict):
    """Create a new secret in AWS Secrets Manager"""
    try:
        from services.secrets_manager import get_secrets_manager
        
        required_fields = ["site_name", "site_url"]
        for field in required_fields:
            if field not in secret_data:
                raise HTTPException(
                    status_code=400, detail=f"Missing required field: {field}"
                )

        secrets_manager = get_secrets_manager()
        secret_arn = secrets_manager.create_secret(
            site_name=secret_data["site_name"],
            site_url=secret_data["site_url"],
            username=secret_data.get("username"),
            password=secret_data.get("password"),
            additional_fields=secret_data.get("additional_fields", {}),
        )

        return {"success": True, "secret_arn": secret_arn}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to create secret in AWS Secrets Manager: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/secrets/{site_name}")
async def get_secret(site_name: str, include_password: bool = False):
    """Get a specific secret from AWS Secrets Manager"""
    try:
        from services.secrets_manager import get_secrets_manager
        
        secrets_manager = get_secrets_manager()
        secret = secrets_manager.get_secret(site_name, include_password=include_password)
        
        if not secret:
            raise HTTPException(status_code=404, detail="Secret not found")

        return secret
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get secret {site_name} from AWS Secrets Manager: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.put("/api/secrets/{site_name}")
async def update_secret(site_name: str, secret_data: dict):
    """Update a secret in AWS Secrets Manager"""
    try:
        from services.secrets_manager import get_secrets_manager
        
        secrets_manager = get_secrets_manager()
        secret_arn = secrets_manager.update_secret(
            site_name=site_name,
            site_url=secret_data.get("site_url"),
            username=secret_data.get("username"),
            password=secret_data.get("password"),
            additional_fields=secret_data.get("additional_fields"),
        )

        return {"success": True, "secret_arn": secret_arn}
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to update secret {site_name} in AWS Secrets Manager: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.delete("/api/secrets/{site_name}")
async def delete_secret(site_name: str, force: bool = False):
    """Delete a secret from AWS Secrets Manager"""
    try:
        from services.secrets_manager import get_secrets_manager
        
        secrets_manager = get_secrets_manager()
        success = secrets_manager.delete_secret(site_name, force_delete=force)
        
        if not success:
            raise HTTPException(status_code=404, detail="Secret not found")

        return {"success": True, "message": "Secret scheduled for deletion (30-day recovery window)" if not force else "Secret deleted immediately"}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to delete secret {site_name} from AWS Secrets Manager: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/live-view/sessions")
async def list_live_sessions():
    """List all active live view sessions"""
    try:
        from services.live_view_service import get_live_view_service

        # Get default config for service access
        config = get_settings_service().get_automation_config("strands")
        if not config:
            raise HTTPException(status_code=500, detail="Configuration not available")

        # Get active sessions from browser service
        from services.browser_service import get_browser_service

        config = get_settings_service().get_automation_config("strands")
        if not config:
            raise HTTPException(status_code=500, detail="Configuration not available")

        browser_service = get_browser_service(config, db_manager)
        sessions = browser_service.list_sessions()

        return {"sessions": sessions, "count": len(sessions)}

    except Exception as e:
        logger.error(f"Failed to list live sessions: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/orders/{order_id}/force-disconnect")
async def force_disconnect_live_session(order_id: str):
    """Force disconnect existing live view session for an order"""
    try:
        from services.live_view_service import get_live_view_service

        # Get default config for service access
        config = get_settings_service().get_automation_config("strands")
        if not config:
            raise HTTPException(status_code=500, detail="Configuration not available")

        # Force disconnect by cleaning up the agent
        from order_queue import get_order_queue

        order_queue = get_order_queue()
        agent = order_queue.active_agents.get(order_id)

        # Just remove agent from active list, but keep browser session for resume
        if agent:
            if order_id in order_queue.active_agents:
                del order_queue.active_agents[order_id]

            logger.info(
                f"Disconnected agent for order {order_id}, browser session preserved"
            )
            return {
                "success": True,
                "message": f"Disconnected agent for order {order_id}, session preserved for resume",
                "session_id": order_id,
            }
        else:
            return {
                "success": True,
                "message": "No active agent session found to disconnect",
                "session_id": None,
            }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to force disconnect session for order {order_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/orders/{order_id}/change-resolution")
async def change_browser_resolution(order_id: str, request: dict):
    """Change browser resolution for live view session"""
    try:
        from services.live_view_service import get_live_view_service

        # Validate request
        if "width" not in request or "height" not in request:
            raise HTTPException(status_code=400, detail="Width and height are required")

        width = int(request["width"])
        height = int(request["height"])

        # Validate resolution values
        if width < 640 or width > 3840 or height < 480 or height > 2160:
            raise HTTPException(
                status_code=400,
                detail="Invalid resolution. Width: 640-3840, Height: 480-2160",
            )

        config = get_settings_service().get_automation_config("strands")
        if not config:
            raise HTTPException(status_code=500, detail="Configuration not available")

        browser_service = get_browser_service(config, db_manager)

        # Change resolution via browser service
        result = browser_service.change_browser_resolution(order_id, width, height)

        if result["success"]:
            logger.info(
                f"Changed browser resolution to {width}x{height} for order {order_id}"
            )
            return result
        else:
            raise HTTPException(status_code=500, detail=result["error"])

    except HTTPException:
        raise
    except ValueError as e:
        raise HTTPException(
            status_code=400, detail=f"Invalid width or height: {str(e)}"
        )
    except Exception as e:
        logger.error(f"Failed to change browser resolution for order {order_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/orders/{order_id}/focus-tab")
async def focus_active_tab(order_id: str):
    """Focus on the active tab for live view session"""
    try:
        from order_queue import get_order_queue

        order_queue = get_order_queue()
        agent = order_queue.active_agents.get(order_id)

        if not agent:
            raise HTTPException(
                status_code=404, detail="No active agent found for this order"
            )

        # For now, just return success as focus is handled automatically
        logger.info(f"Focus request received for order {order_id}")
        return {
            "success": True,
            "message": f"Focus request processed for order {order_id}",
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to focus active tab for order {order_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/orders/{order_id}/take-control")
async def take_manual_control(order_id: str):
    """Enable manual control for browser session"""
    try:
        from services.browser_service import get_browser_service

        # Get browser service
        browser_service = get_browser_service()
        if not browser_service:
            raise HTTPException(status_code=500, detail="Browser service not available")

        # Enable manual control
        result = browser_service.enable_manual_control(order_id)

        if result["success"]:
            logger.info(f"Manual control enabled for order {order_id}")
            return result
        else:
            raise HTTPException(status_code=500, detail=result["error"])

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to enable manual control for order {order_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/orders/{order_id}/release-control")
async def release_manual_control(order_id: str):
    """Disable manual control and return to automation"""
    try:
        from services.live_view_service import get_live_view_service
        from services.browser_service import get_browser_service

        config = get_settings_service().get_automation_config("strands")
        if not config:
            raise HTTPException(status_code=500, detail="Configuration not available")

        # First disable manual control via browser service
        browser_service = get_browser_service()
        if browser_service:
            control_result = browser_service.disable_manual_control(order_id)
            if not control_result["success"]:
                raise HTTPException(status_code=400, detail=control_result["error"])

        # Update order status to processing
        order = db_manager.get_order(order_id)
        if order:
            db_manager.update_order_status(order_id, "processing")
            logger.info(f"Order {order_id} status updated to processing")

            # Resume automation by restarting the agent
            try:
                from agents.strands_agent import StrandsAgent

                # Create new agent instance to continue automation
                agent = StrandsAgent(
                    config=app_config,
                    retailer_config=retailer_config,
                    db_manager=db_manager,
                    browser_service=browser_service,
                )

                # Resume automation in background
                import asyncio

                asyncio.create_task(agent.resume_automation(order.product_name))

                logger.info(f"Automation resumed for order {order_id}")
                return {
                    "success": True,
                    "message": "Manual control released and automation resumed",
                    "order_id": order_id,
                }

            except Exception as e:
                logger.error(f"Failed to resume automation for order {order_id}: {e}")
                return {
                    "success": True,
                    "message": "Manual control released but automation could not be resumed",
                    "order_id": order_id,
                    "warning": str(e),
                }
        else:
            raise HTTPException(status_code=404, detail="Order not found")

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to release manual control for order {order_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/live-view/sessions/{session_id}/status")
async def get_live_session_status(session_id: str):
    """Get status of a specific live view session"""
    try:
        from services.live_view_service import get_live_view_service

        # Get default config for service access
        config = get_settings_service().get_automation_config("strands")
        if not config:
            raise HTTPException(status_code=500, detail="Configuration not available")

        # Get session status from agent
        from order_queue import get_order_queue

        order_queue = get_order_queue()
        agent = order_queue.active_agents.get(session_id)

        if not agent:
            raise HTTPException(status_code=404, detail="Live view session not found")

        if hasattr(agent, "get_session_status"):
            return agent.get_session_status()
        else:
            return {"exists": True, "status": "active", "session_id": session_id}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get live session status: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.delete("/api/live-view/sessions/{session_id}")
async def terminate_live_session(session_id: str):
    """Terminate a live view session"""
    try:
        from services.live_view_service import get_live_view_service

        # Get default config for service access
        config = get_settings_service().get_automation_config("strands")
        if not config:
            raise HTTPException(status_code=500, detail="Configuration not available")

        # Terminate session via agent cleanup
        from order_queue import get_order_queue

        order_queue = get_order_queue()
        agent = order_queue.active_agents.get(session_id)

        if not agent:
            raise HTTPException(status_code=404, detail="Live view session not found")

        # Just remove agent from active list, preserve browser session
        if session_id in order_queue.active_agents:
            del order_queue.active_agents[session_id]

        return {
            "message": f"Live view session {session_id} disconnected, browser session preserved"
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to terminate live session: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/orders/{order_id}/session-replay")
async def get_session_replay(order_id: str):
    """Get session replay information for an order"""
    try:
        order = db_manager.get_order(order_id)
        if not order:
            raise HTTPException(status_code=404, detail="Order not found")

        # Get session replay info from database
        replay_info = db_manager.get_session_replay_info(order_id)

        if not replay_info.get("enabled") or not replay_info.get("s3_bucket"):
            raise HTTPException(
                status_code=404, detail="Session replay not available for this order"
            )

        return {
            "order_id": order_id,
            "session_id": replay_info.get("session_id"),
            "s3_bucket": replay_info.get("s3_bucket"),
            "s3_prefix": replay_info.get("s3_prefix"),
            "replay_available": True,
            "automation_method": order.automation_method,
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get session replay for order {order_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/orders/{order_id}/session-replay/status")
async def get_session_replay_status(order_id: str):
    """Get detailed session replay status and metadata"""
    try:
        order = db_manager.get_order(order_id)
        if not order:
            raise HTTPException(status_code=404, detail="Order not found")

        # Get session replay info from database
        replay_info = db_manager.get_session_replay_info(order_id)

        if not replay_info.get("enabled"):
            return {
                "order_id": order_id,
                "replay_available": False,
                "reason": "Session replay was not enabled for this order",
                "automation_method": order.automation_method,
            }

        # Check if S3 data exists (this would require AWS SDK in a real implementation)
        # For now, we'll assume it exists if the database has the info
        s3_bucket = replay_info.get("s3_bucket")
        s3_prefix = replay_info.get("s3_prefix")
        session_id = replay_info.get("session_id")

        if not s3_bucket or not s3_prefix:
            return {
                "order_id": order_id,
                "replay_available": False,
                "reason": "Session replay S3 configuration is incomplete",
                "automation_method": order.automation_method,
            }

        return {
            "order_id": order_id,
            "session_id": session_id,
            "s3_bucket": s3_bucket,
            "s3_prefix": s3_prefix,
            "replay_available": True,
            "automation_method": order.automation_method,
            "cli_commands": {
                "view_specific": f"python view_recordings.py --bucket {s3_bucket} --prefix {s3_prefix} --session {session_id}",
                "view_latest": f"python view_recordings.py --bucket {s3_bucket} --prefix {s3_prefix}",
                "interactive": "python -m live_view_sessionreplay.browser_interactive_session",
            },
            "documentation_url": "https://docs.aws.amazon.com/bedrock/latest/userguide/agentcore-browser-observability.html",
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get session replay status for order {order_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/orders/{order_id}/retry")
async def retry_order(order_id: str, background_tasks: BackgroundTasks):
    """Retry a failed order"""
    try:
        order = db_manager.get_order(order_id)
        if not order:
            raise HTTPException(status_code=404, detail="Order not found")

        if order.status not in [OrderStatus.FAILED, OrderStatus.CANCELLED]:
            raise HTTPException(
                status_code=400, detail="Only failed or cancelled orders can be retried"
            )

        # Reset order status to pending
        db_manager.update_order_status(order_id, OrderStatus.PENDING)

        # Add back to queue
        background_tasks.add_task(order_queue.process_order, order_id)

        # Broadcast update
        await broadcast_update({"type": "order_retried", "order_id": order_id})

        return {"message": "Order queued for retry", "order_id": order_id}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to retry order {order_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.delete("/api/orders/{order_id}")
async def cancel_order(order_id: str):
    """Cancel an order"""
    try:
        success = await order_queue.cancel_order(order_id)
        if not success:
            raise HTTPException(
                status_code=404, detail="Order not found or cannot be cancelled"
            )

        # Broadcast cancellation
        await broadcast_update({"type": "order_cancelled", "order_id": order_id})

        return {"message": "Order cancelled successfully"}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to cancel order {order_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.delete("/api/orders/{order_id}/force")
async def force_delete_order(order_id: str):
    """Force delete an order regardless of status"""
    cleanup_errors = []
    
    # Set overall timeout for the entire operation
    try:
        return await asyncio.wait_for(_force_delete_order_impl(order_id), timeout=10.0)
    except asyncio.TimeoutError:
        logger.error(f"Force delete timed out for order {order_id}")
        raise HTTPException(status_code=500, detail="Force delete operation timed out")
    except Exception as e:
        logger.error(f"Critical error during force delete of order {order_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Force delete failed: {str(e)}")


async def _force_delete_order_impl(order_id: str):
    """Implementation of force delete with timeout protection"""
    cleanup_errors = []
    
    try:
        # Get order first to check if it exists
        order = db_manager.get_order(order_id)
        if not order:
            raise HTTPException(status_code=404, detail="Order not found")

        logger.info(f"Starting force delete for order {order_id}")

        # Step 1: Aggressively force stop any running automation
        if order_id in order_queue.processing_orders:
            try:
                task = order_queue.processing_orders[order_id]
                if not task.done():
                    # Cancel the task
                    task.cancel()
                    logger.info(f"Cancelled running task for order {order_id}")
                    
                    # Wait for cancellation with timeout
                    try:
                        await asyncio.wait_for(task, timeout=3.0)
                        logger.info(f"Task for order {order_id} cancelled successfully")
                    except asyncio.CancelledError:
                        logger.info(f"Task for order {order_id} was cancelled")
                    except asyncio.TimeoutError:
                        logger.warning(f"Task for order {order_id} did not respond to cancellation within 3 seconds")
                    except Exception as task_error:
                        logger.warning(f"Task cleanup error for {order_id}: {task_error}")
                        
                # Force remove from processing orders immediately
                if order_id in order_queue.processing_orders:
                    del order_queue.processing_orders[order_id]
                    logger.info(f"Forcibly removed {order_id} from processing_orders")
                        
            except Exception as e:
                cleanup_errors.append(f"Task cancellation: {str(e)}")
                logger.warning(f"Failed to cancel task for order {order_id}: {e}")
                
                # Still try to remove from processing orders even if cancellation failed
                try:
                    if order_id in order_queue.processing_orders:
                        del order_queue.processing_orders[order_id]
                        logger.info(f"Forcibly removed {order_id} from processing_orders after cancellation failure")
                except Exception as remove_error:
                    logger.warning(f"Failed to remove {order_id} from processing_orders: {remove_error}")

        # Step 2: Clean up browser session with multiple attempts
        browser_cleanup_success = False
        for attempt in range(2):
            try:
                from services.browser_service import get_browser_service

                # Try both strands and nova_act configs
                for method in ["strands", "nova_act"]:
                    try:
                        config = get_settings_service().get_automation_config(method)
                        if config:
                            browser_service = get_browser_service(config, db_manager)
                            browser_service.cleanup_session(order_id, force=True)
                            logger.info(f"Cleaned up browser session for order {order_id} (method: {method})")
                            browser_cleanup_success = True
                            break
                    except Exception as method_error:
                        logger.debug(f"Browser cleanup failed for {method}: {method_error}")
                        continue
                        
                if browser_cleanup_success:
                    break
                    
            except Exception as e:
                cleanup_errors.append(f"Browser cleanup attempt {attempt + 1}: {str(e)}")
                logger.warning(f"Browser cleanup attempt {attempt + 1} failed for order {order_id}: {e}")
                if attempt == 0:
                    await asyncio.sleep(0.5)  # Brief pause before retry

        # Step 3: Clean up remaining queue data structures

        try:
            if order_id in order_queue.active_agents:
                agent = order_queue.active_agents[order_id]
                # Try to cleanup agent gracefully with timeout
                if hasattr(agent, 'cleanup'):
                    try:
                        # Use asyncio.wait_for with short timeout for agent cleanup
                        await asyncio.wait_for(agent.cleanup(), timeout=1.0)
                    except asyncio.TimeoutError:
                        logger.warning(f"Agent cleanup timed out for {order_id}")
                    except Exception as agent_cleanup_error:
                        logger.warning(f"Agent cleanup error: {agent_cleanup_error}")
                
                # Always remove from active_agents regardless of cleanup success
                del order_queue.active_agents[order_id]
                logger.debug(f"Removed {order_id} from active_agents")
        except Exception as e:
            cleanup_errors.append(f"Active agents cleanup: {str(e)}")
            logger.warning(f"Failed to remove {order_id} from active_agents: {e}")

        # Step 4: Delete from database
        try:
            success = db_manager.delete_order(order_id)
            if not success:
                raise HTTPException(
                    status_code=500, detail="Failed to delete order from database"
                )
            logger.info(f"Deleted order {order_id} from database")
        except Exception as e:
            logger.error(f"Database deletion failed for {order_id}: {e}")
            raise HTTPException(status_code=500, detail=f"Database deletion failed: {str(e)}")

        # Step 5: Broadcast deletion (non-critical)
        try:
            await broadcast_update({"type": "order_deleted", "order_id": order_id})
        except Exception as e:
            cleanup_errors.append(f"Broadcast: {str(e)}")
            logger.warning(f"Failed to broadcast deletion for {order_id}: {e}")

        # Log cleanup summary
        if cleanup_errors:
            logger.warning(f"Order {order_id} deleted with cleanup errors: {cleanup_errors}")
            return {
                "message": f"Order {order_id} force deleted successfully", 
                "cleanup_warnings": cleanup_errors
            }
        else:
            logger.info(f"Order {order_id} force deleted successfully with clean cleanup")
            return {"message": f"Order {order_id} force deleted successfully"}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Critical error during force delete of order {order_id}: {e}")
        import traceback
        logger.error(f"Full traceback: {traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=f"Force delete failed: {str(e)}")


@app.delete("/api/orders/cleanup/completed")
async def delete_completed_orders():
    """Delete all completed and failed orders"""
    try:
        deleted_count = db_manager.delete_completed_orders()

        return {
            "message": f"Deleted {deleted_count} completed orders",
            "deleted_count": deleted_count,
        }

    except Exception as e:
        logger.error(f"Failed to delete completed orders: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# Queue Management
@app.get("/api/queue/metrics")
async def get_queue_metrics():
    """Get queue metrics and statistics"""
    try:
        metrics = await order_queue.get_queue_metrics()
        return {
            "queue_status": metrics.queue_status.value,
            "total_orders": metrics.total_orders,
            "pending_orders": metrics.pending_orders,
            "processing_orders": metrics.processing_orders,
            "completed_orders": metrics.completed_orders,
            "failed_orders": metrics.failed_orders,
            "review_queue": metrics.review_queue,
            "avg_processing_time": metrics.avg_processing_time,
            "success_rate": metrics.success_rate,
            "orders_today": metrics.orders_today,
        }

    except Exception as e:
        logger.error(f"Failed to get queue metrics: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/queue/pause")
async def pause_queue():
    """Pause the order queue"""
    try:
        await order_queue.pause()
        return {"message": "Queue paused successfully"}

    except Exception as e:
        logger.error(f"Failed to pause queue: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/queue/resume")
async def resume_queue():
    """Resume the order queue"""
    try:
        await order_queue.resume()
        return {"message": "Queue resumed successfully"}

    except Exception as e:
        logger.error(f"Failed to resume queue: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/queue/status")
async def get_queue_status():
    """Get current queue status"""
    try:
        status = "active"  # Default status
        if hasattr(order_queue, "is_paused") and order_queue.is_paused:
            status = "paused"
        elif hasattr(order_queue, "paused") and order_queue.paused:
            status = "paused"

        return {"status": status}

    except Exception as e:
        logger.error(f"Failed to get queue status: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# Performance Metrics
@app.get("/api/metrics/performance")
async def get_performance_metrics():
    """Get system performance metrics"""
    try:
        # Get queue metrics
        queue_metrics = await order_queue.get_queue_metrics()

        # Calculate performance metrics
        total_orders = queue_metrics.total_orders
        success_rate = queue_metrics.success_rate
        avg_processing_time = queue_metrics.avg_processing_time

        # Get agent performance (if available)
        agent_performance = {
            "nova_agent": {
                "success_rate": 0.85,
                "avg_processing_time": 120,
                "total_processed": total_orders // 2 if total_orders > 0 else 0,
            },
            "playwright_mcp": {
                "success_rate": 0.78,
                "avg_processing_time": 180,
                "total_processed": total_orders // 2 if total_orders > 0 else 0,
            },
        }

        return {
            "metrics": {
                "overall_metrics": {
                    "total_orders": total_orders,
                    "success_rate": success_rate,
                    "avg_processing_time": avg_processing_time,
                    "orders_today": queue_metrics.orders_today,
                },
                "agent_performance": agent_performance,
                "queue_status": queue_metrics.queue_status.value,
                "timestamp": datetime.now().isoformat(),
            }
        }

    except Exception as e:
        logger.error(f"Failed to get performance metrics: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# Note: AgentCore Browser Management APIs removed
# Using default aws.browser.v1 - no manual browser management needed


# Configuration Management
@app.get("/api/config/retailers")
async def get_retailers():
    """Get supported retailers from database"""
    try:
        # Get retailer URLs from database
        retailer_urls = db_manager.get_retailer_urls()

        # Transform to expected format - group by retailer
        formatted_configs = {}
        supported_retailers = []

        # Group URLs by retailer
        retailer_groups = {}
        for url in retailer_urls:
            retailer = url["retailer"]
            if retailer not in retailer_groups:
                retailer_groups[retailer] = []
            retailer_groups[retailer].append(url)

        # Create formatted configs
        for retailer, urls in retailer_groups.items():
            # Find default URL
            default_url = next(
                (url for url in urls if url["is_default"]), urls[0] if urls else None
            )

            formatted_configs[retailer] = {
                "name": retailer.replace("_", " ").title(),
                "base_url": default_url["starting_url"] if default_url else "",
                "automation_methods": ["strands", "nova_act"],
                "preferred_method": "strands",
                "status": "active",
                "priority": 999,
                "requires_account": False,
            }
            supported_retailers.append(retailer)

        return {
            "supported_retailers": supported_retailers,
            "retailer_configs": formatted_configs,
        }

    except Exception as e:
        logger.error(f"Failed to get retailers: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/config/retailer-urls")
async def get_retailer_urls(retailer: Optional[str] = None):
    """Get retailer URL mappings"""
    try:
        urls = db_manager.get_retailer_urls(retailer)
        return {"retailer_urls": urls}
    except Exception as e:
        logger.error(f"Failed to get retailer URLs: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/config/retailer-urls")
async def add_retailer_url(request: dict):
    """Add a new retailer URL mapping"""
    try:
        required_fields = ["retailer", "website_name", "starting_url"]
        for field in required_fields:
            if field not in request:
                raise HTTPException(
                    status_code=400, detail=f"Missing required field: {field}"
                )

        url_id = db_manager.add_retailer_url(
            retailer=request["retailer"],
            website_name=request["website_name"],
            starting_url=request["starting_url"],
            is_default=request.get("is_default", False),
        )

        return {"status": "success", "url_id": url_id}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to add retailer URL: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.put("/api/config/retailer-urls/{url_id}")
async def update_retailer_url(url_id: str, request: dict):
    """Update a retailer URL mapping"""
    try:
        success = db_manager.update_retailer_url(url_id, **request)
        if not success:
            raise HTTPException(status_code=404, detail="Retailer URL not found")

        return {"status": "success"}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to update retailer URL: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.delete("/api/config/retailer-urls/{url_id}")
async def delete_retailer_url(url_id: str):
    """Delete a retailer URL mapping"""
    try:
        success = db_manager.delete_retailer_url(url_id)
        if not success:
            raise HTTPException(status_code=404, detail="Retailer URL not found")

        return {"status": "success"}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to delete retailer URL: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/config/automation-methods")
async def get_automation_methods():
    """Get available automation methods"""
    try:
        return {
            "automation_methods": [
                {
                    "id": "strands",
                    "name": "Strands + AgentCore Browser + Browser Tools",
                    "description": "Unified Strands automation with comprehensive browser capabilities, screenshots, session replay, and manual control",
                },
                {
                    "id": "nova_act",
                    "name": "Nova Act + AgentCore Browser",
                    "description": "Advanced AI-powered automation using Nova Act with AgentCore Browser",
                },
            ]
        }

    except Exception as e:
        logger.error(f"Failed to get automation methods: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# Removed duplicate - using /api/settings/config instead


# Removed duplicate - using /api/settings/config instead


# Session Management
@app.get("/api/sessions")
async def get_sessions():
    """Get browser sessions status"""
    try:
        # Mock session data for now - in real implementation this would come from browser session manager
        sessions = [
            {
                "id": "session_1",
                "status": "active",
                "retailer": "sample_retailer",
                "created_at": datetime.now().isoformat(),
                "last_activity": datetime.now().isoformat(),
                "orders_processed": 3,
                "current_order": None,
            },
            {
                "id": "session_2",
                "status": "idle",
                "retailer": "net_a_porter",
                "created_at": datetime.now().isoformat(),
                "last_activity": datetime.now().isoformat(),
                "orders_processed": 1,
                "current_order": None,
            },
        ]

        return {
            "sessions": sessions,
            "total": len(sessions),
            "active_count": len([s for s in sessions if s["status"] == "active"]),
            "idle_count": len([s for s in sessions if s["status"] == "idle"]),
        }

    except Exception as e:
        logger.error(f"Failed to get sessions: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# Human Review
@app.get("/api/review/queue")
async def get_review_queue():
    """Get orders requiring human review"""
    try:
        # Get orders that require human review
        orders = db_manager.get_orders_requiring_human_review()

        return {"orders": [order.to_dict() for order in orders], "total": len(orders)}

    except Exception as e:
        logger.error(f"Failed to get review queue: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/review/{order_id}/resolve")
async def resolve_review(order_id: str, request: UpdateOrderRequest):
    """Resolve human review for an order"""
    try:
        order = db_manager.get_order(order_id)
        if not order:
            raise HTTPException(status_code=404, detail="Order not found")

        if order.status != OrderStatus.REQUIRES_HUMAN:
            raise HTTPException(
                status_code=400, detail="Order does not require human review"
            )

        # Update order status
        status = (
            OrderStatus(request.status.upper())
            if request.status
            else OrderStatus.COMPLETED
        )
        db_manager.update_order_status(
            order_id=order_id,
            status=status,
            requires_human_review=False,
            human_review_notes=request.human_review_notes,
        )

        # Get updated order
        updated_order = db_manager.get_order(order_id)

        # Broadcast update
        await broadcast_update(
            {
                "type": "review_resolved",
                "order": updated_order.to_dict() if updated_order else None,
            }
        )

        return updated_order.to_dict() if updated_order else None

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to resolve review for order {order_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# Test endpoints for demo
@app.post("/api/test/sample-order")
async def create_sample_order(automation_method: str = "strands"):
    """Create a sample order for testing"""
    try:
        # Sample order data
        sample_order = {
            "retailer": "sample_retailer",
            "automation_method": automation_method,
            "product": {
                "url": "https://example.com/product/sample-item-12345",
                "name": "Sample Product Item",
                "size": None,
                "color": "Black",
                "quantity": 1,
                "price": 100.00,
            },
            "customer_name": "Jane Doe",
            "customer_email": "jane.doe@example.com",
            "shipping_address": {
                "first_name": "Jane",
                "last_name": "Doe",
                "address_line_1": "123 Main St",
                "city": "New York",
                "state": "NY",
                "postal_code": "10001",
                "country": "US",
                "phone": "555-123-4567",
            },
            "payment_info": {
                "payment_token": "tok_sample_12345",
                "cardholder_name": "Jane Doe",
            },
            "priority": "normal",
        }

        # Create the order using the existing endpoint logic
        order_id = await order_queue.add_order(
            retailer=sample_order["retailer"],
            automation_method=automation_method,
            product_name=sample_order["product"]["name"],
            product_url=sample_order["product"]["url"],
            customer_name=sample_order["customer_name"],
            customer_email=sample_order["customer_email"],
            shipping_address=sample_order["shipping_address"],
            product_size=sample_order["product"]["size"],
            product_color=sample_order["product"]["color"],
            product_price=sample_order["product"]["price"],
            payment_token=sample_order["payment_info"]["payment_token"],
            priority=OrderPriority.NORMAL,
        )

        # Get created order
        order = db_manager.get_order(order_id)

        # Broadcast order creation
        await broadcast_update(
            {"type": "order_created", "order": order.to_dict() if order else None}
        )

        return {
            "order_id": order_id,
            "status": "created",
            "message": f"Sample order created with {automation_method}",
        }

    except Exception as e:
        logger.error(f"Failed to create sample order: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/automation/compare")
async def compare_automation_methods():
    """Compare automation methods by creating sample orders with both"""
    try:
        # Create sample orders with both methods
        results = []

        for method in ["strands", "nova_act"]:
            try:
                order_id = await order_queue.add_order(
                    retailer="sample_retailer",
                    automation_method=method,
                    product_name="Sample Product Item",
                    product_url="https://example.com/product/sample-item-12345",
                    customer_name="Jane Doe",
                    customer_email="jane.doe@example.com",
                    shipping_address={
                        "first_name": "Jane",
                        "last_name": "Doe",
                        "address_line_1": "123 Main St",
                        "city": "New York",
                        "state": "NY",
                        "postal_code": "10001",
                        "country": "US",
                        "phone": "555-123-4567",
                    },
                    product_color="Black",
                    product_price=1890.00,
                    payment_token="tok_sample_12345",
                    priority=OrderPriority.NORMAL,
                )
                results.append({"method": method, "order_id": order_id})
            except Exception as e:
                logger.error(f"Failed to create {method} order: {e}")
                results.append({"method": method, "error": str(e)})

        return {
            "comparison_id": f"comp_{datetime.now().strftime('%Y%m%d_%H%M%S')}",
            "results": results,
            "message": "Comparison orders created successfully",
        }

    except Exception as e:
        logger.error(f"Failed to create comparison orders: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# WebSocket endpoint
@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await manager.connect(websocket)
    try:
        while True:
            # Keep connection alive
            data = await websocket.receive_text()
            # Echo back for heartbeat
            await websocket.send_text(
                json.dumps(
                    {"type": "heartbeat", "timestamp": datetime.now().isoformat()}
                )
            )
    except WebSocketDisconnect:
        manager.disconnect(websocket)


# Error handlers
@app.exception_handler(404)
async def not_found_handler(request, exc):
    return JSONResponse(status_code=404, content={"detail": "Resource not found"})


@app.exception_handler(500)
async def internal_error_handler(request, exc):
    logger.error(f"Internal server error: {exc}")
    return JSONResponse(status_code=500, content={"detail": "Internal server error"})


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("app:app", host="0.0.0.0", port=8000, reload=True, log_level="info")


# Settings and Configuration endpoints
@app.get("/api/settings/aws/status")
async def get_aws_status():
    """Get current AWS configuration status"""
    try:
        settings_service = SettingsService(db_manager)
        config = settings_service.get_aws_status()
        return config
    except Exception as e:
        logger.error(f"Failed to get AWS status: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/settings/aws/search-iam-roles")
async def search_iam_roles(q: str = ""):
    """Search IAM execution roles"""
    try:
        settings_service = SettingsService(db_manager)
        roles = settings_service.search_execution_roles(q)
        return {"execution_roles": roles}
    except Exception as e:
        logger.error(f"Failed to search IAM roles: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/settings/aws/search-s3-buckets")
async def search_s3_buckets(q: str = ""):
    """Search S3 buckets"""
    try:
        settings_service = SettingsService(db_manager)
        buckets = settings_service.search_s3_buckets(q)
        return {"s3_buckets": buckets}
    except Exception as e:
        logger.error(f"Failed to search S3 buckets: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/settings/aws/setup")
async def setup_aws_environment(request: dict):
    """Set up complete AWS environment for AgentCore"""
    try:
        settings_service = SettingsService(db_manager)

        role_name = request.get("role_name", "AgentCoreExecutionRole")
        bucket_name = request.get("bucket_name")

        result = settings_service.setup_complete_environment(role_name, bucket_name)

        # Update config if successful
        if result["overall_status"] in ["success", "partial"]:
            updates = {}
            if (
                result.get("execution_role")
                and result["execution_role"]["status"] == "success"
            ):
                updates["recording_role_arn"] = result["execution_role"]["role_arn"]

            if result.get("s3_bucket") and result["s3_bucket"]["status"] == "success":
                updates["session_replay_s3_bucket"] = result["s3_bucket"]["bucket_name"]

            if updates:
                settings_service.update_system_config(updates)

        return result
    except Exception as e:
        logger.error(f"Failed to setup AWS environment: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/settings/aws/create-role")
async def create_execution_role(request: dict):
    """Create IAM execution role for AgentCore"""
    try:
        settings_service = SettingsService(db_manager)
        role_name = request.get("role_name", "AgentCoreExecutionRole")

        result = settings_service.create_execution_role(role_name)

        # Update config if successful
        if result["status"] == "success":
            settings_service.update_system_config(
                {"recording_role_arn": result["role_arn"]}
            )

        return result
    except Exception as e:
        logger.error(f"Failed to create execution role: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/settings/aws/create-bucket")
async def create_s3_bucket(request: dict):
    """Create S3 bucket for session recordings"""
    try:
        settings_service = SettingsService(db_manager)
        bucket_name = request["bucket_name"]

        result = settings_service.create_s3_bucket(bucket_name)

        # Update config if successful
        if result["status"] == "success":
            settings_service.update_system_config(
                {"session_replay_s3_bucket": result["bucket_name"]}
            )

        return result
    except Exception as e:
        logger.error(f"Failed to create S3 bucket: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/settings/config")
async def get_settings_config():
    """Get current system configuration"""
    try:
        settings_service = SettingsService(db_manager)
        config = settings_service.get_system_config()
        # Remove sensitive information for API response
        safe_config = {
            k: v
            for k, v in config.items()
            if not k.lower().endswith("_key") or k == "nova_act_api_key"
        }
        return {"config": safe_config}
    except Exception as e:
        logger.error(f"Failed to get system config: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.put("/api/settings/config")
async def update_settings_config(request: dict):
    """Update system configuration"""
    try:
        settings_service = SettingsService(db_manager)

        # Handle both single key-value updates and bulk config updates
        if "key" in request and "value" in request:
            # Single key-value update
            config_updates = {request["key"]: request["value"]}
        else:
            # Bulk config update
            config_updates = request.get("config", {})

        if not config_updates:
            return {"status": "success", "message": "No configuration updates provided"}

        result = settings_service.update_system_config(config_updates)
        return result

    except Exception as e:
        logger.error(f"Failed to update system config: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/settings/config")
async def save_settings_config(request: dict):
    """Save complete system configuration"""
    try:
        settings_service = SettingsService(db_manager)
        config_updates = request.get("config", {})

        if not config_updates:
            return {"status": "success", "message": "No configuration provided"}

        result = settings_service.update_system_config(config_updates)
        
        if result:
            return {"status": "success", "message": "Configuration saved successfully"}
        else:
            return {"status": "error", "message": "Failed to save configuration"}

    except Exception as e:
        logger.error(f"Failed to save system config: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/orders/upload-csv")
async def upload_orders_csv(
    file: UploadFile = File(...), 
    automation_method: str = Form("nova_act"),
    ai_model: str = Form("nova_act"),
    background_tasks: BackgroundTasks = None
):
    """Upload CSV file and create multiple orders"""
    try:
        # Validate file type
        if not file.filename.lower().endswith(".csv"):
            raise HTTPException(status_code=400, detail="File must be a CSV file")

        # Read CSV content
        content = await file.read()
        csv_content = content.decode("utf-8")

        # Parse CSV
        csv_reader = csv.DictReader(io.StringIO(csv_content))

        created_orders = []
        errors = []

        # Process each row
        for row_num, row in enumerate(
            csv_reader, start=2
        ):  # Start at 2 because row 1 is header
            try:
                # Map CSV columns to order fields
                # Expected CSV format: name,brand,description,color,size,price,curateditem_url
                product_name = row.get("name", "").strip()
                brand = row.get("brand", "").strip()
                description = row.get("description", "").strip()
                color = row.get("color", "").strip()
                size = row.get("size", "").strip()
                price_str = row.get("price", "").strip()
                product_url = row.get("curateditem_url", "").strip()

                # Validate required fields
                if not product_name:
                    errors.append(f"Row {row_num}: Missing product name")
                    continue

                if not product_url:
                    errors.append(f"Row {row_num}: Missing product URL")
                    continue

                # Parse price
                try:
                    price = float(price_str) if price_str else None
                except ValueError:
                    price = None

                # Create full product name with brand if available
                full_product_name = (
                    f"{brand} {product_name}".strip() if brand else product_name
                )

                # Determine retailer from URL (generic domain extraction)
                retailer = "unknown"
                url_lower = product_url.lower()
                
                # Extract domain from URL for retailer identification
                try:
                    from urllib.parse import urlparse
                    parsed_url = urlparse(product_url)
                    domain = parsed_url.netloc.replace('www.', '')
                    # Use domain as retailer identifier (e.g., "example.com" -> "example")
                    retailer = domain.split('.')[0] if domain else "unknown"
                except Exception:
                    retailer = "unknown"
                
                # Handle affiliate links that contain the actual retailer in the URL
                if "murl=" in url_lower:
                    # Extract the actual URL from affiliate link
                    import urllib.parse
                    if "murl=" in url_lower:
                        try:
                            # Find murl parameter and decode it
                            murl_start = url_lower.find("murl=") + 5
                            murl_end = url_lower.find("&", murl_start)
                            if murl_end == -1:
                                murl_end = len(url_lower)
                            encoded_url = product_url[murl_start:murl_end]
                            decoded_url = urllib.parse.unquote(encoded_url).lower()
                            
                            if "neimanmarcus.com" in decoded_url:
                                retailer = "neiman_marcus"
                            elif "net-a-porter.com" in decoded_url:
                                retailer = "net_a_porter"
                            elif "mytheresa.com" in decoded_url:
                                retailer = "mytheresa"
                        except Exception:
                            pass
                
                # Handle other affiliate patterns
                if ("jdoqocy.com" in url_lower or "dpbolvw.net" in url_lower) and "mytheresa.com" in url_lower:
                    retailer = "mytheresa"

                # Create order with provided settings
                order_id = await order_queue.add_order(
                    retailer=retailer,
                    automation_method=automation_method,
                    ai_model=ai_model,
                    product_name=full_product_name,
                    product_url=product_url,
                    customer_name="CSV Import Customer",
                    customer_email="csv-import@example.com",
                    shipping_address={
                        "first_name": "CSV",
                        "last_name": "Import",
                        "address_line_1": "123 Import Street",
                        "city": "Import City",
                        "state": "CA",
                        "postal_code": "90210",
                        "country": "US",
                    },
                    product_size=size if size else None,
                    product_color=color if color else None,
                    product_price=price,
                    payment_token=f'tok_csv_import_{datetime.now().strftime("%Y%m%d_%H%M%S")}_{row_num}',
                    priority=OrderPriority.NORMAL,
                    instructions=(
                        f"Imported from CSV. Description: {description}"
                        if description
                        else "Imported from CSV"
                    ),
                )

                created_orders.append(order_id)

            except Exception as row_error:
                errors.append(f"Row {row_num}: {str(row_error)}")
                logger.error(f"Error processing CSV row {row_num}: {row_error}")

        # Broadcast update about bulk order creation
        if created_orders:
            await broadcast_update(
                {
                    "type": "bulk_orders_created",
                    "count": len(created_orders),
                    "order_ids": created_orders,
                }
            )

        return {
            "success": True,
            "created_count": len(created_orders),
            "error_count": len(errors),
            "created_orders": created_orders,
            "errors": errors[:10],  # Limit errors to first 10 to avoid huge responses
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to process CSV upload: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to process CSV: {str(e)}")


# ============================================================================
# VOICE CONVERSATION ENDPOINTS (Nova Sonic Integration)
# ============================================================================

@app.post("/api/voice/conversation/start")
async def start_voice_conversation():
    """Start a new voice conversation session"""
    try:
        from services.voice_service import get_voice_service
        import uuid
        
        config_manager = get_config_manager(db_manager)
        voice_service = get_voice_service(config_manager=config_manager)
        conversation_id = str(uuid.uuid4())
        
        result = await voice_service.start_conversation(conversation_id)
        
        return {
            "success": True,
            "conversation_id": conversation_id,
            "audio": result["audio"],
            "text": result["text"],
            "state": result["state"],
            "provider": voice_service.voice_provider,
            "audio_format": voice_service.voice_config.get("output_format", "pcm"),
            "sample_rate": voice_service.voice_config.get("output_sample_rate", 24000)
        }
        
    except Exception as e:
        logger.error(f"Failed to start voice conversation: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/voice/conversation/{conversation_id}/process")
async def process_voice_input(
    conversation_id: str,
    audio_file: UploadFile = File(...)
):
    """Process voice input and return response"""
    try:
        from services.voice_service import get_voice_service
        
        config_manager = get_config_manager(db_manager)
        voice_service = get_voice_service(config_manager=config_manager)
        
        # Read audio data
        audio_data = await audio_file.read()
        
        # Process speech
        result = await voice_service.process_speech(conversation_id, audio_data)
        
        # Broadcast update
        await broadcast_update({
            "type": "voice_interaction",
            "conversation_id": conversation_id,
            "user_text": result["user_text"],
            "assistant_text": result["assistant_text"],
            "provider": result.get("provider", "unknown")
        })
        
        return {
            "success": True,
            "conversation_id": conversation_id,
            "user_text": result["user_text"],
            "assistant_text": result["assistant_text"],
            "audio": result["audio"],
            "audio_format": result.get("audio_format", "pcm"),
            "sample_rate": result.get("sample_rate", 24000),
            "state": result["state"],
            "order_data": result["order_data"],
            "ready_to_submit": result["ready_to_submit"],
            "provider": result.get("provider", "unknown")
        }
        
    except Exception as e:
        logger.error(f"Failed to process voice input: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/voice/conversation/{conversation_id}/state")
async def get_conversation_state(conversation_id: str):
    """Get current state of voice conversation"""
    try:
        from services.voice_service import get_voice_service
        
        config_manager = get_config_manager(db_manager)
        voice_service = get_voice_service(config_manager=config_manager)
        state = voice_service.get_conversation_state(conversation_id)
        
        if state is None:
            raise HTTPException(status_code=404, detail="Conversation not found")
        
        return {
            "success": True,
            "conversation_id": conversation_id,
            "state": state["state"],
            "order_data": state["order_data"],
            "conversation_history": state["conversation_history"]
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get conversation state: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/voice/conversation/{conversation_id}/summary")
async def get_order_summary(conversation_id: str):
    """Get order summary with voice confirmation"""
    try:
        from services.voice_service import get_voice_service
        
        config_manager = get_config_manager(db_manager)
        voice_service = get_voice_service(config_manager=config_manager)
        summary = await voice_service.get_order_summary(conversation_id)
        
        return {
            "success": True,
            "text": summary["text"],
            "audio": summary["audio"],
            "order_data": summary["order_data"],
            "ready_to_submit": summary["ready_to_submit"]
        }
        
    except Exception as e:
        logger.error(f"Failed to get order summary: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/voice/conversation/{conversation_id}/submit")
async def submit_voice_order(
    conversation_id: str,
    automation_method: str = "strands",
    ai_model: Optional[str] = None,
    background_tasks: BackgroundTasks = None
):
    """Submit order created through voice conversation for browser automation"""
    try:
        from services.voice_service import get_voice_service

        voice_service = get_voice_service()
        conversation = voice_service.get_conversation_state(conversation_id)

        if conversation is None:
            raise HTTPException(status_code=404, detail="Conversation not found")

        order_data = conversation["order_data"]

        # Validate ALL required fields for browser automation
        required_fields = {
            "product_name": "Product name",
            "quantity": "Quantity",
            "customer_name": "Customer name",
            "customer_email": "Email address",
            "phone": "Phone number",
            "street": "Street address",
            "city": "City",
            "state": "State",
            "postal_code": "Postal code"
        }

        missing_fields = [v for k, v in required_fields.items() if k not in order_data or not order_data[k]]

        if missing_fields:
            raise HTTPException(
                status_code=400,
                detail=f"Missing required fields for automation: {', '.join(missing_fields)}. Please complete the voice conversation first."
            )

        # Parse customer name into first/last
        name_parts = order_data["customer_name"].strip().split()
        first_name = name_parts[0] if name_parts else ""
        last_name = " ".join(name_parts[1:]) if len(name_parts) > 1 else ""

        # Transform voice data to standard order format
        order_request_data = {
            "retailer": order_data.get("retailer", "ShopZone"),
            "automation_method": automation_method,
            "ai_model": ai_model or order_data.get("ai_model", "us.anthropic.claude-sonnet-4-20250514-v1:0"),
            "product": {
                "url": order_data.get("product_url", ""),
                "name": order_data["product_name"],
                "size": order_data.get("size", ""),
                "color": order_data.get("color", ""),
                "quantity": int(order_data.get("quantity", 1)),
                "price": float(order_data["price"]) if "price" in order_data and order_data["price"] else None
            },
            "customer_name": order_data["customer_name"],
            "customer_email": order_data["customer_email"],
            "shipping_address": {
                "first_name": first_name,
                "last_name": last_name,
                "address_line_1": order_data["street"],
                "city": order_data["city"],
                "state": order_data["state"].upper(),  # Ensure uppercase
                "postal_code": order_data["postal_code"],
                "country": order_data.get("country", "US"),
                "phone": order_data["phone"]
            },
            "payment_info": {
                "payment_token": f"tok_voice_{conversation_id[:12]}",  # Demo token
                "cardholder_name": order_data["customer_name"]
            },
            "priority": "normal",
            "instructions": f"Created via voice conversation {conversation_id}. Voice-automated order."
        }

        logger.info(f"Transformed voice order data: {json.dumps(order_request_data, indent=2)}")

        # Use the standard create_order endpoint logic
        # This ensures consistency with manual orders
        request = CreateOrderRequest(**order_request_data)

        # Create the order using the standard flow
        result = await create_order(request, background_tasks or BackgroundTasks())

        # End conversation
        voice_service.end_conversation(conversation_id)

        # Broadcast voice order creation
        await broadcast_update({
            "type": "voice_order_created",
            "conversation_id": conversation_id,
            "order_id": result["order_id"],
            "automation_method": automation_method
        })

        logger.info(f"Voice order {result['order_id']} submitted for {automation_method} automation")

        return {
            "success": True,
            "order_id": result["order_id"],
            "automation_method": automation_method,
            "message": f"Order created and queued for {automation_method} automation. Browser will start processing shortly."
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to submit voice order: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@app.delete("/api/voice/conversation/{conversation_id}")
async def end_voice_conversation(conversation_id: str):
    """End and cleanup voice conversation"""
    try:
        from services.voice_service import get_voice_service
        
        voice_service = get_voice_service()
        voice_service.end_conversation(conversation_id)
        
        return {
            "success": True,
            "message": "Conversation ended"
        }
        
    except Exception as e:
        logger.error(f"Failed to end conversation: {e}")
        raise HTTPException(status_code=500, detail=str(e))
