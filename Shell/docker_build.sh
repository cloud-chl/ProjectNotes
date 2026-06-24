#!/bin/bash
set -euo pipefail

base_dir=/home/cai/git
local_harbor=10.129.67.36:30003/java
remote_harbor=dockertest.gf.com.cn/ums
file=Dockerfile
platforms=linux/amd64,linux/arm64
red='\033[31m'
reset='\033[0m'

img="${1:-}"
tag="${2:-}"
dev="${3:-}"

if [[ "$tag" == "test" && -z "$dev" ]]; then
    dev="test"
    tag=""
elif [[ "$tag" == "debug" && -z "$dev" ]]; then
    dev="debug"
    tag=""
fi

usage() {
    echo "Usage: $0 <image> [tag] [test]"
    echo "       $0 <image> [test]"
}

red_echo() {
    printf "${red}%s${reset}\n" "$*"
}

sanitize_key() {
    local value="$1"
    value="${value//\//_}"
    value="${value//:/_}"
    printf '%s\n' "$value"
}

get_last_version() {
    local version=0
    local key
    local value

    if [[ -f "$last_file" ]]; then
        while IFS='=' read -r key value; do
            if [[ "$key" == "version" && "$value" =~ ^[0-9]+$ ]]; then
                version="$value"
            fi
        done < "$last_file"
    fi

    printf '%s\n' "$version"
}

get_last_version_for_date() {
    local build_date="$1"
    local version=0
    local key
    local value
    local last_tag=""

    if [[ -f "$last_file" ]]; then
        while IFS='=' read -r key value; do
            case "$key" in
                tag)
                    last_tag="$value"
                    ;;
                version)
                    if [[ "$value" =~ ^[0-9]+$ ]]; then
                        version="$value"
                    fi
                    ;;
            esac
        done < "$last_file"
    fi

    if [[ "$last_tag" =~ ^v[0-9]+-${build_date}$ ]]; then
        printf '%s\n' "$version"
    else
        printf '0\n'
    fi
}

extract_tag_version() {
    local input_tag="$1"

    if [[ "$input_tag" =~ ^v([0-9]+)-[0-9]{8}$ ]]; then
        printf '%s\n' "${BASH_REMATCH[1]}"
        return 0
    fi

    return 1
}

cleanup_local_images() {
    if [[ -z "${img:-}" || -z "${tag:-}" ]]; then
        return 0
    fi

    docker rmi -f \
        "${local_harbor}/${img}:${tag}" \
        "${remote_harbor}/${img}:${tag}-amd64" \
        "${remote_harbor}/${img}:${tag}-arm64" \
        >/dev/null 2>&1 || true

    docker images --format '{{.Repository}}:{{.Tag}}' 2>/dev/null |
        grep -F "$img" |
        xargs -r docker rmi -f >/dev/null 2>&1 || true
}

verify_manifest() {
    local manifest_file="$1"

    if command -v jq >/dev/null 2>&1; then
        jq -e '
            ([.manifests[]?.platform | select(.os == "linux" and .architecture == "amd64")] | length) > 0 and
            ([.manifests[]?.platform | select(.os == "linux" and .architecture == "arm64")] | length) > 0
        ' "$manifest_file" >/dev/null
        return $?
    fi

    if command -v python3 >/dev/null 2>&1; then
        python3 - "$manifest_file" <<'PY'
import json
import sys

with open(sys.argv[1], "r", encoding="utf-8") as f:
    data = json.load(f)

platforms = set()
for item in data.get("manifests", []):
    platform = item.get("platform") or {}
    os_name = platform.get("os")
    architecture = platform.get("architecture")
    if os_name and architecture:
        platforms.add(f"{os_name}/{architecture}")

sys.exit(0 if {"linux/amd64", "linux/arm64"}.issubset(platforms) else 1)
PY
        return $?
    fi

    echo "jq or python3 is required to verify manifest platforms" >&2
    return 1
}

save_build_info() {
    local built_at="$1"

    cat > "$last_file" <<EOF
image=${img}
tag=${tag}
version=${tag_version}
built_at=${built_at}
dockerfile=${file}
remote_ref=${remote_ref}
platforms=${platforms}
manifest_file=${manifest_file}
EOF

    printf '%s\t%s\t%s\t%s\t%s\t%s\t%s\n' \
        "$built_at" "$img" "$tag" "$file" "$remote_ref" "$platforms" "$manifest_file" \
        >> "$history_file"
}

if [[ -z "$img" ]]; then
    usage
    exit 1
fi

if [[ "$dev" == "test" ]]; then
    file=Dockerfile_test
elif [[ "$dev" == "debug" ]]; then
    file=Dockerfile_debug
fi

build_info_dir="${base_dir}/.docker_build_info"
img_key="$(sanitize_key "$img")"
last_file="${build_info_dir}/${img_key}.last"
history_file="${build_info_dir}/${img_key}.history"

mkdir -p "$build_info_dir"

build_date="$(date +%Y%m%d)"

if [[ -z "$tag" ]]; then
    last_version="$(get_last_version_for_date "$build_date")"
    tag="v$((last_version + 1))-${build_date}"
    echo "No tag provided. Auto tag: ${tag}"
fi

tag_version="$(extract_tag_version "$tag" || true)"
if [[ -z "$tag_version" ]]; then
    tag_version="$(get_last_version)"
fi

tag_key="$(sanitize_key "$tag")"
manifest_file="${build_info_dir}/${img_key}_${tag_key}_manifest.json"
source_dir="${base_dir}/${img}"
local_ref="${local_harbor}/${img}:${tag}"
remote_ref="${remote_harbor}/${img}:${tag}"

trap cleanup_local_images EXIT

if [[ ! -d "$source_dir" ]]; then
    echo "Source directory not found: ${source_dir}" >&2
    exit 1
fi

if [[ ! -f "${source_dir}/${file}" ]]; then
    echo "Dockerfile not found: ${source_dir}/${file}" >&2
    exit 1
fi

cd "$source_dir"

docker buildx build --platform "$platforms" -f "$file" -t "$local_ref" --push .

docker pull --platform=linux/amd64 "$local_ref"
docker tag "$local_ref" "${remote_ref}-amd64"
docker push "${remote_ref}-amd64"

docker pull --platform=linux/arm64 "$local_ref"
docker tag "$local_ref" "${remote_ref}-arm64"
docker push "${remote_ref}-arm64"

docker manifest rm "$remote_ref" >/dev/null 2>&1 || true
docker manifest create "$remote_ref" --amend "${remote_ref}-arm64" --amend "${remote_ref}-amd64"
docker manifest push --purge "$remote_ref"

red_echo "Validating remote manifest: ${remote_ref}"
docker manifest inspect "$remote_ref" > "$manifest_file"

if ! verify_manifest "$manifest_file"; then
    red_echo "Manifest check failed: ${remote_ref} is not ${platforms}" >&2
    red_echo "Manifest file: ${manifest_file}" >&2
    exit 1
fi

red_echo "Manifest OK: ${remote_ref} contains ${platforms}"

built_at="$(date '+%Y-%m-%dT%H:%M:%S%z')"
save_build_info "$built_at"
echo "Build info saved: ${last_file}"
