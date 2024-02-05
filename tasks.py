"""Replacement for Makefile."""
import os
import sys
import glob
from datetime import datetime
from pathlib import Path

from typing import Tuple

from invoke import task, Context  # type: ignore

PROJECT_NAME = "infrahub-demo-sony"

def git_info(context: Context) -> Tuple[str, str]:
    """Return the name of the current branch and hash of the current commit."""
    branch_name = context.run("git rev-parse --abbrev-ref HEAD", hide=True, pty=False)
    hash = context.run("git rev-parse --short HEAD", hide=True, pty=False)
    return branch_name.stdout.strip(), hash.stdout.strip()

@task
def generate_archive(context: Context):
    branch, commit = git_info(context=context)
    directory_name = os.path.basename(os.path.dirname(os.path.realpath(__file__)))
    package_name = f"{PROJECT_NAME}-{commit[:8]}.tar.gz"

    commands = [
        f"rm -rf /tmp/{PROJECT_NAME}",
        f"cp -a ../{directory_name} /tmp/{PROJECT_NAME}",
        f"git --git-dir /tmp/{PROJECT_NAME}/.git remote remove origin",
        f"tar -C /tmp -czf {package_name} {PROJECT_NAME}",
    ]

    for command in commands:
        result = context.run(command=command, pty=True)

    print(f"Package {package_name!r} generated successfully.")


@task
def load_schema(context: Context, schema: Path="./models/infrastructure_base.yml") -> None:
    context.run(f"infrahubctl schema load {schema}")
    restart(context, component="infrahub-server")

@task
def load_data(context: Context, script: Path="./models/infrastructure_edge.py") -> None:
    context.run(f"infrahubctl run {script}")

@task
def destroy(context: Context) -> None:
    context.run("docker compose down -v")

@task
def stop(context: Context) -> None:
    context.run("docker compose down")

@task
def start(context: Context) -> None:
    context.run("docker compose up -d")

@task
def restart(context: Context, component: str="")-> None:
    if not component:
        context.run("docker compose restart")

    context.run(f"docker compose restart {component}")

