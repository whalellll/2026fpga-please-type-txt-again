FROM ubuntu:22.04

ENV DEBIAN_FRONTEND=noninteractive

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        build-essential \
        ca-certificates \
        file \
        git \
        make \
        python3 \
        qemu-user \
    && rm -rf /var/lib/apt/lists/*
