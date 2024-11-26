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
  _dotenv_file="${_dotenv_dir}/.env.docker-compose-native"
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

export TMPDIR=/mnt/docker/tmp/
export client_id=7ceb1042-1145-422a-82c2-4eaa67506721
export client_secret=2199bc68-778f-4672-a2f2-44dc6e8ea037
# prod
<<<<<<< HEAD
# export server_url=https://sts.nih.gov
# export host=fsivgl-rms01p
# export client_host=https://fsivgl-rms01p.ncifcrf.gov
# public
export server_url=https://sts.nih.gov
export host=abcsivglrms.cancer.gov
export client_host=https://abcsivglrms.cancer.gov
=======
export server_url=https://sts.nih.gov
export host=fsivgl-rms01p
export client_host=https://fsivgl-rms01p.ncifcrf.gov
# public
export server_url=https://sts.nih.gov
export host=fsivgl-rms01p
export client_host=https://fsivgl-rms01p.ccr.cancer.gov
>>>>>>> b796359d1ce6fcdd9246abb5193b3c91f42d6cfb
