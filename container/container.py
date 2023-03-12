import paramiko
import base64
import io
import os
import boto3

class Container():
    region = 'sa-east-1'
    ecs_service_name = 'valheim'
    world_saves_location = '/home/steam/.config/unity3d/IronGate/Valheim/worlds_local'

    def __init__(self, cluster):
        self.cluster = cluster
        self.ecs_client = boto3.client("ecs", region_name=self.region)

    def get_ecs_instance_public_ip(self):
        try:
            instance_arn = self.ecs_client.list_container_instances(
                cluster=self.cluster,
                maxResults=1
            )['containerInstanceArns'][0]
            ec2_instance_id = self.ecs_client.describe_container_instances(
                cluster=self.cluster,
                containerInstances=[instance_arn]
            )['containerInstances'][0]['ec2InstanceId']
            ec2 = boto3.client('ec2', region_name=self.region)
            ec2_public_ip = ec2.describe_instances(
                InstanceIds=[ec2_instance_id]
            )['Reservations'][0]['Instances'][0]['PublicIpAddress']
            return ec2_public_ip
        except Exception as e:
            return e

    def new_ssh_client(self):
        ec2_public_ip = self.get_ecs_instance_public_ip()
        ssh_key = base64.b64decode(os.environ['SSH_KEY']).decode('utf-8')
        key_file_obj = io.StringIO(ssh_key)
        pem_key = paramiko.RSAKey.from_private_key(key_file_obj)
        client = paramiko.SSHClient()
        client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        print(f'connecting to instance {ec2_public_ip}')
        client.connect(hostname=ec2_public_ip, username='ec2-user', pkey=pem_key)
        return client 
        
    def exec_in_container(self, cmd, path='/root'):
        try:
            client = self.new_ssh_client()
        except Exception as e:
            print(e)
            return e
        try:
            _, stdout, _ = client.exec_command("printf $(docker ps -aqf 'name=valheim')")
            valheim_container_id = stdout.read().decode()
            docker_exec_cmd = f"docker exec -w {path} -it {valheim_container_id} {cmd}"
            print(f'executing command: "{docker_exec_cmd}"')
            _, stdout, _ = client.exec_command(f"exec {docker_exec_cmd}", get_pty=True)
            result = stdout.read().decode()
            print(result)
            client.close()
            return result
        except Exception as e:
            print(e)
            client.close()
            return e

    def get_worlds_local_file_count(self):
        return self.exec_in_container(f'ls -l {self.world_saves_location} | wc -l')

    def compress_files(self, bkp_file_name):
        self.exec_in_container(cmd=f'sh -c "ls -t | tail -n +13 | xargs rm"', path=self.world_saves_location)
        self.exec_in_container(cmd=f'sh -c "tar -zcvf {bkp_file_name} ."', path=self.world_saves_location)

    def copy_bkp_from_container_to_ecs_agent(self, bkp_file_name):
        client = self.new_ssh_client()
        _, stdout, _ = client.exec_command("printf $(docker ps -aqf 'name=valheim')")
        valheim_container_id = stdout.read().decode()
        docker_cp_cmd = f"docker cp {valheim_container_id}:{self.world_saves_location}/{bkp_file_name} /home/ec2-user/{bkp_file_name}"
        print(f"Running command: {docker_cp_cmd}")
        try:
            _, stdout, _ = client.exec_command(docker_cp_cmd)
        except Exception as e:
            client.close()
            return e
        client.close()
        self.exec_in_container(cmd=f'rm {bkp_file_name}', path=self.world_saves_location)

    def copy_bkp_from_ecs_agent(self, from_path: str, to_path: str):
        ssh_client = self.new_ssh_client()
        ftp_client = ssh_client.open_sftp()
        try: 
            # TO DO: CLEAN BACKUP FILES
            ftp_client.get(from_path, to_path)
        except Exception as e:
            print(e)
        ftp_client.close()