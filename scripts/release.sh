#!/bin/bash
# Maakt een release: controleert, maakt de tag op main en pusht hem. Daarna bouwt en publiceert GitHub Actions
# (.github/workflows/release.yml). Gebruik: scripts/release.sh [vX.Y.Z]   (zonder argument vraagt het script ernaar)
set -euo pipefail
cd "$(dirname "$0")/.."

[ "$(git branch --show-current)" = "main" ] || { echo "FOUT: je staat niet op main"; exit 1; }
[ -z "$(git status --porcelain --untracked-files=no)" ] || { echo "FOUT: er zijn niet-gecommitte wijzigingen"; exit 1; }
git fetch --tags --quiet origin
[ "$(git rev-parse HEAD)" = "$(git rev-parse origin/main)" ] || { echo "FOUT: main loopt niet gelijk met origin/main (pull of push eerst)"; exit 1; }

LAST="$(git tag --list 'v[0-9]*' --sort=-v:refname | grep -v -- '-rc' | head -1 || true)"
echo "Laatste release: ${LAST:-geen}"
TAG="${1:-}"
if [ -z "$TAG" ]; then
  if [ -z "$LAST" ]; then SUGGEST="v0.1.0"; else
    IFS=. read -r MA MI PA <<<"${LAST#v}"; SUGGEST="v$MA.$MI.$((PA + 1))"
  fi
  read -r -p "Nieuwe versie [$SUGGEST] (voorversie: vX.Y.Z-rc.N): " TAG
  TAG="${TAG:-$SUGGEST}"
fi

python3 scripts/set-version.py "$TAG" --check >/dev/null   # stopt bij een ongeldige tag
git rev-parse -q --verify "refs/tags/$TAG" >/dev/null && { echo "FOUT: tag $TAG bestaat al"; exit 1; }

echo
echo "Dit maakt tag $TAG op $(git rev-parse --short HEAD) ($(git log -1 --format=%s)) en pusht hem."
echo "GitHub Actions publiceert daarna openbaar een release; dat is niet ongedaan te maken (enkel een nieuwere versie)."
read -r -p "Doorgaan? (j/N): " OK
[[ "$OK" == [jJyY]* ]] || { echo "Afgebroken."; exit 1; }

git tag -a "$TAG" -m "Huurklaar Meldingen $TAG"
git push origin "$TAG"
echo "Klaar. Volg de run: https://github.com/david-dvconsulting/huurklaar-notifier/actions"
