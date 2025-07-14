# Define service names based on your docker-compose.yml setup
FRONTEND_SERVICE=frontend
BACKEND_SERVICE=backend
DB_SERVICE=postgres
DOCKER_COMPOSE_FILE=docker-compose.yml

# Build all services (frontend, backend, and database)
build:
	docker-compose -f $(DOCKER_COMPOSE_FILE) build

# Restart all services
restart:
	docker-compose -f $(DOCKER_COMPOSE_FILE) down && docker-compose -f $(DOCKER_COMPOSE_FILE) up -d

# Restart individual services
restart-backend:
	docker-compose -f $(DOCKER_COMPOSE_FILE) restart $(BACKEND_SERVICE)

restart-frontend:
	docker-compose -f $(DOCKER_COMPOSE_FILE) restart $(FRONTEND_SERVICE)

restart-db:
	docker-compose -f $(DOCKER_COMPOSE_FILE) restart $(DB_SERVICE)

# Stop all containers
stop:
	docker-compose -f $(DOCKER_COMPOSE_FILE) down

# Start all containers in detached mode
start:
	docker-compose -f $(DOCKER_COMPOSE_FILE) up -d

# Remove all stopped containers, dangling images, and unused volumes
clean:
	docker system prune -a --volumes -f

# Rebuild and restart the backend (useful for code updates)
rebuild-backend:
	docker-compose -f $(DOCKER_COMPOSE_FILE) build $(BACKEND_SERVICE) && make restart-backend

# Rebuild and restart the frontend (useful for frontend changes)
rebuild-frontend:
	docker-compose -f $(DOCKER_COMPOSE_FILE) build $(FRONTEND_SERVICE) && make restart-frontend

# Rebuild and restart the database (useful for DB schema changes)
rebuild-db:
	docker-compose -f $(DOCKER_COMPOSE_FILE) build $(DB_SERVICE) && make restart-db

# Show container status
status:
	docker-compose -f $(DOCKER_COMPOSE_FILE) ps

# List all running containers
ps:
	docker ps --format "table {{.ID}}\t{{.Names}}\t{{.Status}}\t{{.Ports}}"


.PHONY: build restart restart-backend restart-frontend restart-db stop start clean rebuild-backend rebuild-frontend rebuild-db status logs logs-backend logs-frontend logs-db ps disk-usage clean-images clean-containers clean-volumes clean-networks
