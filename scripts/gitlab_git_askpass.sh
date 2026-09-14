#!/bin/sh

case "$1" in
  *sername*) printf '%s\n' oauth2 ;;
  *assword*) printf '%s\n' "$GITLAB_API_TOKEN" ;;
  *) exit 1 ;;
esac
