#!/usr/bin/env bash
# Fetch FLORES-200 devtest (CC-BY-SA-4.0; NLLB, Meta).
# Not committed to the repo — run at evaluation time only.
set -euo pipefail
cd "$(dirname "$0")"
URL="https://dl.fbaipublicfiles.com/nllb/flores200_dataset.tar.gz"
if [ ! -d flores200_dataset ]; then
  echo "downloading $URL"
  curl -sL --fail -o flores200.tar.gz "$URL"
  tar xzf flores200.tar.gz
  rm flores200.tar.gz
fi
echo "present: $(ls flores200_dataset/devtest | wc -l) devtest files"
