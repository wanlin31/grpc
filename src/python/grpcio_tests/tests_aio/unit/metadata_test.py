# Copyright 2020 The gRPC Authors
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
"""Tests behavior around the metadata mechanism."""

import asyncio
import logging
import platform
import random
import unittest

import grpc
from grpc.experimental import aio

from tests_aio.unit._test_base import AioTestBase
from tests_aio.unit import _common

_TEST_CLIENT_TO_SERVER = '/test/TestClientToServer'
_TEST_SERVER_TO_CLIENT = '/test/TestServerToClient'
_TEST_TRAILING_METADATA = '/test/TestTrailingMetadata'
_TEST_ECHO_INITIAL_METADATA = '/test/TestEchoInitialMetadata'
_TEST_GENERIC_HANDLER = '/test/TestGenericHandler'
_TEST_UNARY_STREAM = '/test/TestUnaryStream'
_TEST_STREAM_UNARY = '/test/TestStreamUnary'
_TEST_STREAM_STREAM = '/test/TestStreamStream'

_REQUEST = b'\x00\x00\x00'
_RESPONSE = b'\x01\x01\x01'

_INITIAL_METADATA_FROM_CLIENT_TO_SERVER = (
    ('client-to-server', 'question'),
    ('client-to-server-bin', b'\x07\x07\x07'),
)
_INITIAL_METADATA_FROM_SERVER_TO_CLIENT = (
    ('server-to-client', 'answer'),
    ('server-to-client-bin', b'\x06\x06\x06'),
)
_TRAILING_METADATA = (('a-trailing-metadata', 'stack-trace'),
                      ('a-trailing-metadata-bin', b'\x05\x05\x05'))
_INITIAL_METADATA_FOR_GENERIC_HANDLER = (('a-must-have-key', 'secret'),)

_INVALID_METADATA_TEST_CASES = (
    (
        TypeError,
        ((42, 42),),
    ),
    (
        TypeError,
        (({}, {}),),
    ),
    (
        TypeError,
        (('normal', object()),),
    ),
    (
        TypeError,
        object(),
    ),
    (
        TypeError,
        (object(),),
    ),
)


class _TestGenericHandlerForMethods(grpc.GenericRpcHandler):

    def __init__(self):
        self._routing_table = {
            _TEST_CLIENT_TO_SERVER:
                grpc.unary_unary_rpc_method_handler(self._test_client_to_server
                                                   ),
            _TEST_SERVER_TO_CLIENT:
                grpc.unary_unary_rpc_method_handler(self._test_server_to_client
                                                   ),
            _TEST_TRAILING_METADATA:
                grpc.unary_unary_rpc_method_handler(self._test_trailing_metadata
                                                   ),
            _TEST_UNARY_STREAM:
                grpc.unary_stream_rpc_method_handler(self._test_unary_stream),
            _TEST_STREAM_UNARY:
                grpc.stream_unary_rpc_method_handler(self._test_stream_unary),
            _TEST_STREAM_STREAM:
                grpc.stream_stream_rpc_method_handler(self._test_stream_stream),
        }

    @staticmethod
    async def _test_client_to_server(request, context):
        assert _REQUEST == request
        assert _common.seen_metadata(_INITIAL_METADATA_FROM_CLIENT_TO_SERVER,
                                     context.invocation_metadata())
        return _RESPONSE

    @staticmethod
    async def _test_server_to_client(request, context):
        assert _REQUEST == request
        await context.send_initial_metadata(
            _INITIAL_METADATA_FROM_SERVER_TO_CLIENT)
        return _RESPONSE

    @staticmethod
    async def _test_trailing_metadata(request, context):
        assert _REQUEST == request
        context.set_trailing_metadata(_TRAILING_METADATA)
        return _RESPONSE

    @staticmethod
    async def _test_unary_stream(request, context):
        assert _REQUEST == request
        assert _common.seen_metadata(_INITIAL_METADATA_FROM_CLIENT_TO_SERVER,
                                     context.invocation_metadata())
        await context.send_initial_metadata(
            _INITIAL_METADATA_FROM_SERVER_TO_CLIENT)
        yield _RESPONSE
        context.set_trailing_metadata(_TRAILING_METADATA)

    @staticmethod
    async def _test_stream_unary(request_iterator, context):
        assert _common.seen_metadata(_INITIAL_METADATA_FROM_CLIENT_TO_SERVER,
                                     context.invocation_metadata())
        await context.send_initial_metadata(
            _INITIAL_METADATA_FROM_SERVER_TO_CLIENT)

        async for request in request_iterator:
            assert _REQUEST == request

        context.set_trailing_metadata(_TRAILING_METADATA)
        return _RESPONSE

    @staticmethod
    async def _test_stream_stream(request_iterator, context):
        assert _common.seen_metadata(_INITIAL_METADATA_FROM_CLIENT_TO_SERVER,
                                     context.invocation_metadata())
        await context.send_initial_metadata(
            _INITIAL_METADATA_FROM_SERVER_TO_CLIENT)

        async for request in request_iterator:
            assert _REQUEST == request

        yield _RESPONSE
        context.set_trailing_metadata(_TRAILING_METADATA)

    def service(self, handler_call_details):
        return self._routing_table.get(handler_call_details.method)


class _TestGenericHandlerItself(grpc.GenericRpcHandler):

    @staticmethod
    async def _method(request, unused_context):
        assert _REQUEST == request
        return _RESPONSE

    def service(self, handler_call_details):
        assert _common.seen_metadata(_INITIAL_METADATA_FOR_GENERIC_HANDLER,
                                     handler_call_details.invocation_metadata)
        return grpc.unary_unary_rpc_method_handler(self._method)


async def _start_test_server():
    server = aio.server()
    port = server.add_insecure_port('[::]:0')
    server.add_generic_rpc_handlers((
        _TestGenericHandlerForMethods(),
        _TestGenericHandlerItself(),
    ))
    await server.start()
    return 'localhost:%d' % port, server


class TestMetadata(AioTestBase):

    async def setUp(self):
        address, self._server = await _start_test_server()
        self._client = aio.insecure_channel(address)

    async def tearDown(self):
        await self._client.close()
        await self._server.stop(None)

    async def test_from_client_to_server(self):
        multicallable = self._client.unary_unary(_TEST_CLIENT_TO_SERVER)
        call = multicallable(_REQUEST,
                             metadata=_INITIAL_METADATA_FROM_CLIENT_TO_SERVER)
        self.assertEqual(_RESPONSE, await call)
        self.assertEqual(grpc.StatusCode.OK, await call.code())

    async def test_from_server_to_client(self):
        multicallable = self._client.unary_unary(_TEST_SERVER_TO_CLIENT)
        call = multicallable(_REQUEST)
        self.assertEqual(_INITIAL_METADATA_FROM_SERVER_TO_CLIENT, await
                         call.initial_metadata())
        self.assertEqual(_RESPONSE, await call)
        self.assertEqual(grpc.StatusCode.OK, await call.code())

    async def test_trailing_metadata(self):
        multicallable = self._client.unary_unary(_TEST_TRAILING_METADATA)
        call = multicallable(_REQUEST)
        self.assertEqual(_TRAILING_METADATA, await call.trailing_metadata())
        self.assertEqual(_RESPONSE, await call)
        self.assertEqual(grpc.StatusCode.OK, await call.code())

    @unittest.skipIf(platform.system() == 'Windows',
                     'https://github.com/grpc/grpc/issues/21943')
    async def test_invalid_metadata(self):
        multicallable = self._client.unary_unary(_TEST_CLIENT_TO_SERVER)
        for exception_type, metadata in _INVALID_METADATA_TEST_CASES:
            with self.subTest(metadata=metadata):
                call = multicallable(_REQUEST, metadata=metadata)
                with self.assertRaises(exception_type):
                    await call

    async def test_generic_handler(self):
        multicallable = self._client.unary_unary(_TEST_GENERIC_HANDLER)
        call = multicallable(_REQUEST,
                             metadata=_INITIAL_METADATA_FOR_GENERIC_HANDLER)
        self.assertEqual(_RESPONSE, await call)
        self.assertEqual(grpc.StatusCode.OK, await call.code())

    async def test_unary_stream(self):
        multicallable = self._client.unary_stream(_TEST_UNARY_STREAM)
        call = multicallable(_REQUEST,
                             metadata=_INITIAL_METADATA_FROM_CLIENT_TO_SERVER)

        self.assertTrue(
            _common.seen_metadata(_INITIAL_METADATA_FROM_SERVER_TO_CLIENT, await
                                  call.initial_metadata()))

        self.assertSequenceEqual([_RESPONSE],
                                 [request async for request in call])

        self.assertEqual(_TRAILING_METADATA, await call.trailing_metadata())
        self.assertEqual(grpc.StatusCode.OK, await call.code())

    async def test_stream_unary(self):
        multicallable = self._client.stream_unary(_TEST_STREAM_UNARY)
        call = multicallable(metadata=_INITIAL_METADATA_FROM_CLIENT_TO_SERVER)
        await call.write(_REQUEST)
        await call.done_writing()

        self.assertTrue(
            _common.seen_metadata(_INITIAL_METADATA_FROM_SERVER_TO_CLIENT, await
                                  call.initial_metadata()))
        self.assertEqual(_RESPONSE, await call)

        self.assertEqual(_TRAILING_METADATA, await call.trailing_metadata())
        self.assertEqual(grpc.StatusCode.OK, await call.code())

    async def test_stream_stream(self):
        multicallable = self._client.stream_stream(_TEST_STREAM_STREAM)
        call = multicallable(metadata=_INITIAL_METADATA_FROM_CLIENT_TO_SERVER)
        await call.write(_REQUEST)
        await call.done_writing()

        self.assertTrue(
            _common.seen_metadata(_INITIAL_METADATA_FROM_SERVER_TO_CLIENT, await
                                  call.initial_metadata()))
        self.assertSequenceEqual([_RESPONSE],
                                 [request async for request in call])
        self.assertEqual(_TRAILING_METADATA, await call.trailing_metadata())
        self.assertEqual(grpc.StatusCode.OK, await call.code())


if __name__ == '__main__':
    logging.basicConfig(level=logging.DEBUG)
    unittest.main(verbosity=2)