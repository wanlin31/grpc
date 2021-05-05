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

# This is to ensure we can push and pull images from gcr.io. We do not
# necessarily need it to run load tests, but will need it when we employ
# pre-built images in the optimization.
gcloud auth configure-docker

# Connect to benchmarks-prod cluster.
gcloud config set project grpc-testing
gcloud container clusters get-credentials benchmarks-prod \
    --zone us-central1-b --project grpc-testing

# Set up environment varibles
export PREBUILD_IMAGE_PREFIX="gcr.io/grpc-testing/e2etesting/pre_built_workers"
export PREBUILT_IMAGE_TAG=$KOKORO_BUILD_INITIATOR-`date '+%F-%H-%M-%S'`
export ROOT_DIRECTORY_OF_DOCKERFILES="../test-infra/containers/pre_built_workers/"

# Build and push all prebuilt images for runable tests
go run ../test-infra/tools/prepare_prebuilt_workers/prepare_prebuilt_workers.go \
 -l cxx:master \
 -l java:master \
 -l go:master \
 -l ruby:master \
 -l python:master \
 -l csharp:master \
 -p $PREBUILD_IMAGE_PREFIX \
 -t $PREBUILT_IMAGE_TAG \
 -r $ROOT_DIRECTORY_OF_DOCKERFILES

# Generate loadtest template for prebuilt images
tools/run_tests/performance/loadtest_template.py \
    -i ../test-infra/config/samples/*with_pre_built_workers.yaml \
    --inject_client_pool --inject_server_pool --inject_big_query_table \
    --inject_timeout_seconds \
    -o ./tools/run_tests/performance/templates/loadtest_template_prebuilt_all_languages.yaml \
    --name prebuilt_all_languages

# This is subject to change. Runs a single test and does not wait for the
# result.
tools/run_tests/performance/loadtest_config.py -l c++ -l go \
    -t ./tools/run_tests/performance/templates/loadtest_template_prebuilt_all_languages.yaml \
    -s client_pool=workers-8core -s server_pool=workers-8core \
    -s big_query_table=e2e_benchmarks.experimental_results \
    -s timeout_seconds=900 --prefix="kokoro-test" -u $PREBUILT_IMAGE_TAG \
    -s prebuilt_image_prefix=$PREBUILD_IMAGE_PREFIX
    -s prebuilt_image_tag=$PREBUILT_IMAGE_TAG
    -r '(go_generic_sync_streaming_ping_pong_secure|go_protobuf_sync_unary_ping_pong_secure|cpp_protobuf_async_streaming_qps_unconstrained_secure)$' \
    -o ./loadtest_with_prebuilt_images.yaml

# Dump the contents of the loadtest.yaml (since loadtest_config.py doesn't
# list the scenarios that will be run).
cat ./loadtest_with_prebuilt_images.yaml

# The original version of the client is a bit old, update to the latest release
# version v1.21.0.
kubectl version --client
curl -sSL -O https://dl.k8s.io/release/v1.21.0/bin/linux/amd64/kubectl
sudo install -o root -g root -m 0755 kubectl /usr/local/bin/kubectl
chmod +x kubectl
sudo mv kubectl $(which kubectl)
kubectl version --client

kubectl apply -f ./loadtest.yaml

# Delete all images built for this build 
go run ../test-infra/tools/delete_prebuilt_workers/delete_prebuilt_workers.go \
 -p $PREBUILD_IMAGE_PREFIX \
 -t $PREBUILT_IMAGE_TAG \
