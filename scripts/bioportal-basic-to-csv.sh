#!/usr/bin/env bash

set -e
set -o pipefail

HERE="$(dirname $0)"
downloadedAt="${1:?"No downloadedAt argument given"}"
file="${2:?"No argument file given"}"

echo 'downloadedAt,patientId,collectedDate,reportedDate,ageRange,testType,result,region,orderCreatedAt,resultCreatedAt'
"${HERE}"/bioportal-to-jsonl.sh "${downloadedAt}" "${file}" \
    | jq -e -r '[.downloadedAt, .patientId, .collectedDate, .reportedDate, .ageRange, .testType, .result, .region, .orderCreatedAt, .resultCreatedAt] | @csv'
