SHELL := /bin/bash
.SHELLFLAGS := -euo pipefail -c
.ONESHELL:
.DEFAULT_GOAL := help

# Scope test resources to this checkout and user; each Make invocation is unique.
PROJECT_SCOPE := $(shell python3 -c 'import hashlib, os; root=os.path.realpath("."); user="".join(c if c.isalnum() else "-" for c in os.environ.get("USER", "local").lower())[:8] or "local"; print("osa-" + hashlib.sha256(root.encode()).hexdigest()[:8] + "-" + user)')
RUN_ID := $(shell python3 -c 'import uuid; print(uuid.uuid4().hex[:8])')

COMPOSE := docker compose -f docker-compose.yaml
E2E_FILES := -f docker-compose.yaml -f docker-compose.integration-test.yaml

.PHONY: help build integration e2e clean

help:
	@printf '%s\n' \
	  'make build       Validate base Compose and build the app image' \
	  'make integration Run IT-01 through IT-08 in isolated Compose projects' \
	  'make e2e         Run the Chromium journey against the built Compose app' \
	  'make clean       Remove only verified test resources from this checkout'

build:
	$(COMPOSE) config --quiet
	$(COMPOSE) build app

integration:
	scope="$(PROJECT_SCOPE)"
	run_id="$(RUN_ID)"
	project_prefix="$$scope-integration-$$run_id"
	work_root="/tmp/$$project_prefix-work"
	token="$$(python3 -c 'import secrets; print(secrets.token_hex(16))')"
	umask 077
	mkdir -m 700 -- "$$work_root"
	printf '{"scope":"%s","run_id":"%s","kind":"integration","token":"%s"}\n' "$$scope" "$$run_id" "$$token" > "$$work_root/.osa-compose-owner"
	cleanup() {
	  status=$$?
	  trap - EXIT
	  OSA_PROJECT_SCOPE="$$scope" python3 scripts/compose_cleanup.py --temp-root "$$work_root" --token "$$token" --kind integration || status=1
	  exit "$$status"
	}
	trap cleanup EXIT
	OSA_COMPOSE_TEST_PREFIX="$$project_prefix" OSA_COMPOSE_TEST_RUN_ID="$$run_id" OSA_COMPOSE_TEST_TEMP_ROOT="$$work_root" python3 scripts/compose_integration.py

e2e:
	scope="$(PROJECT_SCOPE)"
	run_id="$(RUN_ID)"
	project="$$scope-e2e-$$run_id"
	work_root="/tmp/$$project-work"
	token="$$(python3 -c 'import secrets; print(secrets.token_hex(16))')"
	umask 077
	mkdir -m 700 -- "$$work_root"
	printf '{"scope":"%s","run_id":"%s","kind":"e2e","token":"%s"}\n' "$$scope" "$$run_id" "$$token" > "$$work_root/.osa-compose-owner"
	compose=(docker compose --project-name "$$project" $(E2E_FILES))
	cleanup() {
	  status=$$?
	  trap - EXIT
	  if [ "$$status" -ne 0 ]; then
	    $${compose[@]} logs --no-color --tail=100 app || true
	  fi
	  OSA_PROJECT_SCOPE="$$scope" python3 scripts/compose_cleanup.py --temp-root "$$work_root" --token "$$token" --kind e2e || status=1
	  exit "$$status"
	}
	trap cleanup EXIT
	port="$${OSA_E2E_PORT:-$$(python3 -c 'import socket; s=socket.socket(); s.bind(("127.0.0.1", 0)); print(s.getsockname()[1]); s.close()')}"
	export OSA_PORT="$$port" OSA_ENVIRONMENT=development OSA_VERSION=make-e2e
	export DATASET_DIR=/data DATASET_TTL_SECONDS=60 PUBLIC_DEMO_MODE=false
	$${compose[@]} config --quiet
	$${compose[@]} up --build --detach
	ready=0
	for _ in $$(seq 1 120); do
	  if curl -fsS "http://127.0.0.1:$$port/health/ready" >/dev/null; then
	    ready=1
	    break
	  fi
	  container_id="$$( $${compose[@]} ps -q app )"
	  if [ -n "$$container_id" ]; then
	    status="$$(docker inspect --format='{{.State.Health.Status}}' "$$container_id")"
	    if [ "$$status" = unhealthy ]; then
	      $${compose[@]} logs --no-color --tail=100 app
	      exit 1
	    fi
	  fi
	  sleep 1
	done
	if [ "$$ready" -ne 1 ]; then
	  $${compose[@]} logs --no-color --tail=100 app
	  echo "App did not become ready within 120 seconds"
	  exit 1
	fi
	E2E_BASE_URL="http://127.0.0.1:$$port" npm --prefix frontend run e2e

clean:
	OSA_PROJECT_SCOPE="$(PROJECT_SCOPE)" python3 scripts/compose_cleanup.py
