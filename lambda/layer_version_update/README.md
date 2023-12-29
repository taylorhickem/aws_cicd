# layer-version-update

This lambda function detects any new file changes in the SOURCE
S3 bucket location, and updates a new Lambda layer version with the new
*.zip file.

`<layer_name>-<version_tag>.zip`

If the layer already exists, then a new version is created
If the layer does not already exist, then a new layer is created.
In both cases, the version tag is extracted from the name of the *.zip file.