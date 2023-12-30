import os
import io
import shutil
import zipfile
import base64
import boto3

TMP_DIR = '/tmp'
S3_DIR = 'lambda'
ENCODING = 'utf-8'
clients = {
    'lambda': None,
    's3': None
}
ENV_VARIABLES = [
    'S3_BUCKET'
]
response_body = {
    'status': 'success',
    'message': 'updated lambda funciton code.'
}
ARCHITECTURES = [
    'x86_64'
]
S3_BUCKET = ''


def lambda_handler(event, context):
    global response_body
    response_body['request'] = {}
    response_body['environment'] = {}

    for v in ENV_VARIABLES:
        globals()[v] = os.environ[v]
        response_body['environment'][v] = os.environ[v]

    for a in event:
        if a in ENV_VARIABLES:
            globals()[a] = event[a]
            response_body['request'][a] = event[a]

    bucket_context = read_bucket_context(event)
    function_name = bucket_context['function_name']
    response_body['request']['function_name'] = function_name
    response_body['lambda_response'] = function_update(function_name)

    print(f'lambda execution completed. results {response_body}')

    return {
        'statusCode': 200,
        'body': response_body
    }


def read_bucket_context(event):
    bucket_context = {}
    if 'Records' in event:
        if 's3' in event['Records'][0]:
            object_details = event['Records'][0]['s3']['object']
            file_path = object_details['key']
            bucket_context['function_name'] = file_path.split('/')[1]
    return bucket_context


def client_load(service):
    global clients
    if service in ['lambda', 's3']:
        clients[service] = boto3.client(service)


def client_unload(service):
    global clients
    clients[service] = None


def function_update(function_name):
    source_code_zip_bytes = source_code_zip_from_s3(function_name)

    client_load('lambda')
    response = clients['lambda'].update_function_code(
        FunctionName=function_name,
        ZipFile=source_code_zip_bytes,
        Architectures=ARCHITECTURES
    )
    client_unload('lambda')
    return response


def source_code_zip_from_s3(function_name):
    local_dir = f'{TMP_DIR}/{function_name}'
    if not os.path.exists(local_dir):
        os.mkdir(local_dir)
    function_dir = f'{S3_DIR}/{function_name}'

    client_load('s3')
    objects = clients['s3'].list_objects_v2(
        Bucket=S3_BUCKET,
        Prefix=function_dir
    )
    print(objects['Contents'])
    for obj in objects['Contents']:
        f = obj['Key']
        if f not in [f'{S3_DIR}/', f'{function_dir}/']:
            file_name = f.split('/')[-1]
            local_path = f'{local_dir}/{file_name}'
            clients['s3'].download_file(S3_BUCKET, f, local_path)
    client_unload('s3')

    #zip the files
    zip_bytes = io.BytesIO()
    with zipfile.ZipFile(zip_bytes, 'w') as zipf:
        for root, _, files in os.walk(local_dir):
            for f in files:
                file_path = os.path.join(root, f)
                zipf.write(
                    file_path,
                    os.path.relpath(file_path, local_dir)
                )
    source_code_zip = zip_bytes.getvalue()

    shutil.rmtree(TMP_DIR, ignore_errors=True)
    return source_code_zip
