.PHONY: dev-up dev-down test test-backend test-core test-web lint

dev-up:
	docker compose up --build -d --wait
	@echo "Map: http://localhost:5173  ·  API health: http://localhost:5173/api/v1/health"

dev-down:
	docker compose down

test: test-backend test-web

test-backend:
	cd backend && uv run pytest

test-core:
	cd backend && uv run pytest tests/core

test-web:
	cd frontend && npm test

lint:
	cd backend && uv run ruff check . && uv run ruff format --check . && DEBUG=True uv run mypy .
	cd frontend && npm run lint && npm run typecheck && npm run format:check

# --- AWS (applied at the end of the project; see infra/) -------------------------------------
# Needs AWS credentials. STATE_BUCKET is the bucket created by `make infra-bootstrap`.
# Variables go in infra/main/terraform.tfvars (git-ignored).
TF_MAIN = terraform -chdir=infra/main

.PHONY: infra-bootstrap infra-plan infra-apply app-stop app-start app-status deploy-manual

infra-bootstrap:
	terraform -chdir=infra/bootstrap init
	terraform -chdir=infra/bootstrap apply

infra-plan:
	$(TF_MAIN) init -backend-config="bucket=$(STATE_BUCKET)"
	$(TF_MAIN) plan

infra-apply:
	$(TF_MAIN) init -backend-config="bucket=$(STATE_BUCKET)"
	$(TF_MAIN) apply

# Stop/start is for the build phase only. The app stays ON after submission.
app-stop:
	aws ec2 stop-instances --instance-ids $$($(TF_MAIN) output -raw instance_id)

app-start:
	aws ec2 start-instances --instance-ids $$($(TF_MAIN) output -raw instance_id)

app-status:
	aws ec2 describe-instance-status --include-all-instances \
		--instance-ids $$($(TF_MAIN) output -raw instance_id) \
		--query 'InstanceStatuses[0].InstanceState.Name' --output text

# Fallback if the push-triggered workflow did not run: start the CD workflow by hand.
deploy-manual:
	gh workflow run cd.yml
