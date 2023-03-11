import boto3
import botocore.exceptions as awserr
import re
import asyncio
import paramiko
import base64
import os
import io
import storage.s3 as storage
import container.container as valheim_container

class Valheim:
    region = 'sa-east-1'
    asg_name = 'valheim-ec2-cluster'
    ecs_service_name = 'valheim'
    log_group_name = 'valheim-container'
    num_files = None
    guild = None
    world_saves_location = '/home/steam/.config/unity3d/IronGate/Valheim/worlds_local'

    def __init__(self, cluster):
        self.cluster = cluster
        self.asg_client = boto3.client("autoscaling", region_name=self.region)
        self.ecs_client = boto3.client("ecs", region_name=self.region)
        self.logs_client = boto3.client("logs", region_name=self.region)
        self.valheim_container = valheim_container.Container(cluster=cluster)

    def task_status(self):
        tasks = self.ecs_client.list_tasks(cluster=self.cluster)
        if len(tasks["taskArns"]) != 0:
            task = self.ecs_client.describe_tasks(cluster=self.cluster,tasks=tasks["taskArns"])
            return task["tasks"][0]["lastStatus"], task["tasks"][0]["taskArn"].split("/")[-1]
        else:
            return 'STOPPED', None
    
    def gameserver_status(self, task_name):
        # Define the log group and stream name
        log_stream_name = f'valheim/valheim-latest/{task_name}'

        # Get the log events
        try: 
            response = self.logs_client.get_log_events(
                logGroupName=self.log_group_name,
                logStreamName=log_stream_name,
            )
        except awserr.ClientError as err:
            if err.response['Error']['Code'] == 'ResourceNotFoundException':
                return 'TASK LOGS NOT FOUND'

        status = 'NOT LOADED'
        for event in response['events']:
            if re.search("^\d{2}/\d{2}/\d{4} \d{2}:\d{2}:\d{2}: Game server connected$", event['message']):
                status = 'LOADED'
                break
        return status

    def status(self):
        # Possible status: LOADED, LOADING, RUNNING, PENDING, STOPPED
        task = self.task_status()
        if task[0] == 'RUNNING':
            if self.gameserver_status(task[1]) != 'LOADED':
                return 'LOADING'
            else:
                return 'LOADED'
        else:
            return task[0]


    async def start(self):
        self.asg_client.set_desired_capacity(
            AutoScalingGroupName=self.asg_name,
            DesiredCapacity=1
        )
        while not self.cluster_has_infra():
            print('scaling asg and associating instance to cluster')
            await asyncio.sleep(2)
        self.ecs_client.update_service(
            cluster=self.cluster,
            service=self.ecs_service_name,
            desiredCount=1
        )

    def stop(self):
        self.ecs_client.update_service(
            cluster=self.cluster,
            service=self.ecs_service_name,
            desiredCount=0
        )
        self.asg_client.set_desired_capacity(
            AutoScalingGroupName=self.asg_name,
            DesiredCapacity=0
        )

    def cluster_has_infra(self):
        container_instance_count = self.ecs_client.describe_clusters(
            clusters=[self.cluster]
        )['clusters'][0]['registeredContainerInstancesCount']
        if container_instance_count == 1:
            return True
        else:
            return False

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
            client.close()
            return result
        except Exception as e:
            print(e)
            client.close()
            return e

    def get_storage_details(self):
        try:
            valheim_container_dfh = self.valheim_container.exec_in_container('df -h --output=pcent,target')
            return valheim_container_dfh
        except Exception as e:
            print(e)
            return e

    def get_worlds_local_file_count(self):
        return self.exec_in_container(f'ls -l {self.world_saves_location} | wc -l')

    def compress_extra_files(self, bkp_file_name):
        self.exec_in_container(cmd=f'sh -c "tar -zcvf {bkp_file_name} *2023*"', path=self.world_saves_location)

    def copy_bkp_from_container_to_ecs_agent(self, bkp_file_name):
        client = self.new_ssh_client()
        _, stdout, _ = client.exec_command("printf $(docker ps -aqf 'name=valheim')")
        valheim_container_id = stdout.read().decode()
        docker_cp_cmd = f"docker cp {valheim_container_id}:{self.world_saves_location}/{bkp_file_name} {self.world_saves_location}/{bkp_file_name}"
        _, stdout, _ = client.exec_command(docker_cp_cmd)
        self.exec_in_container(f'rm {self.world_saves_location}/{bkp_file_name}')
        result = stdout.read().decode()
        client.close()
        print(result)

    def copy_bkp_from_ecs_agent(self, bkp_file):
        ftp_client = self.new_ssh_client().open_sftp()
        ftp_client.get(bkp_file, bkp_file)
        ftp_client.close()
    
    def make_valheim_bkp(self):
        bkp_file_name = 'bkp.tar.gz'
        print('Compressing files')
        self.compress_extra_files(bkp_file_name)
        print('Copying from container')
        self.copy_bkp_from_container_to_ecs_agent(f'~/{bkp_file_name}')
        print('Copying from ecs agent')
        self.copy_bkp_from_ecs_agent(f'~/{bkp_file_name}')
        print(os.listdir('~'))
        # Create an instance of the S3Storage class
        s3_storage = storage.S3Storage(bucket='valheim-backup-rda')
        # Read the contents of a file
        with open(f'~/{bkp_file_name}', 'rb') as f:
            file_contents = f.read()
        # Put the file in the S3 bucket
        response = s3_storage.put(key='my-file.txt', data=file_contents)
        print(response)

