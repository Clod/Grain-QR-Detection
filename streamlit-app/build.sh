#!/bin/bash
set -e

image="giar-grainqr-flask-app"
version="latest"


# build image
docker build . -f Dockerfile -t "$image":"$version" -t "$image":dev

# Broadcast image name and tag
echo "${image}:${version}"

