#!/usr/bin/env bash
# Fetch the NTREX-128 reference/source files at runtime (CC BY-SA 4.0 —
# NOT committed to this Apache-2.0 repo; see LICENSES_AND_ATTRIBUTION.md).
set -euo pipefail
cd "$(dirname "$0")"
BASE="https://raw.githubusercontent.com/MicrosoftTranslator/NTREX/main/NTREX-128"
for spec in "eng_src:src.eng" "tha:ref.tha" "lao:ref.lao" "khm:ref.khm"; do
  name="${spec%%:*}"; urlpart="${spec##*:}"
  out="ntrex_${name}.txt"
  if [ -s "$out" ]; then
    echo "have $out"
  else
    curl -fsSL "$BASE/newstest2019-${urlpart}.txt" -o "$out"
    echo "fetched $out ($(wc -l < "$out") lines)"
  fi
done