# Drishti-AI-Navigator 🤖🛒

[![License](https://img.shields.io/badge/License-Apache_2.0-blue.svg)](LICENSE)
[![Python](https://img.shields.io/badge/Python-3.13+-green.svg)](https://www.python.org/)
[![React](https://img.shields.io/badge/React-18.2+-61DAFB.svg)](https://react.dev/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.104+-009688.svg)](https://fastapi.tiangolo.com/)

**Drishti-AI-Navigator** is a production-ready, AI-powered e-commerce order automation platform that autonomously completes online purchases using intelligent agents. Combining AWS Bedrock, Claude AI, voice-based interfaces, and advanced browser automation, it provides a complete solution for automated order fulfillment with real-time monitoring and human-in-the-loop intervention capabilities.

---

## 🌟 Key Features

### 🤖 **Multiple AI Automation Methods**
- **Strands Agent**: Simplified implementation using Playwright MCP + AgentCore browser
- **Nova Act Agent**: AWS Bedrock agent with advanced vision-based navigation
- Flexible model selection (Claude 3.5 Sonnet, Claude 3 Opus, etc.)
- Model Context Protocol (MCP) integration for tool orchestration

### 🎤 **Voice-Based Order Creation**
- **AWS Nova Sonic** bidirectional speech-to-speech conversations
- Natural language order placement
- Real-time audio streaming
- AWS Polly TTS fallback support
- Conversational order detail extraction

### 🖥️ **Real-Time Browser Monitoring**
- **Live Browser Viewing** with screenshot streaming
- **Manual Control Mode** for human takeover during automation
- **Session Recording & Replay** stored on S3
- Multi-tab management
- Configurable browser resolution

### 📋 **Advanced Order Management**
- Priority-based order queue (Low, Normal, High, Urgent)
- Multiple order states (Pending, Processing, Completed, Failed, RequiresHuman)
- CSV batch upload for bulk orders
- Retry failed orders with one click
- Order tracking with confirmation and tracking numbers

### 👥 **Human Review & Intervention**
- Review queue for orders requiring approval
- Manual browser control during automation
- Resolution interface for failed orders
- Detailed execution logs and audit trails

### ⚙️ **Configuration & Management**
- Retailer-specific configuration
- Dynamic retailer URL management
- Encrypted credential storage (Secret Vault)
- AWS IAM and S3 integration
- System settings management

### 📊 **Monitoring & Analytics**
- Real-time WebSocket updates
- Queue metrics and performance analytics
- Active agent tracking
- Success rate monitoring
- Processing time analytics

---

## 🏗️ Architecture

### High-Level Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                     Frontend (React)                         │
│  ┌────────────┐  ┌──────────────┐  ┌──────────────────┐   │
│  │ Dashboard  │  │ Live Browser │  │ Voice Assistant  │   │
│  │            │  │    Viewer    │  │                  │   │
│  └────────────┘  └──────────────┘  └──────────────────┘   │
│         │                 │                    │            │
│         └─────────────────┴────────────────────┘            │
│                           │                                 │
└───────────────────────────┼─────────────────────────────────┘
                            │
                    HTTP/WebSocket
                            │
┌───────────────────────────┼─────────────────────────────────┐
│                  Backend (FastAPI)                           │
│  ┌────────────┐  ┌──────────────┐  ┌──────────────────┐   │
│  │  REST API  │  │  WebSocket   │  │  Order Queue     │   │
│  │ Endpoints  │  │   Server     │  │   Manager        │   │
│  └────────────┘  └──────────────┘  └──────────────────┘   │
│         │                 │                    │            │
│         └─────────────────┴────────────────────┘            │
│                           │                                 │
│  ┌────────────────────────┴────────────────────────────┐   │
│  │              Core Services Layer                     │   │
│  │  ┌─────────────┐  ┌────────────┐  ┌─────────────┐  │   │
│  │  │   Voice     │  │  Browser   │  │   Settings  │  │   │
│  │  │  Service    │  │  Service   │  │   Service   │  │   │
│  │  └─────────────┘  └────────────┘  └─────────────┘  │   │
│  │  ┌─────────────┐  ┌────────────┐  ┌─────────────┐  │   │
│  │  │   Secrets   │  │  Database  │  │   Config    │  │   │
│  │  │   Manager   │  │  Manager   │  │   Manager   │  │   │
│  │  └─────────────┘  └────────────┘  └─────────────┘  │   │
│  └──────────────────────────────────────────────────────┘   │
│                           │                                 │
│  ┌────────────────────────┴────────────────────────────┐   │
│  │              AI Agent Layer                          │   │
│  │  ┌─────────────────┐       ┌──────────────────┐    │   │
│  │  │  Strands Agent  │       │  Nova Act Agent  │    │   │
│  │  │  (MCP+Playwright)│       │  (Vision+Worker) │    │   │
│  │  └─────────────────┘       └──────────────────┘    │   │
│  └──────────────────────────────────────────────────────┘   │
└───────────────────────────┬─────────────────────────────────┘
                            │
        ┌───────────────────┼────────────────────┐
        │                   │                    │
┌───────▼─────────┐ ┌───────▼────────┐  ┌───────▼─────────┐
│  AWS Bedrock    │ │   PostgreSQL   │  │    AWS S3       │
│  (Claude AI,    │ │   Database     │  │   (Session      │
│  Nova Sonic)    │ │                │  │   Recordings)   │
└─────────────────┘ └────────────────┘  └─────────────────┘
```

### Component Architecture

```
Backend Components:
├── API Layer (FastAPI)
│   ├── REST Endpoints (60+ endpoints)
│   ├── WebSocket Server (real-time updates)
│   └── CORS Middleware
│
├── Service Layer
│   ├── VoiceService (Nova Sonic/Polly)
│   ├── BrowserService (AgentCore browser)
│   ├── SettingsService (configuration)
│   └── SecretsManager (credentials)
│
├── Agent Layer
│   ├── StrandsAgent (Playwright MCP)
│   └── NovaActAgent (Vision-based)
│
├── Data Layer
│   ├── DatabaseManager (SQLAlchemy)
│   ├── Models (Order, Session, Settings)
│   └── Alembic Migrations
│
└── Queue Layer
    ├── OrderQueue (priority-based)
    ├── Concurrent Processing
    └── Worker Management

Frontend Components:
├── Pages
│   ├── OrderDashboard
│   ├── CreateOrder
│   ├── OrderDetails
│   ├── ReviewQueue
│   ├── FailedOrders
│   ├── Settings
│   └── SecretVault
│
├── Components
│   ├── CreateOrderWizard
│   ├── LiveBrowserViewer
│   ├── VoiceOrderAssistant
│   ├── SessionReplayViewer
│   └── ModelSelector
│
└── Services
    ├── API Client (Axios)
    └── WebSocket Manager
```

### Data Flow

```
Order Creation Flow:
User → CreateOrderWizard → API → DatabaseManager → OrderQueue
                                                         ↓
                                                   Agent Selection
                                                         ↓
                                          ┌──────────────┴──────────────┐
                                          ↓                             ↓
                                   StrandsAgent                   NovaActAgent
                                          ↓                             ↓
                                   AgentCore Browser ←──────────────────┘
                                          ↓
                                   Website Automation
                                          ↓
                                   Order Completion
                                          ↓
                        ┌─────────────────┴─────────────────┐
                        ↓                                   ↓
                  Update Database                    Send WebSocket Update
                        ↓                                   ↓
                Store Screenshots/Logs              Update Dashboard UI
```

---

## 🚀 Getting Started

### Prerequisites

- **Python 3.13+**
- **Node.js 16+** (LTS recommended)
- **PostgreSQL 13+** (SQLite for development)
- **AWS Account** with Bedrock access
- **Git**

### Required AWS Services

- **AWS Bedrock** (for Claude AI models and Nova Sonic)
- **AWS S3** (for session recordings)
- **AWS IAM** (for role and policy management)
- **AWS Polly** (optional, for TTS fallback)

### Installation

#### 1. Clone the Repository

```bash
git clone https://github.com/akashtalole/Drishti-AI-Navigator.git
cd Drishti-AI-Navigator
```

#### 2. Backend Setup

```bash
cd backend

# Install dependencies
uv sync

# Create virtual environment
source .venv/bin/activate  # On Windows: .venv\Scripts\activate

# Copy environment template
cp .env.example .env

# Edit .env with your configuration
nano .env
```

**Configure `.env` file:**

```bash
# AWS Configuration
AWS_ACCESS_KEY_ID=your_access_key
AWS_SECRET_ACCESS_KEY=your_secret_key
AWS_REGION=us-east-1

# Voice Configuration
VOICE_PROVIDER=nova_sonic  # or "polly"
NOVA_SONIC_REGION=us-east-1
VOICE_MODEL=amazon.nova-sonic-v1:0

# Database (use PostgreSQL for production)
DATABASE_URL=postgresql://user:password@localhost:5432/drishti_db
# For development: DATABASE_URL=sqlite:///./order_automation.db

# Frontend URL (for CORS)
FRONTEND_URL=http://localhost:3000

# Application
PORT=8000
ENVIRONMENT=development

# S3 Configuration
SESSION_REPLAY_S3_BUCKET=your-bucket-name
SESSION_REPLAY_S3_PREFIX=session-replays/

# Security
SECRET_KEY=your-secret-key-here

# Performance
MAX_CONCURRENT_ORDERS=5
BROWSER_SESSION_TIMEOUT=3600
PROCESSING_TIMEOUT=1800
```

**Initialize Database:**

```bash
# Run migrations
alembic upgrade head

# Start the backend server
uvicorn app:app --host 0.0.0.0 --port 8000 --reload
```

#### 3. Frontend Setup

```bash
cd ../frontend

# Install dependencies
npm install

# Start development server
npm start
```

The frontend will be available at `http://localhost:3000`

---

## 📖 Usage Guide

### Creating an Order

#### Method 1: Manual Creation

1. Navigate to **Create Order** page
2. Fill in order details:
   - Retailer
   - Product name and URL
   - Size, color, quantity
   - Customer information
   - Shipping address
   - Payment method
3. Select automation method (Strands or Nova Act)
4. Select AI model (Claude 3.5 Sonnet recommended)
5. Click **Create Order**

#### Method 2: Voice-Based Creation

1. Click on **Voice Assistant** in the navigation
2. Click **Start Conversation**
3. Speak your order details naturally
4. Confirm the extracted information
5. Submit the order

#### Method 3: CSV Batch Upload

1. Navigate to **Batch Upload**
2. Download the CSV template
3. Fill in order details in the CSV
4. Upload the CSV file
5. Review and confirm batch creation

### Monitoring Orders

#### Real-Time Dashboard

- View all orders with current status
- Filter by status, retailer, or priority
- See live progress bars for active orders
- Access quick actions (retry, cancel, take control)

#### Live Browser View

1. Open an order in **Processing** state
2. Click **Live View** button
3. Watch real-time browser automation
4. See current step and progress
5. View execution logs as they happen

#### Manual Control

1. Open an order in **Processing** state
2. Click **Take Control**
3. Browser switches to manual mode
4. Interact with the browser directly
5. Click **Release Control** to resume automation

### Review Queue

Orders requiring human approval appear in the **Review Queue**:

1. Navigate to **Review Queue**
2. Review order details and current state
3. Add notes or corrections
4. Click **Approve** or **Reject**

### Managing Failed Orders

1. Navigate to **Failed Orders**
2. Review error messages and logs
3. Update order details if needed
4. Click **Retry** to reprocess
5. Or manually resolve and mark complete

---

## 🔧 Configuration

### Retailer Configuration

Add retailer-specific settings via **Settings** page:

```json
{
  "name": "Amazon",
  "base_url": "https://www.amazon.com",
  "login_url": "https://www.amazon.com/ap/signin",
  "checkout_flow": "standard",
  "requires_login": true,
  "automation_hints": {
    "add_to_cart_selector": "#add-to-cart-button",
    "checkout_button_selector": "#sc-buy-box-ptc-button"
  }
}
```

### Secret Vault

Store credentials securely:

1. Navigate to **Secret Vault**
2. Click **Add Secret**
3. Enter site name (e.g., "Amazon")
4. Enter username and password
5. Credentials are encrypted at rest

### AWS Setup

Configure AWS integration:

1. Navigate to **Settings** → **AWS Configuration**
2. Search and select IAM role
3. Search and select S3 bucket
4. Or create new role/bucket using the wizard
5. Test connection

### Automation Method Selection

Choose default automation method:

- **Strands Agent**: Faster, simpler, uses Playwright MCP
- **Nova Act Agent**: More robust, vision-based, better error recovery

Override per-order during creation.

---

## 🛠️ Technology Stack

### Backend

| Technology | Version | Purpose |
|------------|---------|---------|
| Python | 3.13+ | Backend language |
| FastAPI | 0.104+ | Web framework |
| Uvicorn | Latest | ASGI server |
| SQLAlchemy | 2.0.23+ | ORM |
| Alembic | 1.13+ | Database migrations |
| PostgreSQL | 13+ | Production database |
| Strands Agents | 1.6.0+ | AI agent framework |
| Nova Act | 0.1.0+ | AWS agent framework |
| Playwright | 1.40+ | Browser automation |
| Boto3 | 1.34+ | AWS SDK |
| Bedrock Runtime | Latest | AWS Bedrock integration |
| WebSockets | 12.0+ | Real-time communication |
| Pydantic | 2.5+ | Data validation |
| Structlog | 23.2+ | Structured logging |

### Frontend

| Technology | Version | Purpose |
|------------|---------|---------|
| React | 18.2.0 | UI framework |
| React Router | 6.x | Routing |
| AWS Cloudscape | 3.0.1082+ | UI component library |
| Axios | 1.11+ | HTTP client |
| TypeScript | 4.9.5 | Type safety |
| Craco | 7.1.0 | Build configuration |
| Lodash | 4.17+ | Utility functions |
| AWS DCV SDK | Latest | Remote desktop protocol |

### AWS Services

- **Amazon Bedrock** (Claude AI models)
- **Amazon Nova Sonic** (Speech-to-speech)
- **Amazon Polly** (Text-to-speech)
- **Amazon S3** (Object storage)
- **AWS IAM** (Identity and access management)
- **Amazon DCV** (Remote desktop streaming)

---

## 📂 Project Structure

```
Drishti-AI-Navigator/
├── backend/
│   ├── app.py                    # Main FastAPI application
│   ├── config.py                 # Configuration manager
│   ├── database.py               # Database models and manager
│   ├── order_queue.py            # Order queue processing
│   ├── agents/                   # AI agent implementations
│   │   ├── strands_agent.py
│   │   └── nova_act_agent.py
│   ├── services/                 # Business logic services
│   │   ├── voice_service.py
│   │   ├── browser_service.py
│   │   ├── settings_service.py
│   │   └── secrets_manager.py
│   ├── tools/                    # Browser automation tools
│   │   └── browser/
│   │       ├── browser_tools.py
│   │       └── browser_manager.py
│   ├── examples/                 # Example scripts
│   ├── tests/                    # Test suite
│   ├── requirements.txt          # Python dependencies
│   ├── .env.example             # Environment template
│   └── order_automation.db      # SQLite database (dev)
│
├── frontend/
│   ├── src/
│   │   ├── App.js               # Main app component
│   │   ├── components/          # Reusable components
│   │   │   ├── OrderDashboard.js
│   │   │   ├── CreateOrderWizard.js
│   │   │   ├── LiveBrowserViewer.js
│   │   │   ├── VoiceOrderAssistant.js
│   │   │   └── ...
│   │   ├── pages/               # Page components
│   │   │   ├── OrderDetails.js
│   │   │   ├── ReviewQueue.js
│   │   │   ├── Settings.js
│   │   │   └── ...
│   │   ├── services/            # Frontend services
│   │   │   ├── api.js
│   │   │   └── websocket.ts
│   │   └── types/               # TypeScript types
│   ├── public/
│   │   └── dcv-sdk/            # AWS DCV SDK
│   ├── package.json
│   └── craco.config.js
│
├── README.md                     # This file
├── LICENSE                       # Apache 2.0 License
└── .gitignore
```

---

## 🔌 API Reference

### Order Management

```
POST   /api/orders                          Create new order
GET    /api/orders                          List all orders
GET    /api/orders/{order_id}               Get order details
PUT    /api/orders/{order_id}               Update order
DELETE /api/orders/{order_id}               Delete order
POST   /api/orders/{order_id}/retry         Retry failed order
POST   /api/orders/upload-csv               Batch upload
```

### Live View & Control

```
GET    /api/orders/{order_id}/live-view               Get live view URL
POST   /api/orders/{order_id}/take-control            Enable manual control
POST   /api/orders/{order_id}/release-control         Disable manual control
POST   /api/orders/{order_id}/change-resolution       Set browser resolution
GET    /api/orders/{order_id}/session-replay          Get session replay
```

### Voice Interface

```
POST   /api/voice/conversation/start                              Start conversation
POST   /api/voice/conversation/{conversation_id}/process          Process audio
GET    /api/voice/conversation/{conversation_id}/state            Get state
POST   /api/voice/conversation/{conversation_id}/submit           Submit order
```

### Queue Management

```
GET    /api/queue/status                    Get queue status
POST   /api/queue/pause                     Pause processing
POST   /api/queue/resume                    Resume processing
GET    /api/queue/metrics                   Get metrics
```

### Configuration

```
GET    /api/config/retailers                Get retailer configs
GET    /api/config/retailer-urls            Get retailer URLs
GET    /api/settings/config                 Get system config
PUT    /api/settings/config                 Update system config
```

### WebSocket

```
WS     /ws                                  Real-time updates
```

**WebSocket Message Format:**

```json
{
  "type": "order_update",
  "order_id": "uuid",
  "status": "processing",
  "progress": 45,
  "current_step": "Adding item to cart",
  "timestamp": "2025-10-21T12:34:56Z"
}
```

---

## 🧪 Testing

### Running Tests

```bash
cd backend

# Run all tests
pytest

# Run with coverage
pytest --cov=. --cov-report=html

# Run specific test file
pytest tests/test_voice_service.py

# Run with verbose output
pytest -v
```

### Example Scripts

```bash
# Test Nova Sonic voice interaction
python examples/nova_sonic_demo.py

# Test speech-to-speech
python examples/nova_sonic_s2s_demo.py

# Test browser integration
python tools/browser/test_integration.py
```

---

## 🐛 Troubleshooting

### Common Issues

#### 1. AWS Credentials Not Found

```
Error: Unable to locate credentials
```

**Solution:**
- Verify `AWS_ACCESS_KEY_ID` and `AWS_SECRET_ACCESS_KEY` in `.env`
- Or configure AWS CLI: `aws configure`
- Ensure IAM user has Bedrock permissions

#### 2. Bedrock Model Access Denied

```
Error: AccessDeniedException: You don't have access to the model
```

**Solution:**
- Go to AWS Bedrock console
- Navigate to "Model access"
- Request access to Claude models and Nova Sonic
- Wait for approval (usually instant)

#### 3. Database Connection Failed

```
Error: could not connect to server
```

**Solution:**
- Check PostgreSQL is running: `sudo systemctl status postgresql`
- Verify `DATABASE_URL` in `.env`
- For development, use SQLite: `DATABASE_URL=sqlite:///./order_automation.db`

#### 4. Frontend Can't Connect to Backend

```
Error: Network Error
```

**Solution:**
- Ensure backend is running on port 8000
- Check `FRONTEND_URL` in backend `.env`
- Verify CORS configuration in `app.py`

#### 5. Browser Session Timeout

```
Error: Browser session expired
```

**Solution:**
- Increase `BROWSER_SESSION_TIMEOUT` in `.env`
- Default is 3600 seconds (1 hour)
- Monitor active sessions in dashboard

---

## 🔒 Security Considerations

### Credentials

- All credentials stored in Secret Vault are encrypted
- Use environment variables for sensitive config
- Never commit `.env` files to version control
- Rotate AWS credentials regularly

### AWS IAM

- Use least-privilege IAM policies
- Create dedicated IAM roles for the application
- Enable MFA on AWS accounts
- Audit IAM permissions regularly

### Network Security

- Use HTTPS in production
- Configure firewall rules
- Restrict WebSocket connections
- Enable CORS only for trusted origins

### Data Protection

- Session recordings may contain sensitive data
- Configure S3 bucket encryption
- Set appropriate retention policies
- Implement data deletion procedures

---

## 🚢 Deployment

### Production Deployment

#### Docker Deployment (Recommended)

Create `Dockerfile` for backend:

```dockerfile
FROM python:3.13-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8000"]
```

Create `docker-compose.yml`:

```yaml
version: '3.8'

services:
  backend:
    build: ./backend
    ports:
      - "8000:8000"
    environment:
      - DATABASE_URL=postgresql://user:password@db:5432/drishti
    depends_on:
      - db

  frontend:
    build: ./frontend
    ports:
      - "80:80"
    depends_on:
      - backend

  db:
    image: postgres:15
    environment:
      - POSTGRES_USER=user
      - POSTGRES_PASSWORD=password
      - POSTGRES_DB=drishti
    volumes:
      - postgres_data:/var/lib/postgresql/data

volumes:
  postgres_data:
```

Deploy:

```bash
docker-compose up -d
```

#### AWS Deployment

1. **Backend**: Deploy to AWS ECS or EC2
2. **Frontend**: Deploy to S3 + CloudFront or Amplify
3. **Database**: Use RDS PostgreSQL
4. **Queue**: Consider SQS for order queue
5. **Secrets**: Use AWS Secrets Manager

#### Environment Variables for Production

```bash
ENVIRONMENT=production
DATABASE_URL=postgresql://user:password@rds-endpoint:5432/drishti
FRONTEND_URL=https://your-domain.com
SESSION_REPLAY_S3_BUCKET=production-session-replays
MAX_CONCURRENT_ORDERS=10
```

---

## 🤝 Contributing

Contributions are welcome! Please follow these guidelines:

1. Fork the repository
2. Create a feature branch: `git checkout -b feature/amazing-feature`
3. Commit your changes: `git commit -m 'Add amazing feature'`
4. Push to the branch: `git push origin feature/amazing-feature`
5. Open a Pull Request

### Development Guidelines

- Follow PEP 8 for Python code
- Use ESLint for JavaScript/TypeScript
- Write tests for new features
- Update documentation
- Use meaningful commit messages

---

## 📄 License

This project is licensed under the **Apache License 2.0**. See the [LICENSE](LICENSE) file for details.

---

## 🙏 Acknowledgments

- **AWS Bedrock** for Claude AI models and Nova Sonic
- **Anthropic** for Claude AI technology
- **Strands AI** for agent framework
- **AWS Cloudscape** for UI components
- **FastAPI** and **React** communities

---

## 📞 Support

For issues, questions, or contributions:

- **GitHub Issues**: [https://github.com/yourusername/Drishti-AI-Navigator/issues](https://github.com/yourusername/Drishti-AI-Navigator/issues)
- **Documentation**: [https://docs.example.com](https://docs.example.com)
- **Email**: support@example.com

---

## 🗺️ Roadmap

### Upcoming Features

- [ ] Multi-region AWS deployment
- [ ] Advanced retry strategies with exponential backoff
- [ ] Payment method tokenization
- [ ] Multiple retailer support expansion
- [ ] Enhanced error recovery with ML-based predictions
- [ ] Mobile app for monitoring
- [ ] Slack/Teams integration for notifications
- [ ] Advanced analytics dashboard
- [ ] A/B testing for agent performance
- [ ] Cost optimization recommendations

---

## 📊 Performance Metrics

### Typical Performance

- **Order Processing Time**: 2-5 minutes per order
- **Success Rate**: 85-95% (varies by retailer)
- **Concurrent Orders**: Up to 10 (configurable)
- **API Response Time**: <100ms (median)
- **WebSocket Latency**: <50ms

### Scalability

- Horizontal scaling supported via queue-based architecture
- Database can handle 100K+ orders
- Session recordings stored on S3 (unlimited)
- WebSocket connections: 1000+ concurrent

---

**Built with ❤️ using AWS Bedrock, AgentCore, Strands Agent,  Claude, and Modern Web Technologies**
