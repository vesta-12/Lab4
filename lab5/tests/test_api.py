"""Real integration tests through nginx. R IDs are defined in spec.md v4."""
from uuid import UUID,uuid4
import pytest

def create(api,text='Functional Lab 5 record'):
    response=api('POST','/records',json={'text':text})
    assert response.status_code==201,response.text
    return response

def test_TC01_time_served_by_R1_R42(api):
    r=api('GET','/time')
    assert r.status_code==200
    assert set(r.json())=={'server_time','served_by'}
    assert r.json()['served_by'] in {'api1','api2','api3'}

def test_TC02_echo_legacy_R2_R3(api):
    assert api('POST','/echo',json={'message':'hello'}).json()=={'message':'hello'}
    assert api('POST','/echo',json={}).status_code==400

def test_TC03_create_contract_R33_R39(api):
    r=create(api,'Hello from Lab 5')
    body=r.json()
    assert set(body)=={'id','text','served_by'}
    assert str(UUID(body['id']))==body['id'] and UUID(body['id']).version==4
    assert body['text']=='Hello from Lab 5'
    assert r.headers['Location']=='/records/'+body['id']

def test_TC04_read_original_R34(api):
    text='Exact Unicode text: Привет, Lab 5!'
    body=create(api,text).json()
    response=api('GET','/records/'+body['id'])
    assert response.status_code==200
    assert response.json()['id']==body['id'] and response.json()['text']==text

def test_TC05_missing_R34(api):
    r=api('GET','/records/'+str(uuid4()))
    assert r.status_code==404 and r.json()=={'error':'record not found'}

@pytest.mark.parametrize('record_id',['invalid-id','ABCDEF00-0000-4000-8000-000000000000'])
def test_TC06_invalid_id_R35(api,record_id):
    r=api('GET','/records/'+record_id)
    assert r.status_code==400 and 'error' in r.json()

@pytest.mark.parametrize('payload',[{},[],{'text':None},{'text':42},{'text':''}])
def test_TC07_invalid_input_R36(api,payload):
    assert api('POST','/records',json=payload).status_code==400

def test_TC08_malformed_json_R36(api):
    assert api('POST','/records',data='{',headers={'Content-Type':'application/json'}).status_code==400
    assert api('POST','/records',data='hello',headers={'Content-Type':'text/plain'}).status_code==400

@pytest.mark.parametrize('text',['x'*65536,'é'*32768],ids=['ascii','unicode'])
def test_TC09_exact_limit_R37(api,text):
    body=create(api,text).json()
    r=api('GET','/records/'+body['id'])
    assert r.status_code==200 and r.json()['text']==text

@pytest.mark.parametrize('text',['x'*65537,'é'*32769],ids=['ascii','unicode'])
def test_TC10_above_limit_R37(api,text):
    assert api('POST','/records',json={'text':text}).status_code==400

def test_TC11_invalid_unicode_and_body_limit_R36_R37(api):
    assert api('POST','/records',data='{"text":"\\ud800"}',headers={'Content-Type':'application/json'}).status_code==400
    assert api('POST','/records',data='x'*524289,headers={'Content-Type':'application/json'}).status_code==400

def test_TC12_cross_replica_R40_R42(api):
    body=create(api,'Shared MongoDB state across API copies').json()
    seen=set()
    for _ in range(12):
        r=api('GET','/records/'+body['id'])
        assert r.status_code==200 and r.json()['text']==body['text']
        seen.add(r.json()['served_by'])
    assert len(seen)>=2,seen

def test_TC13_unique_ids_R33(api):
    a=create(api,'same text').json()['id']
    b=create(api,'same text').json()['id']
    assert a!=b
