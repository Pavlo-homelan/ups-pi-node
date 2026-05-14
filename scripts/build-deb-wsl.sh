#!/usr/bin/env bash
set -euo pipefail

src="${1:?source directory is required}"
out="${2:?output directory is required}"
src="$(cd "$src" && pwd)"
mkdir -p "$out"
out="$(cd "$out" && pwd)"
build_root="$(mktemp -d /tmp/ups-pi-node-build.XXXXXX)"
build_dir="$build_root/src"

mkdir "$build_dir"
tar \
    -C "$src" \
    --exclude=.git \
    --exclude=.venv-wsl \
    --exclude=__pycache__ \
    --exclude=dist \
    --exclude=build \
    --exclude="*.deb" \
    --exclude="*.changes" \
    --exclude="*.buildinfo" \
    -cf - . | tar -C "$build_dir" -xf -

cd "$build_dir"
find . -type d -exec chmod 0755 {} +
find . -type f -exec chmod 0644 {} +
chmod 0755 debian/rules debian/postinst debian/prerm deploy/scripts/ups-pi-node-hotspot-fallback deploy/scripts/ups-pi-node-enable-buses

base_version="$(dpkg-parsechangelog -S Version)"
if [[ -n "${UPS_PI_NODE_BUILD_VERSION:-}" ]]; then
    package_version="$UPS_PI_NODE_BUILD_VERSION"
elif [[ "${UPS_PI_NODE_AUTO_VERSION:-1}" == "0" ]]; then
    package_version="$base_version"
else
    upstream_version="${base_version%-*}"
    if [[ -n "${UPS_PI_NODE_BUILD_REVISION:-}" ]]; then
        build_revision="$UPS_PI_NODE_BUILD_REVISION"
    else
        build_revision=0
        shopt -s nullglob
        for artifact in "$out"/ups-pi-node_"$upstream_version"-*_all.deb; do
            filename="$(basename "$artifact")"
            artifact_version="${filename#ups-pi-node_}"
            artifact_version="${artifact_version%_all.deb}"
            artifact_revision="${artifact_version##*-}"
            if [[ "$artifact_revision" =~ ^[0-9]+$ && "$artifact_revision" -gt "$build_revision" ]]; then
                build_revision="$artifact_revision"
            fi
        done
        shopt -u nullglob
        build_revision=$((build_revision + 1))
    fi
    package_version="${upstream_version}-${build_revision}"
fi

if [[ "$package_version" != "$base_version" ]]; then
    escaped_version="${package_version//\\/\\\\}"
    escaped_version="${escaped_version//&/\\&}"
    sed -i "1s/(.*)/(${escaped_version})/" debian/changelog
fi

echo "Package version: $package_version"
dpkg-buildpackage -b -us -uc

deb="$build_root/ups-pi-node_${package_version}_all.deb"
if [[ ! -f "$deb" ]]; then
    echo "Expected package was not produced: $deb" >&2
    ls -la "$build_root" >&2
    exit 1
fi

cp "$deb" "$out"/
shopt -s nullglob
for artifact in "$build_root"/ups-pi-node_"$package_version"_*.buildinfo "$build_root"/ups-pi-node_"$package_version"_*.changes; do
    cp "$artifact" "$out"/
done
shopt -u nullglob

echo "Built $out/$(basename "$deb")"
