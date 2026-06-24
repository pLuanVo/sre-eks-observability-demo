.PHONY: setup build deploy port-forward load-test destroy lint

setup:
	./scripts/setup.sh

build:
	./scripts/build-push.sh

deploy:
	kubectl apply -k k8s/overlays/production/

port-forward:
	./scripts/port-forward.sh

load-test:
	./scripts/load-test.sh

destroy:
	./scripts/destroy.sh

lint:
	ruff check apps/ mcp-server/
	yamllint -d relaxed k8s/ observability/ sre/
