#!/usr/bin/env bash
# Copyright 2021 The gRPC Authors
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
set -ex

# Enter the gRPC repo root
cd $(dirname $0)/../../..

source tools/internal_ci/helper_scripts/prepare_build_linux_rc

gcloud auth configure-docker

mkdir ~/grpc-test-infra && cd ~/grpc-test-infra
git clone --recursive https://github.com/wanlin31/test-infra.git .
git checkout feature/pre_build_images

export PREBUILD_IMAGE_PREFIX="gcr.io/grpc-testing/e2etesting/pre_built_workers"
export PREBUILT_IMAGE_TAG=$KOKORO_BUILD_INITIATOR-`date '+%F-%H-%M-%S'`
export ROOT_DIRECTORY_OF_DOCKERFILES="containers/pre_built_workers/"

go run tools/prepare_prebuilt_workers/prepare_prebuilt_workers.go \
 -l cxx:master \
 -p $PREBUILD_IMAGE_PREFIX \
 -t $PREBUILT_IMAGE_TAG \
 -r $ROOT_DIRECTORY_OF_DOCKERFILES

sleep 3m

go run  tools/delete_prebuilt_workers/delete_prebuilt_workers.go \
-p $PREBUILD_IMAGE_PREFIX \
-t $PREBUILT_IMAGE_TAG

echo "TODO: Add gRPC OSS Benchmarks here..."

