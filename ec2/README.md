## configure EC2 instance

### installation

_pre-installed_
1. python 3.9
2. aws cli

_manual install_
1. yum setup
2. git
3. pip
4. python libraries
    - boto3

### configuration

1. git SSH credentials

### connect to Github by SSH
[stackoverflow: connect EC2 to git by SSH](https://stackoverflow.com/questions/69049281/connect-ec2-to-git-by-ssh)

1. generate an RSA key pair using keygen

```
ssh-keygen -t rsa 
Generating public/private rsa key pair.
Enter file in which to save the key (/home/ec2-user/.ssh/id_rsa): (enter)
Enter passphrase (empty for no passphrase):  (enter)
Enter same passphrase again: (enter)
Your identification has been saved in /home/ec2-user/.ssh/id_rsa
Your public key has been saved in /home/ec2-user/.ssh/id_rsa.pub
The key fingerprint is:
****
The key's randomart image is:
****
...
```

2. login to git and register the __public__ key to your account
[github keys](https://github.com/settings/keys)

3. set private key permission

```
chmod 400 id_rsa
```

4. test the connection for the first time

```
ssh -T git@github.com
```

```
> The authenticity of host 'github.com (IP ADDRESS)' can't be established.
> RSA key fingerprint is SHA256:nThbg6kXUpJWGl7E1IGOCspRomTxdCARLviKw6E5SY8.
> Are you sure you want to continue connecting (yes/no)?
Verify that the fingerprint in the message you see matches GitHub's RSA public key fingerprint.
```

just type "yes"