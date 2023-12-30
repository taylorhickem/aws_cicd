import os
import zipfile
import shutil
import urllib
import boto3

TMP_DIR = '/tmp'
clients = {
    'lambda': None,
    's3': None
}
ENV_VARIABLES = [
    'SOURCE_BUCKET'
]
response_body = {
    'status': 'script executed without exception'
}
RUNTIMES = [
    'python3.9'
]
ARCHITECTURES = [
    'x86_64'
]
ACTION_TYPE = 'layer_update'
EVENT_BUCKET = ''


def lambda_handler(event, context):
    global response_body, LAYER_NAME, ACTION_TYPE, EVENT_BUCKET

    response_body['environment'] = {}
    for v in ENV_VARIABLES:
        globals()[v] = os.environ[v]
        response_body['environment'][v] = os.environ[v]

    response_body['request'] = {}
    bucket_context = read_bucket_context(event)
    if bucket_context:
        ACTION_TYPE = 'layer_update'
        EVENT_BUCKET = bucket_context['event_bucket']
        layer_name = bucket_context['layer_name']
        version_tag = bucket_context['version_tag']
        response_body['request']['event_bucket'] = EVENT_BUCKET
        response_body['request']['layer_name'] = layer_name
        response_body['request']['version_tag'] = version_tag
    else:
        for a in event:
            globals()[a] = event[a]
            response_body['request'][a] = event[a]

    response_body['ACTION_TYPE'] = ACTION_TYPE
    if ACTION_TYPE == 'layer_update':
        if version_tag:
            package_key = f'{layer_name}-{version_tag}.zip'
        else:
            package_key = f'{layer_name}.zip'
        print(f'publishing new lambda layer: {layer_name} version: {version_tag} ...')
        layer_update(
            EVENT_BUCKET,
            package_key,
            layer_name,
            version_tag
        )

    print(f'lambda execution completed. results {response_body}')

    return {
        'statusCode': 200,
        'body': response_body
    }


def read_bucket_context(event):
    bucket_context = {}
    if 'Records' in event:
        if 's3' in event['Records'][0]:
            bucket_details = event['Records'][0]['s3']['bucket']
            object_details = event['Records'][0]['s3']['object']
            bucket_context['event_bucket'] = bucket_details['name']
            file_name = object_details['key']
            if '-' in file_name:
                layer_name, version_tag = file_name.split('-')
                version_tag = version_tag.replace('.zip', '')
            else:
                layer_name = file_name.replace('.zip', '')
                version_tag = ''
            bucket_context['layer_name'] = layer_name
            bucket_context['version_tag'] = version_tag
    return bucket_context


def client_load(service):
    global clients
    if service in ['lambda', 's3']:
        clients[service] = boto3.client(service)


def client_unload(service):
    global clients
    clients[service] = None


def download_file(url, local_path):
    with urllib.request.urlopen(url) as response, open(local_path, 'wb') as out_file:
        out_file.write(response.read())


def function_update(s3_bucket, source_code_key, layer_name, version_tag):
    client_load('lambda')
    clients['lambda'].publish_layer_version(
        LayerName=layer_name,
        Description=version_tag,
        Content={
            'S3Bucket': s3_bucket,
            'S3Key': package_key
        },
        CompatibleRuntimes=RUNTIMES,
        CompatibleArchitectures=ARCHITECTURES
    )
    client_unload('lambda')
