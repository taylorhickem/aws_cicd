import os
import json
import boto3

TMP_DIR = '/tmp'
clients = {
    's3': None
}
PARAMETERS = [
    'credential_group',
    'resource_name',
    'file_name',
    'file_type',
    'encoding'
]
ENV_VARIABLES = [
    'S3_BUCKET'
]
response_body = {
    'status': 'success',
    'message': 'script executed without exception'
}
S3_BUCKET = ''


def lambda_handler(event, context):
    global response_body

    response_body['environment'] = {}
    for v in ENV_VARIABLES:
        globals()[v] = os.environ[v]
        response_body['environment'][v] = os.environ[v]

    if 'cred_requests' in event:
        cred_requests = event['cred_requests']
        response_body['request'] = cred_requests
        payload = credentials_get(cred_requests)
        response_body['payload'] = payload
    else:
        response_body['payload'] = None
        response_body['status'] = 'failed'
        response_body['message'] = 'ERROR. missing required argument: cred_requests'

    print(f'lambda execution completed. results {response_body}')

    return {
        'statusCode': 200,
        'body': response_body
    }


def credentials_get(cred_requests):
    credentials = {}
    for k in cred_requests:
        credentials[k] = credential_get(**cred_requests[k])
    return credentials


def credential_get(
        credential_group='',
        resource_name='',
        file_name='',
        file_type='',
        encoding=''
        ):

    credential = None
    local_path = f'{TMP_DIR}/{file_name}'
    object_key = f'{credential_group}/{resource_name}/{file_name}'
    client_load('s3')
    clients['s3'].download_file(S3_BUCKET, object_key, local_path)
    client_unload('s3')

    if encoding:
        f = open(local_path, 'r', encoding=encoding)
    else:
        f = open(local_path, 'r')
    if file_type == 'text':
        credential = f.read()
    elif file_type == 'json':
        credential = json.load(f)

    return credential


def client_load(service):
    global clients
    if service in ['s3']:
        clients[service] = boto3.client(service)


def client_unload(service):
    global clients
    clients[service] = None
