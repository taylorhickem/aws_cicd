## boto3: update_function_code
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