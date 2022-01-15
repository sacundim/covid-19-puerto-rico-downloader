#!/usr/bin/env bash

set -e
set -o pipefail

HERE="$(dirname $0)"
downloadedAt="${1:?"No downloadedAt argument given"}"
file="${2:?"No argument file given"}"

echo 'downloadedAt,region,ageRange,sex,deathDate,reportDate'
"${HERE}"/bioportal-to-jsonl.sh "${downloadedAt}" "${file}" \
    | jq -e -r '[.downloadedAt, .region, .ageRange, .sex, .deathDate, .reportDate] | @csv'