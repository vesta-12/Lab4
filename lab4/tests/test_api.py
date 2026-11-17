"""Isolated contract tests. These mocks are NOT the E1-E4 experiments."""
import io
import sys
from pathlib import Path
from unittest.mock import Mock

import pytest
import redis
from botocore.exceptions import ClientError, EndpointConnectionError

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app import create_app

ID = "00000000-0000-4000-8000-000000000001"


@pytest.fixture
def api():
    s3, primary, replica = Mock(), Mock(), Mock()
    primary.get.return_value = "7"
    replica.get.return_value = "6"
    primary.incr.return_value = 8
    client = create_app({"TESTING": True}, s3, primary, replica).test_client()
    return client, s3, primary, replica


def error(code):
    return ClientError({"Error": {"Code": code}}, "test")


def test_legacy_contract(api):
    c = api[0]
    assert set(c.get('/time').json) == {'server_time', 'served_by'}
    assert c.post('/echo', json={'message':'hello'}).json == {'message':'hello'}
    assert c.post('/echo', json={}).status_code == 400


@pytest.mark.parametrize('body', [{}, [], None, {'text':1}, {'text':None}, {'text':''}])
def test_invalid_file_json(api, body):
    c, s3, _, _ = api
    assert c.post('/files', json=body).status_code == 400
    s3.put_object.assert_not_called()


def test_malformed_json(api):
    assert api[0].post('/files', data='{', content_type='application/json').status_code == 400
    assert api[0].post('/files', data='hello', content_type='text/plain').status_code == 400


def test_upload_and_read(api):
    c, s3, _, _ = api
    result = c.post('/files', json={'text':'Hello'})
    assert result.status_code == 201
    assert result.headers['Location'] == '/files/' + result.json['file_id']
    assert s3.put_object.call_args.kwargs['Body'] == b'Hello'
    s3.get_object.return_value = {'Body':io.BytesIO(b'Hello')}
    assert c.get('/files/' + result.json['file_id']).json == dict(result.json, text='Hello')


def test_bucket_creation_and_race(api):
    c, s3, _, _ = api
    s3.head_bucket.side_effect = error('404')
    s3.create_bucket.side_effect = error('BucketAlreadyOwnedByYou')
    assert c.post('/files', json={'text':'race'}).status_code == 201
    s3.create_bucket.assert_called_once_with(Bucket='lab4-files')


@pytest.mark.parametrize('code', ['403', 'AccessDenied'])
def test_bucket_permission_not_hidden(api, code):
    c, s3, _, _ = api
    s3.head_bucket.side_effect = error(code)
    assert c.post('/files', json={'text':'hello'}).status_code == 503
    s3.create_bucket.assert_not_called()


def test_utf8_byte_limit(api):
    c = api[0]
    assert c.post('/files', json={'text':'x'*65536}).status_code == 201
    assert c.post('/files', json={'text':'x'*65537}).status_code == 400
    assert c.post('/files', json={'text':'é'*32769}).status_code == 400
    assert c.post('/files', json={'text':'\ud800'}).status_code == 400
    assert c.post('/files', data='x'*524289, content_type='application/json').status_code == 400


def test_missing_and_invalid_file(api):
    c, s3, _, _ = api
    assert c.get('/files/not-a-uuid').status_code == 400
    s3.get_object.assert_not_called()
    s3.get_object.side_effect = error('NoSuchKey')
    assert c.get('/files/'+ID).status_code == 404


def test_storage_outage(api):
    c, s3, _, _ = api
    s3.head_bucket.side_effect = EndpointConnectionError(endpoint_url='http://offline')
    assert c.post('/files', json={'text':'test'}).status_code == 503
    s3.get_object.side_effect = error('AccessDenied')
    assert c.get('/files/'+ID).status_code == 503


def test_counter_routing(api):
    c, _, primary, replica = api
    assert c.post('/counter/increment').json == {'value':8,'source':'primary'}
    primary.incr.assert_called_once_with('lab4:counter')
    replica.incr.assert_not_called()
    assert c.get('/counter').json == {'value':7,'source':'primary'}
    assert c.get('/counter?from=replica').json == {'value':6,'source':'replica'}
    primary.get.return_value = None
    assert c.get('/counter').json['value'] == 0


@pytest.mark.parametrize('query', ['from=', 'from=other', 'from=primary&from=replica'])
def test_counter_invalid_source(api, query):
    assert api[0].get('/counter?'+query).status_code == 400


def test_redis_outages(api):
    c, _, primary, replica = api
    primary.incr.side_effect = redis.ConnectionError('offline')
    primary.get.side_effect = redis.ConnectionError('offline')
    replica.get.side_effect = redis.TimeoutError('offline')
    assert c.post('/counter/increment').status_code == 503
    assert c.get('/counter?from=primary').status_code == 503
    assert c.get('/counter?from=replica').status_code == 503


def test_redis_readonly_and_bad_integer(api):
    c, _, primary, replica = api
    primary.incr.side_effect = redis.ReadOnlyError('read-only')
    assert c.post('/counter/increment').status_code == 503
    replica.incr.assert_not_called()
    primary.get.return_value = 'invalid-counter'
    assert c.get('/counter').status_code == 503


def test_missing_credentials(monkeypatch):
    monkeypatch.delenv('RUSTFS_ACCESS_KEY', raising=False)
    monkeypatch.delenv('RUSTFS_SECRET_KEY', raising=False)
    c = create_app({'TESTING':True}).test_client()
    assert c.post('/files', json={'text':'hello'}).status_code == 503


def test_environment_ports(monkeypatch):
    monkeypatch.setenv('REDIS_PRIMARY_PORT','6380')
    monkeypatch.setenv('REDIS_REPLICA_PORT','6379')
    app = create_app({'TESTING':True})
    assert app.extensions['lab4_nodes']['primary'].connection_pool.connection_kwargs['port'] == 6380
    assert app.extensions['lab4_nodes']['replica'].connection_pool.connection_kwargs['port'] == 6379
