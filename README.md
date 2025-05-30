# Converse Connect Backend

A comprehensive backend system for managing creative projects with SAGA orchestration patterns.

## Overview

This backend system provides a complete solution for managing creative projects through their entire lifecycle, from initial requirements gathering to final delivery. It implements the SAGA pattern for distributed transaction management and event-driven architecture.

## Features

- **Project Management**: Complete project lifecycle management with status tracking
- **Requirements Gathering**: Handle client requirements with file uploads and validation
- **Production Management**: Internal task management and resource allocation
- **Review Management**: Client feedback collection and approval workflows
- **Delivery Service**: Final asset delivery and version control
- **SAGA Orchestration**: Distributed transaction management for complex workflows
- **Event-Driven Architecture**: Kafka-based event streaming for real-time updates

## Architecture

The system follows a layered architecture with:

- **API Layer**: REST endpoints for client interactions
- **Service Layer**: Business logic and validation
- **Orchestrator Layer**: SAGA pattern implementation
- **Event Layer**: Event-driven communication
- **Data Layer**: ORM models and database interactions

## Project Structure

```
/convrse_connect_backend/
├── src/
│   ├── main.py                     # Application entry point
│   ├── config/                     # Configuration files
│   ├── models/                     # Database ORM models
│   ├── api/                        # REST API endpoints
│   ├── services/                   # Business logic handlers
│   ├── orchestrators/              # SAGA orchestrators
│   ├── listeners/                  # Event consumers
│   ├── events/                     # Event definitions
│   ├── commands/                   # Command definitions
│   └── utils/                      # Utility functions
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
- Redis (for Celery)

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
# Edit .env with your configuration
```

5. Run database migrations:
```bash
# TODO: Add migration commands based on chosen framework
```

6. Start the application:
```bash
python src/main.py
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

### Authentication
- `POST /auth/login` - User login
- `POST /auth/register` - User registration
- `POST /auth/logout` - User logout
- `POST /auth/refresh` - Token refresh

### Projects
- `GET /projects` - List all projects
- `POST /projects` - Create new project
- `GET /projects/{id}` - Get project by ID
- `PUT /projects/{id}` - Update project
- `DELETE /projects/{id}` - Delete project

### Deliverables
- `GET /deliverables` - List deliverables
- `GET /deliverables/{id}` - Get deliverable by ID
- `PUT /deliverables/{id}/status` - Update deliverable status

### Requirements
- `GET /requirements` - List requirements
- `POST /requirements` - Create requirement
- `PUT /requirements/{id}` - Update requirement
- `POST /requirements/{id}/files` - Upload files

### Review Items
- `GET /review-items` - List review items
- `GET /review-items/{id}` - Get review item by ID
- `POST /review-items/{id}/feedback` - Submit feedback

### Internal Tasks
- `GET /internal-tasks` - List tasks
- `GET /internal-tasks/{id}` - Get task by ID
- `PUT /internal-tasks/{id}` - Update task
- `PUT /internal-tasks/{id}/status` - Update task status

## SAGA Orchestration

The system implements SAGA patterns for:

1. **Project Lifecycle**: Managing the overall project flow
2. **Deliverable Management**: Handling individual deliverable workflows

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

The system uses Kafka for event streaming with the following event types:

- **Project Events**: Project lifecycle changes
- **Deliverable Events**: Deliverable status updates
- **Task Events**: Internal task management
- **Client Feedback Events**: Client interaction tracking

## Testing

Run the test suite:

```bash
# Unit tests
pytest tests/unit/

# Integration tests
pytest tests/integration/

# End-to-end tests
pytest tests/e2e/

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

- Set up proper environment variables
- Configure database connection pooling
- Set up Kafka cluster
- Configure Redis for caching
- Set up monitoring and logging
- Configure load balancing

## Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Add tests
5. Run the test suite
6. Submit a pull request

## License

[Add your license information here]

## Support

[Add support contact information here] 