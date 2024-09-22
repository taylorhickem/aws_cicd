import os
import time
import subprocess
import boto3


TMP_DIR = '/tmp'
clients = {
    'lambda': None,
    's3': None
}
ENV_VARIABLES = [
    'SOURCE_BUCKET',
    'SOURCE_PREFIX',
    'LIB_PREFIX',
    'TIMEOUT_SEC',
    'WHEEL_PACKAGE_BINARY_FILE'
]
INT_VAR = [
    'TIMEOUT_SEC'
]
response_body = {
        'status': 'script executed without exception'
}
ACTION_TYPE = 'wheel_build'
WHEEL_FILE_DIR = 'dist'
WHEEL_FILE_EXT = 'whl'
WHEEL_BUILD_SCRIPT = 'wheel_build.sh'
RECHECK_SEC = 3
TMP_PACKAGE_DIR = f'{TMP_DIR}/site-packages'
PYTHONPATH_DELIM = ':'


def lambda_handler(event, context):
    global response_body, ACTION_TYPE
    lambda_response = {
        'statusCode': 400,
    }
    
    response_body['environment'] = {}
    for v in ENV_VARIABLES:
        if v in os.environ:
            if v in INT_VAR:
                env_value = int(os.environ[v])
            else:
                env_value = os.environ[v]
            globals()[v] = env_value
            response_body['environment'][v] = env_value

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
        result = wheel_build(
            package_name
        )  
        response_body['build_result'] = result

    print(f'lambda execution completed. results {response_body}')

    lambda_response = {
        'statusCode': 200,
        'body': response_body
    }

    return lambda_response


def read_bucket_context(event):
    bucket_context = {}
    if 'Records' in event:
        if 's3' in event['Records'][0]:
            bucket_details = event['Records'][0]['s3']['bucket']
            object_details = event['Records'][0]['s3']['object']
            bucket_context['event_bucket'] = bucket_details['name']
            package_name = object_details['key'].split('/')[1]
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
    build_success = 1
    result = {'build_success': build_success}
    s3_source_dir = SOURCE_PREFIX[:-1]
    s3_target_dir = LIB_PREFIX[:-1]
    package_dir = os.path.join(TMP_DIR, package_name)
    local_wheel_dir = os.path.join(package_dir, WHEEL_FILE_DIR)

    try:
        s3_dir_download(
            package_name,
            SOURCE_BUCKET,
            s3_dir=s3_source_dir        
        )
    except Exception as e:
        result['errors'] = f'ERROR. failed to download source {package_name} from S3 {s3_source_dir}. {str(e)}'
        build_success = 0

    if build_success:        
        build_success, bash_result, errors = bash_wheel_build(package_name)
        print(bash_result)
    
    if build_success:        
        wheel_file, wheel_file_errors = get_wheel_filename(dir=package_dir)
        if wheel_file:
            try:
                s3_file_upload(
                    wheel_file, 
                    SOURCE_BUCKET,
                    s3_dir=s3_target_dir,
                    local_dir=local_wheel_dir
                )
            except Exception as e:
                result['errors'] = f'ERROR. failed to upload wheel file {wheel_file} at {local_wheel_dir} to S3 {s3_target_dir}. {str(e)}'
                build_success = 0
        else:
            result['errors'] = f'ERROR. failed to find wheel file in local dir {local_wheel_dir}. {wheel_file_errors}'
            build_success = 0

    result['build_success'] = build_success
    return result


def s3_dir_download(directory_name, s3_bucket, s3_dir='', local_dir=''):
    files = []
    if not local_dir:
        local_dir = os.path.join(TMP_DIR, directory_name)
    remote_dir = f'{s3_dir}/{directory_name}'
    client_load('s3')
    response = clients['s3'].list_objects_v2(
        Bucket=s3_bucket,
        Prefix=remote_dir
    )
    contents = response['Contents']
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


def s3_file_download(filename, s3_bucket, s3_dir='', local_dir=''):        
    if s3_dir:
        s3_key = f'{s3_dir}/{filename}'
    else:
        s3_key = filename
    if local_dir:
        local_path = os.path.join(local_dir, filename)
    else:
        local_path = os.path.join(TMP_DIR, filename)
    client_load('s3')
    response = clients['s3'].download_file(s3_bucket, s3_key, local_path)
    client_unload('s3')


def s3_file_upload(filename, s3_bucket, s3_dir='', local_dir=''):
    client_load('s3')
    if local_dir:
        local_path = os.path.join(local_dir, filename)
    else:
        local_path = filename
    if s3_dir:
        s3_key = f'{s3_dir}/{filename}'
    else:
        s3_key = filename
    print(f'uploading wheel {local_path} to S3 {s3_key} bucket {s3_bucket} ...')
    response = clients['s3'].upload_file(
        local_path,
        s3_bucket,
        s3_key
    )
    client_unload('s3')


def get_wheel_filename(dir=''):
    wheel_file = ''
    errors = ''
    counter_sec = 0
    while not wheel_file and counter_sec <= TIMEOUT_SEC:
        wheel_file = check_wheel_filename(dir=dir)
        if not wheel_file:
            time.sleep(RECHECK_SEC)
            counter_sec += RECHECK_SEC

    if not wheel_file:
        if counter_sec >= TIMEOUT_SEC:
            errors = f'ERROR. Failed to find .whl file in local dir {dir}. Timeout reached after {counter_sec} seconds.'
        else:
            errors = f'ERROR. Failed to find .whl file in local dir {dir}.'
    return wheel_file, errors


def check_wheel_filename(dir=''):
    wheel_file = ''
    if dir:
        wheel_dir = os.path.join(dir, WHEEL_FILE_DIR)
    else:
        wheel_dir = WHEEL_FILE_DIR
    if os.path.isdir(wheel_dir):
        print('found wheel dist dir')
        dir_files = os.listdir(wheel_dir)
        print(dir_files)
        if dir_files:
            wheel_file = [f for f in dir_files if f.endswith(WHEEL_FILE_EXT)][0]
    return wheel_file


def bash_wheel_build(package_name):
    success = 0
    errors = ''
    working_dir = os.path.join(TMP_DIR, package_name)
    s3_file_download(
        WHEEL_PACKAGE_BINARY_FILE,
        SOURCE_BUCKET,
        s3_dir=LIB_PREFIX[:-1],
        local_dir=working_dir
    )    
    bash_env = os.environ.copy()
    if 'PYTHONPATH' in bash_env:
        bash_env['PYTHONPATH'] = bash_env['PYTHONPATH'] + PYTHONPATH_DELIM + TMP_PACKAGE_DIR
    else:
        bash_env['PYTHONPATH'] = TMP_PACKAGE_DIR
    wheel_binary_path = f'{working_dir}/{WHEEL_PACKAGE_BINARY_FILE}'
    install_result = subprocess.run(
        ['python', '-m', 'pip', 'install', '--target', TMP_PACKAGE_DIR, wheel_binary_path],
        capture_output=True, 
        text=True
    )
    print(install_result)        
    result = subprocess.run(
        ['python', 'setup.py', 'bdist_wheel'],
        cwd=working_dir,
        env=bash_env,
        capture_output=True, 
        text=True
    )

    errors = result.stderr
    if not errors:
        success = 1        
    return success, result, errors
