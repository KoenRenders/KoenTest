# Sourced by scripts/test-local.sh, e2e-local.sh, measure-local.sh and
# measure-run.sh (#1891): the ONE place that reads a database URL, and the
# switch "the database already exists — use it".
#
# The switch, for the three local scripts:
#
#   EXISTING_DB_URL          the URL of a database server that already runs. Its
#                            database is the one the script connects to in order
#                            to make its own (as POSTGRES_DB is in the dev
#                            container); the script still derives its own
#                            database name, per working copy and per script, and
#                            takes user, password and host from this URL.
#                            A unix socket goes in libpq's form: nothing between
#                            "@" and "/", and the socket directory in ?host= —
#                            scheme://user:password@/postgres?host=/some/directory
#   EXISTING_DB_SOCKET_DIR   a directory on the machine that runs the script,
#                            mounted into the helper container at the place the
#                            URL's ?host= points at. Nothing here knows that path.
#
# With EXISTING_DB_URL set a script does not bring up the `db` service, reads no
# credentials from a container and does not attach its helper container to
# `dev_internal`. Both unset: the commands of before, unchanged.
#
# A helper container keeps the network and the mounts it was created with: after
# switching between the two ways, run once with VERS=1.
#
# In a rootless Docker one more variable goes with these two, for test-local.sh
# only: HELPER_CONTAINER_USER=root (#1893; that script's header says why).

# db_url_parse URL — the parts of scheme://authority/name[?query]. Sets
# DB_URL_HEAD (scheme://authority), DB_URL_NAME and DB_URL_QUERY; fails on
# anything else. A "/" or a "?" in a password is written percent-encoded, as a
# URL asks.
#
# Parsed and not cut (#1891): "everything after the last /" reads the socket
# directory of ?host= as the database name, and a name guard that reads the
# wrong name guards nothing.
db_url_parse() {
  local pattern='^([a-zA-Z][a-zA-Z0-9+.-]*://[^/?#]*)/([^/?#]*)(\?([^#]*))?$'
  [[ "$1" =~ $pattern ]] || return 1
  DB_URL_HEAD="${BASH_REMATCH[1]}"
  DB_URL_NAME="${BASH_REMATCH[2]}"
  DB_URL_QUERY="${BASH_REMATCH[4]:-}"
}

# db_url_with_name URL NAME — the same server, user and query, another database.
db_url_with_name() {
  db_url_parse "$1" || return 1
  printf '%s/%s%s' "$DB_URL_HEAD" "$2" "${DB_URL_QUERY:+?$DB_URL_QUERY}"
}

# db_url_socket_dir URL — the directory in ?host=, empty when the URL names none.
db_url_socket_dir() {
  db_url_parse "$1" || return 1
  local part parts
  IFS='&' read -r -a parts <<<"$DB_URL_QUERY"
  for part in "${parts[@]}"; do
    case "$part" in host=/*) printf '%s' "${part#host=}" ;; esac
  done
}

# existing_db SCRIPT NAME — what the switch asks of a script, decided before its
# first docker call. Sets URL (the script's own database on the existing server)
# and RUN_ARGS (what `docker run` gets in place of the compose network); with
# the switch off it sets nothing and the script goes its usual way.
existing_db() {
  local script="$1" name="$2" socket
  if [ -z "${EXISTING_DB_URL:-}" ]; then
    if [ -n "${EXISTING_DB_SOCKET_DIR:-}" ]; then
      echo "$script: REFUSED — EXISTING_DB_SOCKET_DIR is set without EXISTING_DB_URL." >&2
      exit 2
    fi
    return 0
  fi
  if [ -n "${TEST_DATABASE_URL:-}" ]; then
    echo "$script: REFUSED — EXISTING_DB_URL and TEST_DATABASE_URL are both set; set one." >&2
    exit 2
  fi
  if ! URL="$(db_url_with_name "$EXISTING_DB_URL" "$name")"; then
    echo "$script: REFUSED — EXISTING_DB_URL does not read as scheme://[user[:password]@][host[:port]]/database[?query]." >&2
    exit 2
  fi
  RUN_ARGS=()
  if [ -n "${EXISTING_DB_SOCKET_DIR:-}" ]; then
    socket="$(db_url_socket_dir "$EXISTING_DB_URL")"
    if [ -z "$socket" ]; then
      echo "$script: REFUSED — EXISTING_DB_SOCKET_DIR is set, but EXISTING_DB_URL names no socket directory in ?host=." >&2
      exit 2
    fi
    RUN_ARGS=(-v "$EXISTING_DB_SOCKET_DIR:$socket")
  fi
}


# url_env NAME URL — one line of an environment file, NAME=URL (#1964). A database
# URL carries the password, so it never goes to `docker run` or `docker exec` as
# `-e NAME=value`: that puts it in the command line of the docker client, which
# every user of the machine can read while the command runs. It goes through
# `--env-file <(url_env NAME "$URL")`: the client reads the pipe, and no file is
# left behind. An environment file of the caller's own (e2e.env) goes beside it.
url_env() {
  printf '%s=%s\n' "$1" "$2"
}

# warn_if_no_init CONTAINER SCRIPT — one line when a helper container that already
# exists was made without the init process (#1964): its first process, `sleep
# infinity`, reaps nothing, so every `docker exec` leaves defunct processes in it.
# A container keeps what it was created with, so it is not recreated under a run;
# the line says how, and that it is the caller's own container to recreate.
warn_if_no_init() {
  local init
  init="$(docker inspect -f '{{.HostConfig.Init}}' "$1" 2>/dev/null || true)"
  if [ "$init" != "true" ]; then
    echo "$(basename "$0"): the helper container $1 has no init process, so defunct processes pile up in it — recreate your own once with: VERS=1 scripts/$2" >&2
  fi
}
