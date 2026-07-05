COMPOSE = sudo docker compose --env-file .env \
	-f docker/compose_db.yml \
	-f docker/compose_web.yml \
	-f docker/compose_tracking.yml

.PHONY: up down restart logs ps build

up:
	$(COMPOSE) up --build -d --remove-orphans

down:
	$(COMPOSE) down

restart:
	$(COMPOSE) restart web worker

build:
	$(COMPOSE) build

logs:
	$(COMPOSE) logs -f web worker

ps:
	$(COMPOSE) ps