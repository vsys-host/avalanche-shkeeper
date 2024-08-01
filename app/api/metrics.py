import requests
import json
import prometheus_client
from prometheus_client import generate_latest, Info, Gauge
from web3 import Web3, HTTPProvider
from web3.middleware import geth_poa_middleware 

from . import metrics_blueprint
from ..config import config
from ..models import Settings, db


prometheus_client.REGISTRY.unregister(prometheus_client.GC_COLLECTOR)
prometheus_client.REGISTRY.unregister(prometheus_client.PLATFORM_COLLECTOR)
prometheus_client.REGISTRY.unregister(prometheus_client.PROCESS_COLLECTOR)


def get_latest_release(name):
    if name == 'avalanchego':
        url = 'https://api.github.com/repos/ava-labs/avalanchego/releases/latest'
    else:
        return False
    data = requests.get(url).json()
    version = data["tag_name"].split('v')[1]
    info = { key:data[key] for key in ["name", "tag_name", "published_at"] }
    info['version'] = version
    return info


def get_all_metrics():
    w3 = Web3(HTTPProvider(config["FULLNODE_URL"], request_kwargs={'timeout': int(config['FULLNODE_TIMEOUT'])}))
    w3.middleware_onion.inject(geth_poa_middleware, layer=0)

    if w3.isConnected:
        response = {}
        last_fullnode_block_number = w3.eth.block_number
        response['last_fullnode_block_number'] = last_fullnode_block_number
        response['last_fullnode_block_timestamp'] = w3.eth.get_block(w3.toHex(last_fullnode_block_number))['timestamp']
    
        json_info = {"jsonrpc":"2.0", "id":1, "method" :"info.getNodeVersion"}
        try:
            r_info = requests.post(config["FULLNODE_INFO_URL"], json=json_info).json()
        except Exception as e:
            r_info = {"result":{"vmVersions":{"platform":"v999.999.999"}}}
        avalanchego_version = r_info["result"]["vmVersions"]["platform"]
        response['avalanchego_version'] = avalanchego_version
    
        pd = Settings.query.filter_by(name = 'last_block').first()
        last_checked_block_number = int(pd.value)
        response['avalanche_wallet_last_block'] = last_checked_block_number
        block =  w3.eth.get_block(w3.toHex(last_checked_block_number))
        response['avalanche_wallet_last_block_timestamp'] = block['timestamp']
        response['avalanche_fullnode_status'] = 1
        return response
    else:
        response['avalanche_fullnode_status'] = 0
        return response

geth_last_release = Info(
    'avalanchego_last_release',
    'Version of the latest release from https://github.com/ava-labs/avalanchego/releases'
)


geth_last_release.info(get_latest_release('avalanchego'))

geth_fullnode_version = Info('avalanche_fullnode_version', 'Current geth version in use')

avalanche_fullnode_status = Gauge('avalanche_fullnode_status', 'Connection status to avalanche fullnode')

avalanche_fullnode_last_block = Gauge('avalanche_fullnode_last_block', 'Last block loaded to the fullnode', )
avalanche_wallet_last_block = Gauge('avalanche_wallet_last_block', 'Last checked block ')  #.set_function(lambda: BlockScanner().get_last_seen_block_num())

avalanche_fullnode_last_block_timestamp = Gauge('avalanche_fullnode_last_block_timestamp', 'Last block timestamp loaded to the fullnode', )
avalanche_wallet_last_block_timestamp = Gauge('avalanche_wallet_last_block_timestamp', 'Last checked block timestamp')


@metrics_blueprint.get("/metrics")
def get_metrics():
    response = get_all_metrics()
    if response['avalanche_fullnode_status'] == 1:
        geth_fullnode_version.info({'version': response['avalanchego_version']})
        avalanche_fullnode_last_block.set(response['last_fullnode_block_number'])
        avalanche_fullnode_last_block_timestamp.set(response['last_fullnode_block_timestamp'])
        avalanche_wallet_last_block.set(response['avalanche_wallet_last_block'])
        avalanche_wallet_last_block_timestamp.set(response['avalanche_wallet_last_block_timestamp'])
        avalanche_fullnode_status.set(response['avalanche_fullnode_status'])
    else:
        avalanche_fullnode_status.set(response['avalanche_fullnode_status'])

    return generate_latest().decode()
