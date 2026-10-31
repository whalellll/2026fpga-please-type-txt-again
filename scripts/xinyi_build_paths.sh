#!/bin/sh
# Validate resolved build paths in this checkout or its explicit private link.
xinyi_build_path() {
    xq_path=$(realpath -m -- "$2") || return 2
    xq_build=$(realpath -m -- "$1/build") || return 2
    case "$xq_path" in "$xq_build"/*) return 0;; esac
    xq_link="$1/build/picture-e42-20261025"
    if [ -d "$xq_link" ]; then
        xq_private=$(realpath -e -- "$xq_link") || return 2
        case "$xq_path" in "$xq_private"/*) return 0;; esac
    fi
    echo 'Use this checkout build directory or its explicit private build link' >&2
    return 2
}
