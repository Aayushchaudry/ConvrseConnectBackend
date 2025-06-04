# Converse Connect Backend

A comprehensive backend system for managing creative projects with SAGA orchestration patterns and centralized authentication.

## Overview

This backend system provides a complete solution for managing creative projects through their entire lifecycle, from initial requirements gathering to final delivery. It implements the SAGA pattern for distributed transaction management, event-driven architecture, and integrates with a centralized auth-service for unified user management and business context.

## Features

- **Project Management**: Complete project lifecycle management with status tracking
- **Requirements Gathering**: Handle client requirements with file uploads and validation
- **Production Management**: Internal task management and resource allocation
- **Review Management**: Client feedback collection and approval workflows
- **Delivery Service**: Final asset delivery and version control
- **SAGA Orchestration**: Distributed transaction management for complex workflows
- **Event-Driven Architecture**: Kafka-based event streaming for real-time updates
- **🔐 Auth Service Integration**: Centralized authentication and business context management
- **🏢 Multi-tenant Support**: Business-isolated data access and permissions
- **📊 Activity Logging**: Comprehensive audit trails for all user actions

## Architecture

The system follows a layered architecture with:

- **API Layer**: REST endpoints for client interactions
- **Service Layer**: Business logic and validation
- **Orchestrator Layer**: SAGA pattern implementation
- **Event Layer**: Event-driven communication
- **Data Layer**: ORM models and database interactions
- **🔐 Auth Layer**: JWT-based authentication and authorization middleware
- **🔄 Integration Layer**: External service communication (auth-service)

## Project Structure

```
/convrse_connect_backend/
├── src/
│   ├── main.py                     # Application entry point
│   ├── config/                     # Configuration files
│   │   └── auth_config.py          # 🔐 Auth service configuration
│   ├── models/                     # Database ORM models
│   │   └── activity_logs.py        # 📊 Audit logging model
│   ├── api/                        # REST API endpoints
│   │   └── integration/            # 🔄 Integration endpoints
│   ├── services/                   # Business logic handlers
│   │   └── activity_logger.py      # 📊 Activity logging service
│   ├── orchestrators/              # SAGA orchestrators
│   ├── listeners/                  # Event consumers
│   ├── events/                     # Event definitions
│   ├── commands/                   # Command definitions
│   ├── middleware/                 # 🔐 Auth middleware
│   ├── integrations/               # 🔄 External service clients
│   │   └── auth_service_client.py  # Auth service integration
│   └── utils/                      # Utility functions
├── migrations/                     # 🗄️ Database migrations
├── scripts/                        # 🧪 Testing and utility scripts
├── tests/                          # Test suite
├── requirements.txt                # Python dependencies
├── Dockerfile                      # Container configuration
└── README.md                       # This file
```

## Getting Started

### Prerequisites

- Python 3.11+
- PostgreSQL or MySQL
- Apache Kafka
- Redis (for auth token caching)
- 🔐 Auth Service (running on port 8001)

### Installation

1. Clone the repository:
```bash
git clone <repository-url>
cd convrse_connect_backend
```

2. Create a virtual environment:
```bash
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
```

3. Install dependencies:
```bash
pip install -r requirements.txt
```

4. Set up environment variables:
```bash
cp .env.example .env
# Edit .env with your configuration including:
# - AUTH_SERVICE_URL=http://localhost:8001
# - AUTH_SERVICE_TOKEN=your_service_token
# - JWT_SECRET_KEY=your_jwt_secret_key_32_chars_min
# - REDIS_URL=redis://localhost:6379/0
```

5. Run database migrations:
```bash
# Apply auth integration migration
psql -d your_database -f migrations/auth_integration_20241219.sql
```

6. Start the application:
```bash
python src/main.py
```

### 🧪 Testing Auth Integration

Test the auth integration setup:
```bash
python scripts/test_auth_integration.py
```

### Development Setup

1. Install development dependencies:
```bash
pip install -r requirements.txt
```

2. Run tests:
```bash
pytest
```

3. Format code:
```bash
black src/
```

4. Lint code:
```bash
flake8 src/
```

## API Endpoints

### 🔐 Authentication

All API endpoints (except health checks) require JWT authentication via the `Authorization: Bearer <token>` header.

### 🔄 Integration Endpoints

- `POST /api/v1/integration/auth/validate` - Validate current token
- `GET /api/v1/integration/user/profile` - Get user profile
- `GET /api/v1/integration/user/businesses` - Get user businesses
- `GET /api/v1/integration/health` - Auth integration health check

### Projects (🔐 Authenticated)
- `GET /api/v1/projects` - List projects (filtered by business context)
- `POST /api/v1/projects` - Create new project (with business context)
- `GET /api/v1/projects/{id}` - Get project by ID (business access validation)
- `PUT /api/v1/projects/{id}` - Update project (permission validation)
- `DELETE /api/v1/projects/{id}` - Delete project (permission validation)

### Deliverables (🔐 Authenticated)
- `GET /api/v1/deliverables` - List deliverables (business filtered)
- `GET /api/v1/deliverables/{id}` - Get deliverable by ID
- `PUT /api/v1/deliverables/{id}/status` - Update deliverable status

### Requirements (🔐 Authenticated)
- `GET /api/v1/requirements` - List requirements
- `POST /api/v1/requirements` - Create requirement
- `PUT /api/v1/requirements/{id}` - Update requirement
- `POST /api/v1/requirements/{id}/files` - Upload files

### Review Items (🔐 Authenticated)
- `GET /api/v1/review-items` - List review items
- `GET /api/v1/review-items/{id}` - Get review item by ID
- `POST /api/v1/review-items/{id}/feedback` - Submit feedback

### Internal Tasks (🔐 Authenticated)
- `GET /api/v1/internal-tasks` - List tasks
- `GET /api/v1/internal-tasks/{id}` - Get task by ID
- `PUT /api/v1/internal-tasks/{id}` - Update task
- `PUT /api/v1/internal-tasks/{id}/status` - Update task status

### Health Checks
- `GET /api/v1/health` - Application health (includes auth service status)

## 🔐 Authentication & Authorization

### User Context
All authenticated requests include user context:
- **User ID**: Unique identifier from auth-service
- **Business ID**: Current business context
- **Role**: User role (super_admin, client, etc.)
- **Permissions**: List of granted permissions

### Business Isolation
- Projects and deliverables are filtered by business context
- Users can only access resources within their assigned businesses
- Super admins can access across all businesses

### Audit Logging
All user actions are logged for audit trails:
- **Local Logging**: Activity logs table in ConvrseConnectBackend
- **Centralized Logging**: Forwarded to auth-service for unified audit
- **Context**: Includes user ID, business ID, correlation ID, and action details

## SAGA Orchestration

The system implements SAGA patterns for:

1. **Project Lifecycle**: Managing the overall project flow (with user context)
2. **Deliverable Management**: Handling individual deliverable workflows (with business context)

### Project Lifecycle States
- INITIATED
- INFO_GATHERING
- PLANNING
- IN_PRODUCTION
- IN_REVIEW
- AWAITING_CLIENT_FEEDBACK
- DELIVERY_PREPARATION
- DELIVERED
- COMPLETED
- FAILED
- CANCELLED

### Deliverable States
- CREATED
- TASKS_ASSIGNED
- IN_PROGRESS
- READY_FOR_REVIEW
- IN_REVIEW
- REQUIRES_CHANGES
- APPROVED
- DELIVERED
- COMPLETED
- FAILED
- CANCELLED

## Event Architecture

The system uses Kafka for event streaming with user and business context:

- **Project Events**: Project lifecycle changes (with business_id, user_id)
- **Deliverable Events**: Deliverable status updates (with user context)
- **Task Events**: Internal task management (with user assignments)
- **Client Feedback Events**: Client interaction tracking (with business context)

## 🏢 Multi-Tenant Architecture

### Business Context
- All projects belong to a specific business
- Users are associated with one or more businesses
- Data is isolated by business boundaries

### Permission System
- Role-based access control via auth-service
- Business-specific permissions
- Resource-level authorization

## Testing

Run the test suite:

```bash
# Unit tests
pytest tests/unit/

# Integration tests
pytest tests/integration/

# End-to-end tests
pytest tests/e2e/

# Auth integration tests
python scripts/test_auth_integration.py

# All tests
pytest
```

## Deployment

### Docker

Build and run with Docker:

```bash
docker build -t converse-connect-backend .
docker run -p 8000:8000 converse-connect-backend
```

### Production Considerations

- Set up proper environment variables (especially auth configuration)
- Configure database connection pooling
- Set up Kafka cluster
- Configure Redis for auth token caching
- 🔐 Deploy auth-service and configure service-to-service authentication
- Set up monitoring and logging
- Configure load balancing

### Environment Variables

Required for auth integration:
```bash
AUTH_SERVICE_URL=http://auth-service:8001
AUTH_SERVICE_TOKEN=your_secure_service_token
JWT_SECRET_KEY=your_jwt_secret_key_minimum_32_characters
REDIS_URL=redis://redis:6379/0
```

## 🔧 Configuration

### Auth Service Integration
The system integrates with a centralized auth-service for:
- JWT token validation
- User and business management
- Permission checking
- Activity logging

### Caching Strategy
- Redis caching for auth tokens (5-minute TTL)
- User permissions caching (1-minute TTL)
- Circuit breaker pattern for auth-service resilience

### Security Features
- JWT-based authentication
- Business-level data isolation
- Comprehensive audit logging
- Rate limiting (configurable per business)
- CORS protection
- Input validation

## Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes (following auth integration patterns)
4. Add tests (including auth integration tests)
5. Run the test suite
6. Submit a pull request

## License

[Add your license information here]

## Support

[Add support contact information here] 