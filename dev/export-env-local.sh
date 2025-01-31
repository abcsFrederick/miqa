# Export environment variables from the .env file in the first argument.
# If no argument is given, default to "dev/.env.docker-compose-native".
# This file must be sourced, not run.

if [ -n "$1" ]; then
  # If an argument was provided, use it as the .env file
  _dotenv_file="$1"
else
  # Otherwise, use the default .env file
  if [ -n "$ZSH_VERSION" ]; then
    # ZSH has a different way to get the directory of the current script
    _dotenv_dir="$0:A:h"
  else
    # Assume this is Bash
    _dotenv_dir="$( dirname "${BASH_SOURCE[0]}" )"
  fi
  _dotenv_file="${_dotenv_dir}/.env.docker-compose-native-local"
fi

# Export all assignments in the $_dotenv_file
# Using "set -a" allows .env files with spaces or comments to work seamlessly
# https://stackoverflow.com/a/45971167
set -a
. "$_dotenv_file"
set +a

# Clean up, since sourcing this leaks any shell variables
unset _dotenv_dir
unset _dotenv_file

# localhost:8000
export TMPDIR=/mnt/docker/tmp/
export client_id=0b4a535a-9f88-4717-b4af-6b1b0cb48933
export client_secret=e246a609-243c-45f4-9f52-f75d9b2e85d9
# dev
export server_url=https://stsstg.nih.gov
export host=localhost:8000
export server_host=localhost:8000
export server_api_proxy=''
export workspace=fsivgl-rms01d
export client_host=http://localhost:8000
export client_subpath=''
<<<<<<< HEAD
export http_protocol = http
=======
>>>>>>> 3b8fd5c52a8c33fc26776240028b4f7c8a9b4f9b
