#!/bin/sh
# agent-vault sets SSL_CERT_FILE to /root/.agent-vault/mitm-ca.pem (root-only).
# Hermes drops to uid hermes after /init, so httpx cannot load that CA → Errno 13.
# Install a readable CA bundle on the data volume (system CAs + broker MITM root).
set -e
if [ -f /root/.agent-vault/mitm-ca.pem ]; then
  dest=/opt/data/.agent-vault-mitm-ca.pem
  if [ -f /etc/ssl/certs/ca-certificates.crt ]; then
    cat /etc/ssl/certs/ca-certificates.crt /root/.agent-vault/mitm-ca.pem >"$dest"
  else
    cp /root/.agent-vault/mitm-ca.pem "$dest"
  fi
  chmod 644 "$dest"
  chown hermes:hermes "$dest" 2>/dev/null || true
  export SSL_CERT_FILE="$dest"
  export REQUESTS_CA_BUNDLE="$dest"
  export NODE_EXTRA_CA_CERTS="$dest"
  export GIT_SSL_CAINFO="$dest"
  export DENO_CERT="$dest"
fi
exec "$@"
