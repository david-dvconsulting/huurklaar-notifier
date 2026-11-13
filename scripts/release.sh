#!/bin/bash
# Maakt een release: controleert, maakt de tag op main en pusht hem. Daarna bouwt en publiceert GitHub Actions
# (.github/workflows/release.yml).
# Gebruik: scripts/release.sh [--ask | --minor | --major | vX.Y.Z]
#   --ask vraagt of het een minor of major is (de run-config gebruikt dit; geen antwoord binnen 10 s = patch)
#   zonder argument: patch erbij (v1.2.3 wordt v1.2.4); --minor (v1.3.0); --major (v2.0.0);
#   of een eigen versie, ook een voorversie (vX.Y.Z-rc.N).
set -euo pipefail
cd "$(dirname "$0")/.."

[ "$(git branch --show-current)" = "main" ] || { echo "FOUT: je staat niet op main"; exit 1; }
[ -z "$(git status --porcelain --untracked-files=no)" ] || { echo "FOUT: er zijn niet-gecommitte wijzigingen"; exit 1; }
git fetch --tags --quiet origin || { echo "FOUT: tags ophalen mislukt (verschilt een lokale tag van die op origin?)"; exit 1; }
[ "$(git rev-parse HEAD)" = "$(git rev-parse origin/main)" ] || { echo "FOUT: main loopt niet gelijk met origin/main (pull of push eerst)"; exit 1; }

LAST="$(git tag --list 'v[0-9]*' --sort=-v:refname | grep -v -- '-rc' | head -1 || true)"
echo "Laatste release: ${LAST:-geen}"
ARG="${1:-}"
if [ "$ARG" = "--ask" ]; then
  ARG=""
  read -r -t 10 -p "Minor? (j/N, na 10 s: N): " ANSWER || true; echo
  [[ "${ANSWER:-}" == [jJyY]* ]] && ARG="--minor"
  ANSWER=""
  read -r -t 10 -p "Major? (j/N, na 10 s: N): " ANSWER || true; echo
  [[ "${ANSWER:-}" == [jJyY]* ]] && ARG="--major"
fi
if [[ "$ARG" == v* ]]; then
  TAG="$ARG"
else
  if [ -z "$LAST" ]; then MA=0; MI=1; PA=0; else IFS=. read -r MA MI PA <<<"${LAST#v}"; fi
  case "$ARG" in
    --major) [ -z "$LAST" ] && : || { MA=$((MA + 1)); MI=0; PA=0; } ;;
    --minor) [ -z "$LAST" ] && : || { MI=$((MI + 1)); PA=0; } ;;
    "") [ -z "$LAST" ] && : || PA=$((PA + 1)) ;;
    *) echo "FOUT: onbekend argument $ARG (gebruik --minor, --major of vX.Y.Z)"; exit 1 ;;
  esac
  TAG="v$MA.$MI.$PA"
  KIND="${ARG#--}"; echo "Soort release: ${KIND:-patch} ($LAST wordt $TAG)"
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
