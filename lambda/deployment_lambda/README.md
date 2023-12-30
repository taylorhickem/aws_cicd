# deployment lambda
builds the lambda function from source code in S3 bucket. The lambda should already be created with correct configuration, IAM policy and triggers.

## Arguments
the lambda funciton does not accept any arguments in the *event* context. 
It automatically detects any new file changes in the source code S3 bucket.

## ENVIRONMENT VARIABLES

S3_BUCKET: S3 bucket where the source code files are located

## lambda operation steps

1. download the source code files to /tmp 
2. zip the files
3. upload to lambda function code


## function source code directory
the source code files are located in the lambda function folder
 named <function_name>
```
<function_name>/
    lambda_function.py
    ... # config files, local modules
```

## source code bucket directory
the lambda function folder is located in the `/lambda` subdirectory
```
<S3_BUCKET>/
    /git
    /lambda
        /<function_name>
        ... # other lambda functions
```

### boto3: update_function_code
https://boto3.amazonaws.com/v1/documentation/api/latest/reference/services/lambda/client/update_function_code.html

`Lambda.Client.update_function_code(**kwargs)`

```
response = client.update_function_code(
    FunctionName='string',
    ZipFile=b'bytes',
    S3Bucket='string',
    S3Key='string',
    S3ObjectVersion='string',
    ImageUri='string',
    Publish=True|False,
    DryRun=True|False,
    RevisionId='string',
    Architectures=[
        'x86_64'|'arm64',
    ]
)
```