#!/bin/sh
# shellcheck shell=sh
# s6 with-contenv reads /run/s6/container_environment; on some hosts docker -e
# values are only visible on PID 1. Import missing vars from /proc/1/environ.

import_docker_env() {
  [ -r /proc/1/environ ] || return 0
  for var do
    eval "current=\${${var}-}"
    if [ -n "${current}" ]; then
      continue
    fi
    val="$(tr '\0' '\n' < /proc/1/environ | sed -n "s/^${var}=//p" | head -1)"
    if [ -n "${val}" ]; then
      export "${var}=${val}"
    fi
  done
}
