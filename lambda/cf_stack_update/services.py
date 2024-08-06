import boto3

CLIENTS_AVAILABLE = [
    'cloudformation',
    's3',
    'sts'
]
clients = {
    'cloudformation': None,
    's3': None,
    'sts': None
}


def client_load(service):
    global clients
    if service in CLIENTS_AVAILABLE:
        clients[service] = boto3.client(service)


def client_unload(service):
    global clients
    clients[service] = None


def get_bucket_region(bucket_name):
    client_load('s3')
    response = clients['s3'].get_bucket_location(Bucket=bucket_name)
    region_name = response['LocationConstraint']
    client_unload('s3')
    return region_name