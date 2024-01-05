import os
import io
import shutil
import zipfile
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
    source_code_zip = None
    files = []
    local_dir = f'{TMP_DIR}/{function_name}'
    if not os.path.exists(local_dir):
        os.mkdir(local_dir)
    function_dir = f'{S3_DIR}/{function_name}'

    client_load('s3')
    response = clients['s3'].list_objects_v2(
        Bucket=S3_BUCKET,
        Prefix=function_dir
    )
    contents = response['Contents']
    print(f'S3 source code contents for lambda function {function_name}: \n {contents}')
    if len(contents) > 0:
        for obj in contents:
            key = obj['Key']
            if key not in [f'{S3_DIR}/', f'{function_dir}/']:
                files.append(key)

    if len(files) > 0:
        for f in files:
            local_path = f.replace(function_dir, local_dir, 1)
            if not os.path.exists(os.path.dirname(local_path)):
                os.makedirs(os.path.dirname(local_path))
            clients['s3'].download_file(S3_BUCKET, f, local_path)
    client_unload('s3')

    print('source code files:')
    for subdir, dirs, files in os.walk(local_dir):
        for file in files:
            print(os.path.join(subdir, file))

    #zip the files
    if len(files) > 0:
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
