# AWS CICD
source code for AWS CICD used to automate 
deployment on AWS resources 

## directory

```
/lambda
    /layer_version_update
        lambda_function.py
.gitignore
LICENSE
README.md
requirements.txt
```

## lambda functions

1. [layer-version-update](#layer-version-update)

## layer-version-update

This lambda function detects any new file changes in the SOURCE
S3 bucket location, and updates a new Lambda layer version with the new
*.zip file.

`<layer_name>-<version_tag>.zip`

If the layer already exists, then a new version is created
If the layer does not already exist, then a new layer is created.
In both cases, the version tag is extracted from the name of the *.zip file.