#!/usr/bin/env sh
set -e

# Use whoever invoked sudo, else the current user
TARGET="${SUDO_USER:-$USER}"

# Ensure the docker group exists
sudo groupadd -f docker

# Add the user to the docker group
sudo usermod -aG docker "$TARGET"

# If we're that user, start a new shell with the updated groups
if [ "$TARGET" = "$USER" ]; then
  echo "Starting a new shell with 'docker' group for $TARGET (type 'exit' to return)..."
  exec newgrp docker
else
  echo "Done. Re-login as $TARGET or run: sudo -iu $TARGET newgrp docker"
fi
