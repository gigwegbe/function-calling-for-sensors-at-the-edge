!/bin/bash
aws ecr create-repository --repository-name thingsboard-stack/integration
aws ecr create-repository --repository-name thingsboard-stack/publisher

docker tag thingsboard-integration:latest 390403863289.dkr.ecr.us-east-1.amazonaws.com/thingsboard-stack/integration:latest
docker push 390403863289.dkr.ecr.us-east-1.amazonaws.com/thingsboard-stack/integration:latest

docker tag thingsboard_publisher:latest 390403863289.dkr.ecr.us-east-1.amazonaws.com/thingsboard-stack/publisher:latest
docker push 390403863289.dkr.ecr.us-east-1.amazonaws.com/thingsboard-stack/publisher:latest
aws ecr get-login-password --region us-east-1 | docker login --username AWS --password-stdin 390403863289.dkr.ecr.us-east-1.amazonaws.com

docker rmi -f $(docker images | grep control-panel | awk '{print $3}')

docker build -t thingsboard-control:latest .
docker tag thingsboard-control:latest 390403863289.dkr.ecr.us-east-1.amazonaws.com/thingsboard-stack/control-panel:latest
docker push 390403863289.dkr.ecr.us-east-1.amazonaws.com/thingsboard-stack/control-panel:latest
aws ecr get-login-password --region us-east-1 | docker login --username AWS --password-stdin 390403863289.dkr.ecr.us-east-1.amazonaws.com
aws ecr create-repository --repository-name thingsboard-stack/control-panel
docker push 390403863289.dkr.ecr.us-east-1.amazonaws.com/thingsboard-stack/control-panel:latest

# ssh -i ~/thingsboard-key.pem ec2-user@172.31.17.255
ssh -i ~/thingsboard-key.pem ec2-user@ec2-54-145-56-199.compute-1.amazonaws.com

docker stop $(docker ps -aq)
docker rm $(docker ps -aq)
docker rmi -f $(docker images -aq)
docker volume rm $(docker volume ls -q)
docker network prune -f

# Stop and remove the running control-panel container
docker-compose stop control-panel
docker-compose rm -f control-panel

# Remove the existing control-panel image
docker rmi 390403863289.dkr.ecr.us-east-1.amazonaws.com/thingsboard-stack/control-panel:latest

# Pull the latest control-panel image from ECR
aws ecr get-login-password --region us-east-1 | docker login --username AWS --password-stdin 390403863289.dkr.ecr.us-east-1.amazonaws.com
docker pull 390403863289.dkr.ecr.us-east-1.amazonaws.com/thingsboard-stack/control-panel:latest

# Run docker-compose to recreate and start the control-panel container
docker-compose up -d
docker logs ec2-user_control-panel_1
# Remove the existing control-panel image
docker rmi 390403863289.dkr.ecr.us-east-1.amazonaws.com/thingsboard-stack/control-panel:latest

# Pull the latest control-panel image from ECR
aws ecr get-login-password --region us-east-1 | docker login --username AWS --password-stdin 390403863289.dkr.ecr.us-east-1.amazonaws.com
docker pull 390403863289.dkr.ecr.us-east-1.amazonaws.com/thingsboard-stack/control-panel:latest

# Run docker-compose to recreate and start the control-panel container
docker-compose up -d

aws ec2 authorize-security-group-ingress --group-id sg-0f82ae45f9a580cdf --protocol tcp --port 5000 --cidr 0.0.0.0/0


docker build -t 390403863289.dkr.ecr.us-east-1.amazonaws.com/thingsboard-stack/llm-service ./llm
docker push 390403863289.dkr.ecr.us-east-1.amazonaws.com/thingsboard-stack/llm-service:latest
chainlit run sensor_chat.py --port 8000


instance_public_ip = "3.89.163.209"
ssh -i ~/thingsboard-key.pem ec2-user@3.89.163.209


---------------------------------------------------------------------------------
|                               DescribeInstances                               |
+----------------------+-----------------------+------------------+-------------+
|       Instance       |         Name          | PublicIpAddress  |    State    |
+----------------------+-----------------------+------------------+-------------+
|  i-0d35eca83375207d2 |  ThingsBoardInstance  |  3.89.163.209    |  running    |
|  i-01f526684b7946352 |  ThingsBoardInstance  |  None            |  terminated |
+----------------------+-----------------------+------------------+-------------+

aws ec2 describe-instances --instance-ids i-0d35eca83375207d2 --query 'Reservations[*].Instances[*].[InstanceId,Tags[?Key==`Name`].Value,PublicIpAddress,State.Name]' --output table
-------------------------
|   DescribeInstances   |
+-----------------------+
|  i-0d35eca83375207d2  |
|  ThingsBoardInstance  |
|  3.89.163.209         |
|  running              |
+-----------------------+
aws ecr get-login-password --region us-east-1 | docker login --username AWS --password-stdin 390403863289.dkr.ecr.us-east-1.amazonaws.com
aws configure list
cat ~/.aws/config
cat ~/.aws/credentials
sudo yum update -y
sudo yum install -y docker
sudo service docker start
sudo usermod -a -G docker ec2-user
ls -l /usr/lib64/libcrypt.so.1sudo yum install -y libxcrypt-compat