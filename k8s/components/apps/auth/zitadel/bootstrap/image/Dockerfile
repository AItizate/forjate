# Runtime image of the zitadel-bootstrap Job: CPython plus the pinned dependencies of
# ../requirements.txt, baked in, so a Job that runs it installs nothing at start and
# needs no egress besides the Zitadel API and the Kubernetes API. Built and published
# by .github/workflows/build-zitadel-bootstrap-image.yml.
#
# bootstrap.py is NOT in the image: it reaches the Job as a ConfigMap (see
# ../kustomization.yaml), so a change to the script does not need a new image. The
# image changes only when requirements.txt or the base image changes.
#
# Build context: the bootstrap/ directory (one level up), so requirements.txt is
# the same file the tests check:
#   docker buildx build -f bootstrap/image/Dockerfile bootstrap/
#
# The base is pinned by the digest of its multi-arch index (amd64 and arm64 are both
# built). Bump: `docker buildx imagetools inspect python:<version>-alpine<version>`.
ARG PYTHON_IMAGE=python:3.13.13-alpine3.23@sha256:420cd0bf0f3998275875e02ecd5808168cf0843cbb4d3c536432f729247b2acc

FROM ${PYTHON_IMAGE} AS deps
COPY requirements.txt /tmp/requirements.txt
# Every file is checked against its hash and only binary wheels are accepted: no
# sdist runs code at build time.
RUN pip install --no-cache-dir --disable-pip-version-check --no-compile \
      --require-hashes --only-binary=:all: \
      --target=/opt/bootstrap/deps --requirement=/tmp/requirements.txt

FROM ${PYTHON_IMAGE}
COPY --from=deps /opt/bootstrap/deps /opt/bootstrap/deps
# First the Alpine fixes published after the base was cut (the official python image
# lags behind them). Then nothing that installs or runs other code stays in the image:
# no pip or ensurepip (the bundled pip wheel), no apk, and no busybox shell or applets.
# The apk database stays so that image scanners still see the OS packages. busybox is
# called by its path because the applet symlinks (rm, sh...) disappear in the loop.
RUN apk upgrade --no-cache \
 && rm -rf /usr/local/lib/python3.13/site-packages/pip \
           /usr/local/lib/python3.13/site-packages/pip-* \
           /usr/local/lib/python3.13/ensurepip \
           /usr/local/bin/pip* \
           /sbin/apk /etc/apk /usr/share/apk /var/cache/apk \
 && /bin/busybox --list-full | while read -r applet; do /bin/busybox rm -f "/$applet"; done \
 && /bin/busybox rm -f /bin/busybox
ENV PYTHONPATH=/opt/bootstrap/deps \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1
# Same non-root identity the Job's securityContext sets.
USER 65532:65532
ENTRYPOINT ["python"]
