DOCKER_REGISTRY ?= ghcr.io/chameleoncloud
DOCKER_TAG ?= latest

DOCKER_IMAGE = $(DOCKER_REGISTRY)/hammers:$(DOCKER_TAG)

.PHONY: build
build:
	docker build -t $(DOCKER_IMAGE) .

.PHONY: publish
publish:
	docker push $(DOCKER_IMAGE)
