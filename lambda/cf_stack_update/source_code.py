import os
import io
import shutil
import zipfile
from services import client_load, client_unload, clients


TMP_DIR = '/tmp'
CF_DIR = 'cloudformation'

def stack_download_from_s3(stack_name, s3_bucket, s3_dir='', local_dir='', print_updates=True):
    files = []
    if not local_dir:
        local_dir = os.path.join(os.path.join(TMP_DIR, CF_DIR), stack_name)
    if s3_dir:
        remote_dir = f'{s3_dir}/{CF_DIR}/{stack_name}'
    else:
        remote_dir = f'{CF_DIR}/{stack_name}'
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
    if print_updates:
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

    if print_updates:
        print('source code files downloaded:')
    for subdir, dirs, files in os.walk(local_dir):
        for file in files:
            if print_updates:
                print(os.path.join(subdir, file))


def lambda_function_zip_to_S3(function_name, local_dir, s3_bucket, s3_prefix='', print_updates=True):
    zip_key = f'{s3_prefix}/{function_name}.zip'
    if print_updates:
        print(f'zipping source code to S3 bucket {s3_bucket} and key {zip_key} ...')
    zipobj = zip_buffer(local_dir)
    zipobj.seek(0)
    client_load('s3')
    clients['s3'].upload_fileobj(zipobj, s3_bucket, zip_key)
    client_unload('s3')
    if print_updates:
        print(f'source code zipped to {zip_key}.')


def zip_buffer(local_dir):
    zipobj = None
    if os.path.exists(local_dir):
        zipobj = io.BytesIO()
        with zipfile.ZipFile(zipobj, 'w') as zipf:
            for root, _, files in os.walk(local_dir):
                for f in files:
                    file_path = os.path.join(root, f)
                    zipf.write(
                        file_path,
                        os.path.relpath(file_path, local_dir)
                    )

    shutil.rmtree(TMP_DIR, ignore_errors=True)
    return zipobj