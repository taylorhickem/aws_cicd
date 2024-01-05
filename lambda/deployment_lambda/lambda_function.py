import os
import io
import shutil
import zipfile
import boto3

TMP_DIR = '/tmp'
S3_DIR = 'lambda'
ENCODING = 'utf-8'
CLIENTS_AVAILABLE = [
    'cloudformation',
    'lambda',
    's3'
]
clients = {
    'cloudformation': None,
    'lambda': None,
    's3': None
}
STATUS_LABELS = [
    'FAILED',
    'SUCCESS'
]
ENV_VARIABLES = [
    'S3_BUCKET'
]
EVENT_VARIABLES = [
    'ACTION_TYPE',
    'FUNCTION_NAME'
]
ARCHITECTURES = [
    'x86_64'
]
STACK_CONFIG = {
    'stack_name': '',
    'template': '',
    'parameters': {},
    'rollback_actions': {}
}
STATUS_TYPE = 1
response_body = {
    'statusCode': 200,
    'Status': STATUS_LABELS[STATUS_TYPE],
    'message': ''
}
STACK_ALIVE_STATUS = 'CREATE_COMPLETE'
S3_BUCKET = ''
FUNCTION_NAME = ''
ACTION_TYPE = 'function_update'

def lambda_handler(event, context):
    global response_body, STATUS_TYPE
    response_body['request'] = {}
    response_body['environment'] = {}

    for v in ENV_VARIABLES:
        globals()[v] = os.environ[v]
        response_body['environment'][v] = os.environ[v]

    for a in event:
        if a in EVENT_VARIABLES:
            globals()[a] = event[a]
            response_body['request'][a] = event[a]

    if FUNCTION_NAME:
        response_body['request']['function_name'] = FUNCTION_NAME
        if ACTION_TYPE == 'function_update':
            #bucket_context = read_bucket_context(event) used together with S3 trigger on bucket
            #function_name = bucket_context['function_name']
            try:
                response_body['lambda_response'] = function_update(FUNCTION_NAME)
                STATUS_TYPE = 1
                message = f'updated lambda function code for {FUNCTION_NAME}.'
            except Exception as e:
                STATUS_TYPE = 0
                message = f'ERROR. failed to update lambda funciton code {FUNCTION_NAME}. {str(e)}'
        elif ACTION_TYPE == 'stack_update':
            cfn_response, message, STATUS_TYPE = stack_update(FUNCTION_NAME)
            response_body['cfn_response'] = cfn_response
        else:
            STATUS_TYPE = 0
            message = f'USER INPUT ERROR. Unrecognized ACTION_TYPE {ACTION_TYPE}. Allowed = [function_update, stack_update]'
    else:
        STATUS_TYPE = 1
        message = 'USER INPUT ERROR. No Lambda FUNCTION_NAME passed.'

    response_body['Status'] = STATUS_LABELS[STATUS_TYPE]
    response_body['message'] = message
    print(f'lambda execution completed. results {response_body}')
    return response_body


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
    if service in CLIENTS_AVAILABLE:
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


def stack_update(function_name):
    status_type = 1
    message = 'stack exists'
    cfn_response = {}
    read_stack_config(function_name)
    stack_name = STACK_CONFIG['stack_name']
    client_load('cloudformation')
    stack_deployed = stack_exists(stack_name)
    client_unload('cloudformation')
    if not stack_deployed:
        message = 'stack does not exists'
    return cfn_response, message, status_type


def read_stack_config(function_name):
    global STACK_CONFIG
    #client_load('s3')
    STACK_CONFIG['stack_name'] = 'lambda-blockytime-events-update'
    #client_unload('s3')


def stack_exists(stack_name):
    stack_alive = False
    stack_summaries = clients['cloudformation'].list_stacks()['StackSummaries']
    stack_count = len(stack_summaries)
    if stack_count > 0:
        i = 0
        while i < stack_count and not stack_alive:
            stack_summary = stack_summaries[i]
            if stack_summary['StackName'] == stack_name:
                stack_status = stack_summary['StackStatus']
                stack_alive = stack_status == STACK_ALIVE_STATUS
            i = i + 1
    return stack_alive
