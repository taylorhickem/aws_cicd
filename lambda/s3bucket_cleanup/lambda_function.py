import boto3

STATUS_LABELS = [
    'FAILED',
    'SUCCESS'
]
EVENT_PASS_FIELDS = [
    'StackId',
    'RequestId',
    'LogicalResourceId'
]
resources = {
    's3': None
}
clients = {
    's3': None
}
STATUS_CODE = 0
S3_BUCKET = ''


def lambda_handler(event, context):
    global STATUS_CODE, S3_BUCKET
    response_body = {
        'Status': STATUS_LABELS[STATUS_CODE]
    }
    message = 'ERROR. bucket not emptied.'
    try:
        S3_BUCKET = event['ResourceProperties']['BucketName']
        request_type = event['RequestType']
        STATUS_CODE = 1
    except Exception as e:
        STATUS_CODE = 0
        message = f'ERROR. Unexpected request format. Expected fields ResourceProperties: BucketName and RequestType {event}. {str(e)}'

    if STATUS_CODE == 1:
        if request_type == 'Delete':
            STATUS_CODE, message = empty_bucket_contents(S3_BUCKET)
        else:
            message = f'Caller RequestType: {request_type} is NOT Delete. Exiting without emptying bucket.'

    response_body['Status'] = STATUS_LABELS[STATUS_CODE]
    response_body['Data'] = {'message': message}
    response_body['Reason'] = 'Log stream name: ' + context.log_stream_name
    response_body['PhysicalResourceId'] = context.log_stream_name
    for f in EVENT_PASS_FIELDS:
        if f in event:
            response_body[f] = event[f]
        else:
            response_body[f] = ''

    return response_body


def empty_bucket_contents(s3_bucket):
    status_code = 0
    message = f'failed to empty S3 Bucket {s3_bucket}'
    print(f'emptying contents for S3 Bucket {s3_bucket} ...')
    client_load('s3')
    try:
        contents = clients['s3'].list_objects_v2(Bucket=s3_bucket)['Contents']
        print(f'bucket contents {contents}')
        object_count = len(contents)
        if object_count > 0:
            bucket_keys = [{'Key': o['Key']} for o in contents]
            resources['s3'].Bucket(s3_bucket).delete_objects(Delete={'Objects': bucket_keys})
            status_code = 1
            message = f'success. deleted {object_count} objects from S3 Bucket {s3_bucket}'
        else:
            status_code = 1
            message = f'success. S3 Bucket {s3_bucket} is empty.'
    except Exception as e:
        status_code = 0
        message = f'ERROR. failed to empty contents from S3 Bucket {s3_bucket}. {str(e)}'
    client_unload('s3')
    print(message)
    return status_code, message


def client_load(service):
    global clients, resources
    if service in ['s3']:
        clients[service] = boto3.client(service)
        resources[service] = boto3.resource(service)


def client_unload(service):
    global clients, resources
    clients[service] = None
    resources[service] = None