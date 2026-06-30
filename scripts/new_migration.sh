#!/usr/bin/env bash
# Create the next sequential Alembic migration stub, numbered automatically so
# nobody hand-picks a number (two people picking the same number is exactly how
# divergent heads happen).
#
#   scripts/new_migration.sh "short description of the change"
#
# Writes migrations/versions/NNNN_short_description.py with revision/down_revision
# already wired to the current single head. Refuses when there are multiple heads
# (resolve those first with `uv run alembic merge`).
set -euo pipefail

msg="${1:-}"
if [ -z "$msg" ]; then
  echo "usage: scripts/new_migration.sh \"short description\"" >&2
  exit 2
fi

cd "$(git rev-parse --show-toplevel)"

# Current head(s). In this repo a revision id IS the leading 4-digit number.
# (Avoid `mapfile` — macOS ships bash 3.2, which lacks it.)
heads="$(uv run alembic heads 2>/dev/null | grep -oE '^[0-9a-f]+' || true)"
count="$(printf '%s\n' "$heads" | grep -c . || true)"
if [ "$count" -ne 1 ]; then
  echo "✋ Expected exactly 1 migration head, found ${count}: $(echo $heads)" >&2
  echo "   Resolve first:  uv run alembic merge -m 'merge heads' $(echo $heads)" >&2
  exit 1
fi
head="$heads"

# next = head + 1, zero-padded to 4. 10# forces base-10 so leading zeros don't
# get read as octal.
next="$(printf '%04d' "$((10#$head + 1))")"

# slug: lowercase, collapse non-alphanumeric runs to "_", trim, cap at 40 chars.
slug="$(printf '%s' "$msg" | tr '[:upper:]' '[:lower:]' | tr -cs '[:alnum:]' '_' \
  | sed 's/^_//; s/_$//' | cut -c1-40)"

file="migrations/versions/${next}_${slug}.py"
if [ -e "$file" ]; then
  echo "✋ $file already exists" >&2
  exit 1
fi

cat > "$file" <<EOF
"""${msg}

Revision ID: ${next}
Revises: ${head}
"""

from alembic import op

revision = "${next}"
down_revision = "${head}"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("")  # TODO: forward DDL


def downgrade() -> None:
    op.execute("")  # TODO: reverse of upgrade()
EOF

echo "Created $file  (revises ${head})"
echo "Next: edit upgrade()/downgrade(), then  git add $file"
