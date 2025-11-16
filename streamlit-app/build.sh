#!/bin/bash
set -e

image="grainqr-streamlit-app"
version="latest"


# build image
docker build . -f Dockerfile -t "$image":"$version" -t "$image":dev

# Broadcast image name and tag
echo "${image}:${version}"

