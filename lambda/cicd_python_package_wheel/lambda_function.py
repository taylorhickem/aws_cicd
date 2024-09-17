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
    'SOURCE_BUCKET',
    'SOURCE_PREFIX',
    'LIB_PREFIX'
]
response_body = {
        'status': 'script executed without exception'
}
ACTION_TYPE = 'wheel_build'


def lambda_handler(event, context):
    global response_body, LAYER_NAME, ACTION_TYPE, VERSION_TAG
    
    response_body['environment'] = {}
    for v in ENV_VARIABLES:
        globals()[v] = os.environ[v]
        response_body['environment'][v] = os.environ[v]

    response_body['request'] = {}
    bucket_context = read_bucket_context(event)
    print(f'found bucket context: {bucket_context}')
    if bucket_context:
        ACTION_TYPE = 'wheel_build'
        event_bucket = bucket_context['event_bucket']
        package_name = bucket_context['package_name']
        response_body['request']['event_bucket'] = event_bucket
        response_body['request']['package_name'] = package_name
    else:
        for a in event:
            globals()[a] = event[a]
            response_body['request'][a] = event[a]

    response_body['ACTION_TYPE'] = ACTION_TYPE
    if (ACTION_TYPE == 'wheel_build') and event_bucket == SOURCE_BUCKET:
        print(f'building wheel with package_name:{package_name}')
        wheel_build(
            package_name
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
            package_name = object_details['key'].split('/')[0]
            bucket_context['package_name'] = package_name
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


def wheel_build(package_name):
    download_from_s3(
        package_name,
        SOURCE_BUCKET        
    )
    #bash install wheel package
    #bash wheel build


def download_from_s3(directory_name, s3_bucket, s3_dir='', local_dir=''):
    files = []
    if not s3_dir:
        s3_dir = SOURCE_PREFIX[:-1]
    if not local_dir:
        local_dir = os.path.join(TMP_DIR, directory_name)
    remote_dir = f'{s3_dir}/{directory_name}'
    client_load('s3')
    response = clients['s3'].list_objects_v2(
        Bucket=s3_bucket,
        Prefix=remote_dir
    )
    contents = response['Contents']
    print(f'S3 source code contents for directory {directory_name}: \n {contents}')
    if len(contents) > 0:
        for obj in contents:
            key = obj['Key']
            if key not in [f'{s3_dir}/', f'{remote_dir}/']:
                files.append(key)

    file_count = len(files)
    print(f'found {file_count} files.')
    if file_count > 0:
        if not os.path.exists(local_dir):
            os.mkdir(local_dir)
        for f in files:
            local_path = f.replace(remote_dir, local_dir, 1)
            if not os.path.exists(os.path.dirname(local_path)):
                os.makedirs(os.path.dirname(local_path))
            clients['s3'].download_file(s3_bucket, f, local_path)
    client_unload('s3')

    print('source code files downloaded:')
    for subdir, dirs, files in os.walk(local_dir):
        for file in files:
            print(os.path.join(subdir, file))
