# use a virtualenv
```shell
sudo apt update
sudo apt install -y python3-venv python3-full

# create a venv for ansible/azure
python3 -m venv ~/.venvs/ansible-azure

# activate it
source ~/.venvs/ansible-azure/bin/activate

# upgrade pip tooling inside venv
pip install -U pip setuptools wheel

# install Azure collection python deps
pip install -r ~/.ansible/collections/ansible_collections/azure/azcollection/requirements.txt
```