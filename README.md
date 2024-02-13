# Infrahub - Demo repository for the Sony POC

This repository is demoing the key Infrahub features for the Sony POC.

## Personal fork

If you want to be able to make change to this repository, it is recommended to create a fork of this repository.
Changes can be merged into the upstream repository using the pull request workflow.

## Using Github CodeSpaces

To have a consistent user experience, independent of hardware resources, we recommend the usage of Github CodeSpaces.

- Click the green `Code` button
- Switch to the `Codespaces` tab
- Click the `Create codespace on main` button (or click the `...` button and select `New with options` to be able to select your region)

## Using the demo environment

### Prerequisites

Define and export the following environment variables
```bash
export INFRAHUB_PRODUCTION=false
export INFRAHUB_SECURITY_SECRET_KEY=327f747f-efac-42be-9e73-999f08f86b92
export INFRAHUB_SDK_API_TOKEN=06438eb2-8019-4776-878c-0941b1f1d1ec
export INFRAHUB_SDK_TIMEOUT=20
export INFRAHUB_METRICS_PORT=8001
export INFRAHUB_DB_TYPE=neo4j
export INFRAHUB_SECURITY_INITIAL_ADMIN_TOKEN=06438eb2-8019-4776-878c-0941b1f1d1ec
export INFRAHUB_CONTAINER_REGISTRY=9r2s1098.c1.gra9.container-registry.ovh.net
export INFRAHUB_VERSION=0.11.0
export DATABASE_DOCKER_IMAGE="neo4j:5.16.0-enterprise"
export CACHE_DOCKER_IMAGE="redis:7.2.4"
export MESSAGE_QUEUE_IMAGE="rabbitmq:3.12.12-management"
```

### Spin up Sony demo environment

```sh
invoke start
```

### Load the initial schema

```sh
invoke load-schema
```

### Load data into the environment

```sh
invoke load-data
```

### Stop the Sony demo environment

```sh
invoke stop
```

### Stop and destroy the Sony demo environment

```sh
invoke destroy
```
