#!/usr/bin/env bash
#
# Convert a `minimal-info-unique-tests` download to CSV.
#

set -e
set -o pipefail

HERE="$(dirname $0)"
downloadedAt="${1:?"No downloadedAt argument given"}"
file="${2:?"No argument file given"}"

echo 'downloadedAt,collectedDate,reportedDate,ageRange,testType,result,city,createdAt'
"${HERE}"/bioportal-to-jsonl.sh "${downloadedAt}" "${file}" \
    | jq -r '[.downloadedAt, .collectedDate, .reportedDate, .ageRange, .testType, .result, .city, .createdAt] | @csv'
