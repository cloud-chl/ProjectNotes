#!/bin/bash
set -euo pipefail

# ============ 配置 ============
base_dir=$(pwd)
local_harbor="10.129.67.36:30003/java"        # 本地 Harbor（留空则直推远端）
remote_harbor="dockertest.gf.com.cn/ums"
file=Dockerfile
arches=(amd64 arm64)                          # 支持的架构列表
platforms="linux/amd64,linux/arm64"           # buildx 多架构参数
red='\033[31m'
reset='\033[0m'

img="${1:-}"
tag="${2:-}"
dev="${3:-}"

# 第 2 个参数含环境关键字（test/prod/prd）时当作 dev，prd 归一为 prod
if [[ -z "$dev" ]]; then
    case "$tag" in
        test)     dev="test"; tag="" ;;
        prod|prd) dev="prod"; tag="" ;;
    esac
fi

usage()    { echo "Usage: $0 <image> [tag|test|prod|prd] [test|prod|prd]"; }
red_echo() { printf "${red}%s${reset}\n" "$*"; }
sanitize_key() { local v="$1"; v="${v//\//_}"; v="${v//:/_}"; printf '%s\n' "$v"; }

# ============ 通用函数 ============

# 本地构建记录的最新版本号；$1=日期 $2=后缀（可选），记录 tag 不匹配当天模式则视为 0
get_last_version() {
    local build_date="${1:-}" suffix="${2:-}" version=0 key value last_tag=""
    if [[ -f "$last_file" ]]; then
        while IFS='=' read -r key value; do
            case "$key" in
                tag)     last_tag="$value" ;;
                version) [[ "$value" =~ ^[0-9]+$ ]] && version="$value" ;;
            esac
        done < "$last_file"
    fi
    if [[ -n "$build_date" ]]; then
        local pattern="^v[0-9]+-${build_date}"
        [[ -n "$suffix" ]] && pattern+="-${suffix}"
        pattern+='$'
        [[ "$last_tag" =~ $pattern ]] || version=0
    fi
    printf '%s\n' "$version"
}

# 远端 tag 检查: 0=存在 1=不存在 2=查询失败
check_remote_tag_exists() {
    local output
    output=$(docker manifest inspect "$1" 2>&1) && return 0
    if echo "$output" | grep -qiE "manifest.*unknown|not found|no such manifest"; then
        return 1
    fi
    return 2
}

# 从 $1 起递增查找当天空闲 tag（test/默认格式: vN-日期[-后缀]），找到则写入全局 tag
find_free_tag() {
    local ver="$1" suffix="$2"
    for ((; ver <= 999; ver++)); do
        [[ -n "$suffix" ]] && tag="v${ver}-${build_date}-${suffix}" || tag="v${ver}-${build_date}"
        local rc=0
        check_remote_tag_exists "${remote_harbor}/${img}:${tag}" || rc=$?
        case $rc in
            0) echo "Tag ${tag} 已被远程占用，递增..." ;;
            1) return 0 ;;
            2) red_echo ">>> 远程仓库查询失败，使用当前版本号"; return 0 ;;
        esac
    done
    red_echo "错误: 今天已构建超过 999 个版本，请手动指定 tag" >&2
    exit 1
}

# 自动安装 jq（如果需要）
ensure_jq() {
    command -v jq >/dev/null 2>&1 && return 0
    echo "jq 未安装，正在自动安装..."
    command -v apt-get >/dev/null 2>&1 || { echo "无法自动安装 jq，请手动安装" >&2; return 1; }
    apt-get update -qq && apt-get install -y -qq jq
    command -v jq >/dev/null 2>&1
}

# 校验 manifest 是否包含全部架构
verify_manifest() {
    jq -e '
        ([.manifests[]?.platform | select(.os == "linux" and .architecture == "amd64")] | length) > 0 and
        ([.manifests[]?.platform | select(.os == "linux" and .architecture == "arm64")] | length) > 0
    ' "$1" >/dev/null
}

# 本地仓库连通性检测（能连通即用本地中转）
check_local_registry() {
    [[ -n "$local_harbor" ]] || return 1
    local host="${local_harbor%%/*}"
    curl -sk --connect-timeout 2 --max-time 3 "https://${host}/v2/" >/dev/null 2>&1 || \
    curl -sk --connect-timeout 2 --max-time 3 "http://${host}/v2/"  >/dev/null 2>&1
}

# 退出时清理本地镜像
cleanup_local_images() {
    [[ -n "${img:-}" && -n "${tag:-}" ]] || return 0

    local refs=()
    [[ "$use_local" == "true" ]] && refs+=("${local_harbor}/${img}:${tag}")
    for arch in "${arches[@]}"; do
        refs+=("${remote_harbor}/${img}:${tag}-${arch}")
    done
    for ref in "${refs[@]}"; do
        docker rmi -f "$ref" >/dev/null 2>&1 || true
    done

    docker images --format '{{.Repository}}:{{.Tag}}' 2>/dev/null |
        grep -F "$img" |
        xargs -r docker rmi -f >/dev/null 2>&1 || true
}

# 构建并推送单个架构（构建一次，推送可重试）
build_and_push_arch() {
    local arch="$1"
    local arch_ref="${remote_ref}-${arch}"

    red_echo ">>> Pushing ${arch} -> ${arch_ref}"

    if [[ "$use_local" == "true" ]]; then
        docker pull --platform="linux/${arch}" "$local_ref" || return 1
        docker tag "$local_ref" "$arch_ref" || return 1
    else
        docker buildx build --platform "linux/${arch}" \
            -f "$file" -t "$arch_ref" --load . || return 1
    fi

    for ((attempt = 1; attempt <= 3; attempt++)); do
        if docker push "$arch_ref"; then
            return 0
        fi
        red_echo "Push ${arch} 失败 (${attempt}/3)，重试..."
        sleep 3
    done
    return 1
}

# ============ 记录保存 ============

save_daily_summary() {
    local tmp_file="${daily_summary_file}.tmp"
    if [[ -f "$daily_summary_file" ]]; then
        awk -F $'\t' -v env="$build_env" -v ref="$remote_ref" '!($2 == env && $6 == ref)' \
            "$daily_summary_file" > "$tmp_file"
    else
        : > "$tmp_file"
    fi
    printf '%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\n' \
        "$build_date" "$build_env" "$1" "$img" "$tag" "$remote_ref" "$file" "$manifest_file" \
        >> "$tmp_file"
    mv "$tmp_file" "$daily_summary_file"
}

print_daily_summary() {
    [[ -s "$daily_summary_file" ]] || { echo "No verified images for ${build_date}."; return 0; }

    echo
    echo "Verified image tags for ${build_date}:"
    LC_ALL=C sort -t $'\t' -k2,2 -k3,3 "$daily_summary_file" |
        awk -F $'\t' '
            {
                if ($2 != env) {
                    if (printed) print ""
                    print "[" $2 "]"
                    env = $2
                    printed = 1
                }
                print "  - " $6 "  " $3
            }
        '
}

save_build_info() {
    cat > "$last_file" <<EOF
image=${img}
tag=${tag}
version=${tag_version}
built_at=${1}
dockerfile=${file}
remote_ref=${remote_ref}
platforms=${platforms}
manifest_file=${manifest_file}
EOF

    printf '%s\t%s\t%s\t%s\t%s\t%s\t%s\n' \
        "$1" "$img" "$tag" "$file" "$remote_ref" "$platforms" "$manifest_file" \
        >> "$history_file"

    save_daily_summary "$1"
}

# ===================== 主逻辑 =====================

[[ -n "$img" ]] || { usage; exit 1; }

# 环境后缀（tag 用）
case "$dev" in
    test) env_suffix="test" ;;
    prod) env_suffix="prd" ;;
    *)    env_suffix="$dev" ;;
esac

# 构建信息目录
build_info_dir="${base_dir}/.docker_build_info"
img_key="$(sanitize_key "$img")"
last_file="${build_info_dir}/${img_key}.last"
history_file="${build_info_dir}/${img_key}.history"
build_env="${dev:-default}"
mkdir -p "$build_info_dir"

build_date="$(date +%Y%m%d)"
daily_summary_file="${build_info_dir}/${build_date}.verified.tsv"

ensure_jq || exit 1

# ---------- tag 生成 ----------
# prod: v20260813；当天已构建过则交互确认后追加 -2/-3
# test/默认: v1-20260813[-test]，递增 + 远端冲突检测
if [[ -z "$tag" ]]; then
    if [[ "$dev" == "prod" ]]; then
        tag="v${build_date}"
        rc=0
        check_remote_tag_exists "${remote_harbor}/${img}:${tag}" || rc=$?
        if [[ $rc -eq 0 ]]; then
            read -r -p "生产包 ${tag} 今天已构建过，是否继续构建新版本? (y/N): " confirm || true
            [[ "$confirm" =~ ^[yY]$ ]] || { echo "已取消构建"; exit 0; }
            for ((seq_ver = 2; seq_ver <= 99; seq_ver++)); do
                tag="v${build_date}-${seq_ver}"
                rc=0
                check_remote_tag_exists "${remote_harbor}/${img}:${tag}" || rc=$?
                case $rc in
                    0) echo "Tag ${tag} 已被远程占用，递增..." ;;
                    1) break ;;
                    2) red_echo ">>> 远程仓库查询失败，使用当前版本号"; break ;;
                esac
            done
            ((seq_ver <= 99)) || { red_echo "错误: 今天已构建超过 99 个生产版本，请手动指定 tag" >&2; exit 1; }
        elif [[ $rc -eq 2 ]]; then
            red_echo ">>> 远程仓库查询失败，使用 ${tag}"
        fi
    else
        find_free_tag "$(($(get_last_version "$build_date" "$env_suffix") + 1))" "$env_suffix"
    fi
    echo "No tag provided. Auto tag: ${tag}"
fi

tag_version=""
[[ "$tag" =~ ^v([0-9]+)-[0-9]{8}(-[a-z]+)?$ ]] && tag_version="${BASH_REMATCH[1]}"
[[ -z "$tag_version" ]] && tag_version="$(get_last_version)"

tag_key="$(sanitize_key "$tag")"
manifest_file="${build_info_dir}/${img_key}_${tag_key}_manifest.json"
source_dir="${base_dir}/${img}"
local_ref="${local_harbor}/${img}:${tag}"
remote_ref="${remote_harbor}/${img}:${tag}"

# 手动指定 tag 时检查远端是否已存在
if [[ -n "${2:-}" ]]; then
    tag_exists_rc=0
    check_remote_tag_exists "$remote_ref" || tag_exists_rc=$?
    case $tag_exists_rc in
        0) red_echo "警告: 远程仓库已存在 ${remote_ref}，继续构建将覆盖已有镜像及 Manifest" ;;
        2) red_echo ">>> 无法查询远程仓库状态，将继续构建" ;;
    esac
fi

# ---------- 构建策略 ----------
if check_local_registry; then
    red_echo ">>> 策略: 本地仓库 (${local_harbor}) → 中转推送到远端"
    use_local=true
else
    red_echo ">>> 策略: 无本地仓库 → 直接推送到远端 (${remote_harbor})"
    use_local=false
fi

trap cleanup_local_images EXIT

[[ -d "$source_dir" ]] || { echo "Source directory not found: ${source_dir}" >&2; exit 1; }
[[ -f "${source_dir}/${file}" ]] || { echo "Dockerfile not found: ${source_dir}/${file}" >&2; exit 1; }
cd "$source_dir"

# ---------- 构建 ----------
if [[ "$use_local" == "true" ]]; then
    red_echo ">>> Buildx 构建 ${arches[*]} → ${local_ref}"
    docker buildx build --platform "$platforms" -f "$file" -t "$local_ref" --push .
fi
for arch in "${arches[@]}"; do
    build_and_push_arch "$arch"
done

# ---------- Manifest ----------
manifest_args=()
for arch in "${arches[@]}"; do
    manifest_args+=(--amend "${remote_ref}-${arch}")
done
if docker manifest inspect "$remote_ref" >/dev/null 2>&1; then
    red_echo ">>> 远程已有 Manifest，将覆盖更新: ${remote_ref}"
else
    red_echo ">>> 创建 Manifest: ${remote_ref}"
fi
# 已 push 新单架构镜像（digest 已变），必须重建并推送 manifest
docker manifest rm "$remote_ref" >/dev/null 2>&1 || true
docker manifest create "$remote_ref" "${manifest_args[@]}"
docker manifest push --purge "$remote_ref"

# ---------- 验证 ----------
red_echo ">>> 验证 Manifest: ${remote_ref}"
docker manifest inspect "$remote_ref" > "$manifest_file"
if ! verify_manifest "$manifest_file"; then
    red_echo "Manifest 校验失败: ${remote_ref} 缺少架构" >&2
    exit 1
fi
red_echo "Manifest OK: ${remote_ref} 包含 ${platforms}"

# ---------- 记录 ----------
built_at="$(date '+%Y-%m-%dT%H:%M:%S%z')"
save_build_info "$built_at"
echo "Build info saved: ${last_file}"
find "$build_info_dir" -type f -mtime +1 -delete 2>/dev/null || true
print_daily_summary
