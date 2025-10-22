# AWS Architecture Diagrams - Drishti AI Navigator

## Table of Contents
1. [High-Level System Architecture](#1-high-level-system-architecture)
2. [AWS Services Integration](#2-aws-services-integration)
3. [Order Processing Flow](#3-order-processing-flow)
4. [Voice Conversation Flow](#4-voice-conversation-flow)
5. [Browser Automation Architecture](#5-browser-automation-architecture)
6. [Data Flow & Storage](#6-data-flow--storage)
7. [Security & IAM](#7-security--iam)

---

## 1. High-Level System Architecture

```mermaid
graph TB
    subgraph "Client Layer"
        WEB[Web Frontend<br/>React App]
        VOICE[Voice Interface<br/>Microphone Input]
    end

    subgraph "API Layer"
        API[FastAPI Backend<br/>Port 8000]
        WS[WebSocket Server<br/>Real-time Updates]
    end

    subgraph "Application Services"
        ORDER[Order Queue<br/>Service]
        BROWSER[Browser Service<br/>AgentCore Management]
        VOICESVC[Voice Service<br/>Nova Sonic/Polly]
        SETTINGS[Settings Service<br/>Configuration]
        SECRETS[Secrets Service<br/>AWS Secrets Manager]
    end

    subgraph "Automation Agents"
        NOVA[Nova Act Agent<br/>AI-Powered Browser]
        STRANDS[Strands Agent<br/>MCP + Browser Tools]
    end

    subgraph "AWS Services"
        BEDROCK[Amazon Bedrock<br/>- Nova Act<br/>- Nova Sonic<br/>- Claude Models]
        AGENTCORE[AgentCore Browser<br/>Managed Browser Sessions]
        S3[Amazon S3<br/>Session Recordings<br/>Screenshots]
        SM[AWS Secrets Manager<br/>Credentials Storage]
        IAM[AWS IAM<br/>Execution Roles]
    end

    subgraph "Data Layer"
        DB[(SQLite Database<br/>Orders & Configs)]
    end

    WEB --> API
    VOICE --> API
    API --> WS
    API --> ORDER
    API --> BROWSER
    API --> VOICESVC
    API --> SETTINGS
    API --> SECRETS

    ORDER --> NOVA
    ORDER --> STRANDS
    SETTINGS --> DB
    ORDER --> DB

    NOVA --> BEDROCK
    NOVA --> AGENTCORE
    STRANDS --> BEDROCK
    STRANDS --> AGENTCORE
    BROWSER --> AGENTCORE
    VOICESVC --> BEDROCK
    SECRETS --> SM

    AGENTCORE --> S3
    NOVA --> S3
    STRANDS --> S3
    
    AGENTCORE --> IAM
    BEDROCK --> IAM

    style BEDROCK fill:#FF9900
    style AGENTCORE fill:#FF9900
    style S3 fill:#569A31
    style SM fill:#DD344C
    style IAM fill:#DD344C
```

---

## 2. AWS Services Integration

```mermaid
graph LR
    subgraph "Amazon Bedrock Services"
        NOVASONIC[Amazon Nova Sonic<br/>Speech-to-Speech AI<br/>Model: nova-sonic-v1:0]
        NOVAACT[Amazon Nova Act<br/>Browser Automation AI<br/>Multimodal Agent]
        CLAUDE[Claude Models<br/>- Claude 3.5 Sonnet v2<br/>- Claude 3 Haiku<br/>Strands Agent LLM]
    end

    subgraph "AgentCore Browser"
        BROWSER[Browser Client<br/>Managed Chrome Sessions]
        CONTROL[Control Plane API<br/>Session Management]
        RECORDING[Session Recording<br/>Browser Activity Capture]
        LIVEVIEW[Live View URLs<br/>Real-time Monitoring]
    end

    subgraph "Storage & Security"
        S3BUCKET[S3 Bucket<br/>drishti-ai]
        S3REPLAY[Session Replays<br/>s3://bucket/session-replays/]
        S3SCREEN[Screenshots<br/>s3://bucket/screenshots/]
        SECRETS[Secrets Manager<br/>Site Credentials<br/>Payment Tokens]
        IAMROLE[IAM Role<br/>AgentCoreExecutionRole<br/>Permissions]
    end

    subgraph "Application"
        APP[FastAPI Backend]
    end

    APP -->|Converse Stream| NOVASONIC
    APP -->|Act Invocation| NOVAACT
    APP -->|Strands Tools| CLAUDE
    APP -->|Create Session| CONTROL
    APP -->|Store/Retrieve| SECRETS
    APP -->|Assume Role| IAMROLE

    CONTROL -->|Manage| BROWSER
    BROWSER -->|Record to| S3REPLAY
    BROWSER -->|Save to| S3SCREEN
    BROWSER -->|Generate| LIVEVIEW
    CONTROL -->|Configure| RECORDING

    NOVAACT -->|Control| BROWSER
    CLAUDE -->|Via MCP| BROWSER

    IAMROLE -->|Access| S3BUCKET
    IAMROLE -->|Access| SECRETS

    style NOVASONIC fill:#FF9900
    style NOVAACT fill:#FF9900
    style CLAUDE fill:#FF9900
    style BROWSER fill:#FF9900
    style S3BUCKET fill:#569A31
    style SECRETS fill:#DD344C
    style IAMROLE fill:#DD344C
```

---

## 3. Order Processing Flow

```mermaid
sequenceDiagram
    participant User
    participant API
    participant OrderQueue
    participant Agent
    participant Bedrock
    participant AgentCore
    participant S3
    participant DB

    User->>API: POST /api/orders<br/>(Create Order)
    API->>DB: Store Order<br/>Status: PENDING
    API->>OrderQueue: Add to Queue
    API->>User: Order ID + Status
    
    OrderQueue->>DB: Get Next Order<br/>Priority-based
    OrderQueue->>Agent: Assign Order<br/>(Nova Act or Strands)
    
    Agent->>AgentCore: Create Browser Session<br/>with Recording Config
    AgentCore->>S3: Setup Recording<br/>Bucket: drishti-ai
    AgentCore-->>Agent: Browser Client + Session ID
    
    Agent->>DB: Update Status<br/>PROCESSING
    
    loop Automation Steps
        Agent->>Bedrock: AI Request<br/>(Nova Act or Claude)
        Bedrock-->>Agent: Action/Response
        Agent->>AgentCore: Execute Browser Action
        AgentCore->>S3: Save Screenshot
        AgentCore-->>Agent: Action Result
        Agent->>DB: Log Execution Step
    end
    
    alt Success
        Agent->>DB: Update Status<br/>COMPLETED
        Agent->>AgentCore: Close Session
        AgentCore->>S3: Finalize Recording
    else Failure
        Agent->>DB: Update Status<br/>FAILED + Error Details
        Agent->>AgentCore: Close Session
    else Requires Human
        Agent->>DB: Update Status<br/>REQUIRES_HUMAN
        Agent->>AgentCore: Keep Session<br/>Generate Live View URL
    end
    
    Agent->>OrderQueue: Notify Completion
    OrderQueue->>API: Broadcast Update<br/>via WebSocket
    API->>User: Order Status Update
```

---

## 4. Voice Conversation Flow

```mermaid
sequenceDiagram
    participant User
    participant API
    participant VoiceService
    participant NovaSonic
    participant OrderQueue
    participant Agent
    participant DB

    User->>API: POST /api/voice/conversation/start
    API->>VoiceService: Start Conversation<br/>Generate Conversation ID
    VoiceService->>NovaSonic: Converse Stream Request<br/>System Prompt: Order Assistant
    NovaSonic-->>VoiceService: Welcome Audio (PCM 24kHz)
    VoiceService-->>API: Conversation ID + Audio
    API-->>User: Play Welcome Message
    
    loop Order Information Gathering
        User->>API: POST /api/voice/conversation/process<br/>Audio Input (WAV/PCM)
        API->>VoiceService: Process Speech
        VoiceService->>NovaSonic: Bidirectional Stream<br/>Audio Input
        
        NovaSonic->>NovaSonic: Speech-to-Text<br/>Intent Recognition
        NovaSonic->>NovaSonic: Generate Response<br/>Text-to-Speech
        
        NovaSonic-->>VoiceService: Response Audio + Transcript
        VoiceService->>VoiceService: Extract Order Data<br/>Parse Fields
        VoiceService->>DB: Update Conversation State
        VoiceService-->>API: Audio + Order Data<br/>Ready Status
        API-->>User: Play Response<br/>Show Order Preview
    end
    
    User->>API: GET /api/voice/conversation/summary
    API->>VoiceService: Get Order Summary
    VoiceService->>NovaSonic: Generate Confirmation<br/>Read Order Details
    NovaSonic-->>VoiceService: Confirmation Audio
    VoiceService-->>API: Summary + Audio
    API-->>User: Confirm Order Details
    
    User->>API: POST /api/voice/conversation/submit<br/>automation_method=strands
    API->>VoiceService: Get Order Data
    VoiceService-->>API: Complete Order Object
    API->>OrderQueue: Add Order to Queue
    OrderQueue->>Agent: Process Order
    API->>DB: Store Order<br/>Source: VOICE
    API-->>User: Order Submitted<br/>Tracking ID
    
    User->>API: DELETE /api/voice/conversation/{id}
    API->>VoiceService: Cleanup Conversation
    VoiceService->>DB: Remove State
    VoiceService-->>API: Success
```

---

## 5. Browser Automation Architecture

```mermaid
graph TB
    subgraph "Automation Agents"
        NOVA[Nova Act Agent]
        STRANDS[Strands Agent]
    end

    subgraph "AgentCore Browser Infrastructure"
        CLIENT[Browser Client<br/>Python SDK]
        CONTROL[Control Plane API<br/>Session Management]
        
        subgraph "Browser Session"
            CHROME[Chrome Browser<br/>Headless/Headful]
            PLAYWRIGHT[Playwright Integration<br/>Page Control]
            WS[WebSocket<br/>Chrome DevTools Protocol]
        end
        
        subgraph "Capabilities"
            RECORDING[Session Recording<br/>Video + Actions]
            SCREENSHOTS[Screenshot Capture<br/>Step-by-step]
            LIVEVIEW[Live View URL<br/>DCV Protocol]
            RESOLUTION[Resolution Control<br/>Dynamic Resize]
        end
    end

    subgraph "Browser Tools (MCP)"
        NAVIGATE[Navigate Tool<br/>URL Navigation]
        CLICK[Click Tool<br/>Element Interaction]
        TYPE[Type Tool<br/>Form Input]
        SCREENSHOT_TOOL[Screenshot Tool<br/>Visual Capture]
        EXTRACT[Extract Tool<br/>Data Scraping]
        EVALUATE[Evaluate Tool<br/>JavaScript Execution]
    end

    subgraph "Storage"
        S3[Amazon S3]
        LOCAL[Local Screenshots<br/>static/screenshots/]
    end

    subgraph "Bedrock AI Models"
        NOVAACT_MODEL[Nova Act<br/>Multimodal Vision + Action]
        CLAUDE_MODEL[Claude 3.5 Sonnet<br/>Reasoning + Planning]
    end

    NOVA --> CLIENT
    STRANDS --> CLIENT
    STRANDS --> NAVIGATE
    STRANDS --> CLICK
    STRANDS --> TYPE
    STRANDS --> SCREENSHOT_TOOL
    STRANDS --> EXTRACT
    STRANDS --> EVALUATE

    NOVA --> NOVAACT_MODEL
    STRANDS --> CLAUDE_MODEL

    CLIENT --> CONTROL
    CONTROL --> CHROME
    CHROME --> PLAYWRIGHT
    PLAYWRIGHT --> WS

    CHROME --> RECORDING
    CHROME --> SCREENSHOTS
    CHROME --> LIVEVIEW
    CHROME --> RESOLUTION

    RECORDING --> S3
    SCREENSHOTS --> S3
    SCREENSHOTS --> LOCAL

    NAVIGATE --> PLAYWRIGHT
    CLICK --> PLAYWRIGHT
    TYPE --> PLAYWRIGHT
    SCREENSHOT_TOOL --> PLAYWRIGHT
    EXTRACT --> PLAYWRIGHT
    EVALUATE --> PLAYWRIGHT

    style NOVAACT_MODEL fill:#FF9900
    style CLAUDE_MODEL fill:#FF9900
    style CLIENT fill:#FF9900
    style CHROME fill:#4285F4
    style S3 fill:#569A31
```

---

## 6. Data Flow & Storage

```mermaid
graph TB
    subgraph "Application Data"
        DB[(SQLite Database)]
        
        subgraph "Database Tables"
            ORDERS[Orders Table<br/>- order_id<br/>- status<br/>- retailer<br/>- automation_method<br/>- customer_info<br/>- timestamps]
            
            LOGS[Execution Logs<br/>- log_id<br/>- order_id<br/>- level<br/>- message<br/>- step<br/>- timestamp]
            
            CONFIG[System Config<br/>- config_key<br/>- config_value<br/>- updated_at]
            
            RETAILERS[Retailer URLs<br/>- url_id<br/>- retailer<br/>- website_name<br/>- starting_url<br/>- is_default]
            
            SESSIONS[Browser Sessions<br/>- session_id<br/>- order_id<br/>- browser_id<br/>- recording_config<br/>- status]
        end
    end

    subgraph "AWS Storage"
        S3BUCKET[S3 Bucket: drishti-ai]
        
        subgraph "S3 Structure"
            REPLAYS[session-replays/<br/>order_id/<br/>- metadata.json<br/>- recording.webm<br/>- actions.log]
            
            SCREENS[screenshots/<br/>order_id/<br/>- step_001.png<br/>- step_002.png<br/>- final.png]
            
            ARCHIVES[archives/<br/>date/<br/>completed-orders/]
        end
    end

    subgraph "AWS Secrets Manager"
        SECRETSTORE[Secrets Store]
        
        subgraph "Secret Types"
            SITECREDS[Site Credentials<br/>drishti/site/site_name<br/>- username<br/>- password<br/>- site_url]
            
            PAYMENT[Payment Tokens<br/>drishti/payment/token_id<br/>- card_token<br/>- cardholder<br/>- expiry]
            
            APIKEYS[API Keys<br/>drishti/config/key_name<br/>- nova_act_api_key<br/>- bedrock_keys]
        end
    end

    subgraph "Local Storage"
        LOCALSCREEN[static/screenshots/<br/>Temporary Files]
        LOGS_LOCAL[Logs Directory<br/>Application Logs]
    end

    ORDERS --> DB
    LOGS --> DB
    CONFIG --> DB
    RETAILERS --> DB
    SESSIONS --> DB

    REPLAYS --> S3BUCKET
    SCREENS --> S3BUCKET
    ARCHIVES --> S3BUCKET

    SITECREDS --> SECRETSTORE
    PAYMENT --> SECRETSTORE
    APIKEYS --> SECRETSTORE

    DB -.->|Backup| S3BUCKET
    LOCALSCREEN -.->|Upload| SCREENS
    SESSIONS -.->|Record to| REPLAYS

    style DB fill:#4DB33D
    style S3BUCKET fill:#569A31
    style SECRETSTORE fill:#DD344C
```

---

## 7. Security & IAM

```mermaid
graph TB
    subgraph "IAM Roles & Policies"
        EXEC_ROLE[AgentCoreExecutionRole<br/>IAM Role]
        
        subgraph "Attached Policies"
            BEDROCK_POLICY[Bedrock Access Policy<br/>- bedrock:InvokeModel<br/>- bedrock:InvokeModelStream<br/>- bedrock-runtime:*]
            
            AGENTCORE_POLICY[AgentCore Policy<br/>- agentcore:CreateBrowser<br/>- agentcore:GetBrowser<br/>- agentcore:UpdateBrowser<br/>- agentcore:DeleteBrowser<br/>- agentcore:CreateSession]
            
            S3_POLICY[S3 Access Policy<br/>- s3:PutObject<br/>- s3:GetObject<br/>- s3:ListBucket<br/>Bucket: drishti-ai]
            
            SECRETS_POLICY[Secrets Manager Policy<br/>- secretsmanager:GetSecretValue<br/>- secretsmanager:CreateSecret<br/>- secretsmanager:UpdateSecret<br/>- secretsmanager:DeleteSecret<br/>Resource: drishti/*]
        end
    end

    subgraph "Application Authentication"
        APP[FastAPI Application]
        ENV[Environment Variables<br/>AWS_ACCESS_KEY_ID<br/>AWS_SECRET_ACCESS_KEY<br/>AWS_REGION]
        BOTO3[Boto3 Clients<br/>SigV4 Authentication]
    end

    subgraph "AWS Services"
        BEDROCK[Amazon Bedrock]
        AGENTCORE[AgentCore Browser]
        S3[Amazon S3]
        SECRETSMGR[Secrets Manager]
    end

    subgraph "Data Encryption"
        TRANSIT[In-Transit<br/>TLS 1.2+<br/>HTTPS/WSS]
        REST[At-Rest<br/>S3: AES-256<br/>Secrets: KMS]
        WSENCRYPT[WebSocket<br/>Secure WebSocket<br/>WSS Protocol]
    end

    EXEC_ROLE --> BEDROCK_POLICY
    EXEC_ROLE --> AGENTCORE_POLICY
    EXEC_ROLE --> S3_POLICY
    EXEC_ROLE --> SECRETS_POLICY

    APP --> ENV
    ENV --> BOTO3
    BOTO3 --> EXEC_ROLE

    BEDROCK_POLICY -.->|Authorize| BEDROCK
    AGENTCORE_POLICY -.->|Authorize| AGENTCORE
    S3_POLICY -.->|Authorize| S3
    SECRETS_POLICY -.->|Authorize| SECRETSMGR

    BOTO3 --> BEDROCK
    BOTO3 --> AGENTCORE
    BOTO3 --> S3
    BOTO3 --> SECRETSMGR

    TRANSIT --> APP
    REST --> S3
    REST --> SECRETSMGR
    WSENCRYPT --> APP

    style EXEC_ROLE fill:#DD344C
    style BEDROCK_POLICY fill:#FF9900
    style AGENTCORE_POLICY fill:#FF9900
    style S3_POLICY fill:#569A31
    style SECRETS_POLICY fill:#DD344C
    style TRANSIT fill:#146EB4
    style REST fill:#146EB4
```

---

## Architecture Components Summary

### Core AWS Services Used

| Service | Purpose | Configuration |
|---------|---------|---------------|
| **Amazon Bedrock** | AI Models (Nova Act, Nova Sonic, Claude) | Region: us-west-2 |
| **AgentCore Browser** | Managed browser automation | Control Plane + Browser Client |
| **Amazon S3** | Session recordings, screenshots | Bucket: drishti-ai |
| **AWS Secrets Manager** | Credentials storage | Prefix: drishti/* |
| **AWS IAM** | Access control & permissions | Role: AgentCoreExecutionRole |

### Automation Methods

1. **Nova Act Agent**
   - Uses Amazon Nova Act multimodal AI
   - Direct browser control via AgentCore
   - Visual understanding + action planning
   - Best for complex, adaptive scenarios

2. **Strands Agent**
   - Uses Claude 3.5 Sonnet for reasoning
   - Browser Tools via MCP (Model Context Protocol)
   - Structured tool-based interactions
   - Best for deterministic workflows

### Key Features

- **Voice Ordering**: Nova Sonic speech-to-speech conversations
- **Live View**: Real-time browser session monitoring
- **Session Replay**: S3-stored browser recordings
- **Manual Control**: Human intervention capability
- **Priority Queue**: Intelligent order processing
- **Real-time Updates**: WebSocket-based notifications
- **Credential Management**: Secure storage in Secrets Manager

### Network Architecture

```
User → [HTTPS] → FastAPI (Port 8000)
       ↓
       WebSocket (Port 8000)
       ↓
[TLS] → AWS Services
       - Bedrock Runtime
       - AgentCore Control Plane
       - S3
       - Secrets Manager
```

### Data Retention

- **Database**: Local SQLite (persistent)
- **Screenshots**: S3 (30-day lifecycle)
- **Session Replays**: S3 (configurable retention)
- **Secrets**: Secrets Manager (30-day recovery window)

---

## Deployment Considerations

### Prerequisites
1. AWS Account with Bedrock access
2. IAM role with necessary permissions
3. S3 bucket for recordings
4. Python 3.11+ environment

### Environment Variables
```bash
AWS_REGION=us-west-2
AWS_ACCESS_KEY_ID=<your-key>
AWS_SECRET_ACCESS_KEY=<your-secret>
AGENTCORE_REGION=us-west-2
SESSION_REPLAY_S3_BUCKET=drishti-ai
```

### Scaling Recommendations
- **Horizontal**: Multiple FastAPI instances behind load balancer
- **Vertical**: Increase worker threads for order queue
- **Browser Sessions**: Monitor AgentCore browser limits
- **S3 Storage**: Implement lifecycle policies for cost optimization

---

*Generated: October 2025*
*Application: Drishti AI Navigator - AWS AI Agent Global Hackathon*
