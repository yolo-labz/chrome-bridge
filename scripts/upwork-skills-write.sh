#!/usr/bin/env bash
# upwork-skills-write.sh — fire updateSkillsGql with the captured 20 UIDs.
#
# Pre-req:
#   1. cb daemon running (auto-started by launch/profile-auto.sh)
#   2. Profile-Auto Chrome (CfT 145) running with chrome-bridge loaded
#   3. Pedro logged into Upwork in the Profile-Auto window (one-time)
#
# What it does:
#   1. Read profile_vv_gql_token from Profile-Auto cookies
#   2. Run getProfileSkills (sanity check current state)
#   3. Run updateSkillsGql with skills array from upwork-skill-uids.json

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
CB="$REPO_ROOT/cli/cb"
UIDS_JSON="$REPO_ROOT/captures/upwork-skill-uids.json"
PROFILE_URL="${UPWORK_PROFILE_URL:-~01dae7197e964ddf3f}"

if [[ ! -x "$CB" ]]; then
  echo "error: cb CLI not found at $CB" >&2; exit 2
fi
if [[ ! -f "$UIDS_JSON" ]]; then
  echo "error: skill UIDs json not found at $UIDS_JSON" >&2; exit 2
fi

echo "[1/4] reading profile_vv_gql_token from Profile-Auto Chrome..."
TOKEN="$("$CB" cookies-bearer https://www.upwork.com/ profile_vv_gql_token 2>/dev/null || true)"
if [[ -z "$TOKEN" ]]; then
  echo "error: profile_vv_gql_token cookie not found." >&2
  echo "       Pedro must log into Upwork in the Profile-Auto Chrome window first." >&2
  echo "       The relay daemon + Profile-Auto Chrome must be running:" >&2
  echo "       $REPO_ROOT/launch/profile-auto.sh --bg" >&2
  exit 3
fi
echo "      OK token=${TOKEN:0:25}..."

echo
echo "[2/4] fetching current skill list (sanity check)..."
"$CB" gql https://www.upwork.com/api/graphql/v1 \
  --alias getProfileSkills \
  --query 'query getProfileSkills($profileUrl: String) { talentVPDAuthProfile(filter:{profileUrl:$profileUrl}){profile{skills{node{id name rank}}}} }' \
  --vars "{\"profileUrl\":\"$PROFILE_URL\"}" \
  --bearer "$TOKEN" \
  | jq -r '.json.data.talentVPDAuthProfile.profile.skills[].node | "  \(.rank). \(.name) (id=\(.id))"' || {
    echo "warn: getProfileSkills failed, continuing anyway" >&2
  }

echo
echo "[3/4] building updateSkillsGql payload..."
SKILLS_PAYLOAD=$(jq '{input:{skills:[.resolved[] | {skillID: .id}]}}' "$UIDS_JSON")
echo "$SKILLS_PAYLOAD" | jq -r '.input.skills | length | "      skills count: \(.)"'

echo
echo "[4/4] firing updateSkillsGql mutation..."
"$CB" gql https://www.upwork.com/api/graphql/v1 \
  --alias updateSkillsGql \
  --query 'mutation updateTalentProfileSkills($input: TalentProfileSkillsInput!) { updateTalentProfileSkills(input: $input) { status } }' \
  --vars "$SKILLS_PAYLOAD" \
  --bearer "$TOKEN"

echo
echo "[done] verifying new skill list..."
"$CB" gql https://www.upwork.com/api/graphql/v1 \
  --alias getProfileSkills \
  --query 'query getProfileSkills($profileUrl: String) { talentVPDAuthProfile(filter:{profileUrl:$profileUrl}){profile{skills{node{id name rank}}}} }' \
  --vars "{\"profileUrl\":\"$PROFILE_URL\"}" \
  --bearer "$TOKEN" \
  | jq -r '.json.data.talentVPDAuthProfile.profile.skills[].node | "  \(.rank). \(.name)"'
