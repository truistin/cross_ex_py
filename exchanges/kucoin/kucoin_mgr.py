import hmac
import hashlib
import requests
import json
import time
import base64
import urllib.parse
from model.model import Balance, WithdrawalStatus, Status, Position, Chain

class KucoinMgr():
    api_key: str
    secrect_key: str
    passphrase: str
    withdrawals_records: dict
    deposits_records: dict
    pairs_info: dict

    def __init__(self, api_key, secrect_key, passphrase = ''):
        self.api_key = api_key
        self.secrect_key = secrect_key
        self.passphrase = passphrase
        self.withdrawals_records = {}
        self.deposits_records = {}
        self.pairs_info = {}

    def fetch_now_px(self):
        resp = requests.get("https://api-futures.kucoin.com/api/v1/contracts/active").json()
        px_map = {}
        for item in resp['data']:
            px_map[item['symbol']] = float(item['markPrice'])
        return px_map

    def fetch_pairs_info(self):
        resp = requests.get("https://api-futures.kucoin.com/api/v1/contracts/active").json()
        for item in resp['data']:
            self.pairs_info[item['symbol']] = float(item['multiplier'])

    def gen_sign(self, method, request_path = '', body_string = ''):
        timestamp = str(int(time.time() * 1000))
        prehash = timestamp + method.upper() + request_path + body_string
        signature = base64.b64encode(hmac.new(self.secrect_key.encode('utf-8'), prehash.encode('utf-8'), digestmod=hashlib.sha256).digest()).decode()
        headers = {
            "KC-API-KEY": self.api_key,
            "KC-API-SIGN": signature,
            "KC-API-TIMESTAMP": timestamp,
            "KC-API-PASSPHRASE": self.passphrase,
            "Content-Type": "application/json"
        }
        return headers

    def set_leverage(self, symbol, leverage):
        params = {}
        params['symbol'] = symbol
        params['leverage'] = str(leverage)
        body = json.dumps(params)
        request_path = '/api/v2/changeCrossUserLeverage'
        url = 'https://api-futures.kucoin.com' + request_path
        method = 'POST'
        headers = self.gen_sign(method = method, request_path = request_path, body_string = body)
        resp = requests.request(method, url, headers=headers, data=body, timeout=10).json()
        return resp

    def fetch_spot_balance(self):  ###资金账户
        params = {}
        params['currency'] = 'USDT'
        params['type'] = 'main'
        request_path = '/api/v1/accounts' + '?' + urllib.parse.urlencode(params)
        method = 'GET'
        headers = self.gen_sign(method = method, request_path = request_path, body_string='')
        url = 'https://api.kucoin.com' + request_path
        resp = requests.request(method, url, headers=headers, timeout=10).json()
        bal = Balance()
        for item in resp['data']:
            if item['currency'] == 'USDT':
                bal.currency = item['currency']
                bal.available = float(item['available'])
                bal.locked = float(item['holds'])
                bal.equity = float(item['balance'])
                #print(bal)
                return bal
        return bal

    def fetch_future_balance(self):
        params = {}
        params['currency'] = 'USDT'
        request_path = '/api/v1/account-overview' + '?' + urllib.parse.urlencode(params)
        method = 'GET'
        headers = self.gen_sign(method = method, request_path = request_path, body_string='')
        url = 'https://api-futures.kucoin.com' + request_path
        resp = requests.request(method, url, headers=headers, timeout=10).json()
        bal = Balance()
        #print(resp)
        bal.currency = resp['data']['currency']
        bal.available = float(resp['data']['availableBalance'])
        bal.equity = float(resp['data']['accountEquity'])
        bal.locked = bal.equity - bal.available
        print(bal)
        return bal

    def asset_transfer_inner(self, coin, from_field, to_field, amount):
        params = {}
        params['clientOid'] = 'kucoin-' + str(int(time.time() * 1000))
        params['currency'] = coin
        params['amount'] = str(amount)
        params['type'] = 'INTERNAL'
        if from_field == 'spot':
            params['fromAccountType'] = 'MAIN'
            params['toAccountType'] = 'CONTRACT'
        else:
            params['fromAccountType'] = 'CONTRACT'
            params['toAccountType'] = 'MAIN'
        body = json.dumps(params)
        request_path = '/api/v3/accounts/universal-transfer'
        url = 'https://api.kucoin.com' + request_path
        method = 'POST'
        headers = self.gen_sign(method = method, request_path = request_path, body_string = body)
        resp = requests.request(method, url, headers=headers, data=body, timeout=10).json()
        print(resp)
        if resp['code'] == '200000': ##成功
            return 0, resp
        else:
            return 1, resp

    def withdrawals(self, coin, to_exch, address, chain, amount):
        params = {}
        params['currency'] = coin
        params['toAddress'] = address
        params['amount'] = str(amount)
        params['withdrawType'] = 'ADDRESS'
        if chain == Chain.ERC20:
            params['chain'] = 'eth'
        elif chain == Chain.TRC20:
            params['chain'] = 'trx'
        params['isInner'] = False
        body = json.dumps(params)
        request_path = '/api/v3/withdrawals'
        url = 'https://api.kucoin.com' + request_path
        method = 'POST'
        headers = self.gen_sign(method = method, request_path = request_path, body_string = body)
        resp = requests.request(method, url, headers=headers, data=body, timeout=10).json()
        print(resp)
        if resp['code'] != '200000':
            status = Status.FAIL
            return WithdrawalStatus(currency=coin, tx_id='0', withdraw_clt_id='0', 
                amount=amount, to_exch= to_exch, address=address, chain=chain, status=status, msg=resp)
        else:
            status = Status.PENDING
            return WithdrawalStatus(
                currency=coin, tx_id=resp['data']['withdrawalId'], withdraw_clt_id=resp['data']['withdrawalId'], 
                amount=amount, to_exch= to_exch, address=address, chain=chain, status=status, msg=resp)

    def query_withdrawals_record(self, withdraw_clt_id):
        params = {}
        request_path = f'/api/v1/withdrawals/{withdraw_clt_id}' + '?' + urllib.parse.urlencode(params)
        method = 'GET'
        headers = self.gen_sign(method = method, request_path = request_path, body_string='')
        url = 'https://api.kucoin.com' + request_path
        resp = requests.request(method, url, headers=headers, timeout=10).json()
        print(resp)
        if resp['code'] != '200000':
            return Status.FAIL, resp
        else:
            if resp['data']['status'] == 'SUCCESS': #转账成功
                return Status.SUCC, resp
            elif resp['data']['status'] in ('REVIEW', 'PROCESSING', 'WALLET_PROCESSING'): #转账中
                return Status.PENDING, resp
            else:
                return Status.FAIL, resp

    def query_desposite_record(self, tx_id):
        params = {}
        params['currency'] = 'USDT'
        params['pageSize'] = '500'
        request_path = f'/api/v1/deposits' + '?' + urllib.parse.urlencode(params)
        method = 'GET'
        headers = self.gen_sign(method = method, request_path = request_path, body_string='')
        url = 'https://api.kucoin.com' + request_path
        resp = requests.request(method, url, headers=headers, timeout=10).json()
        print(resp)
        if resp['code'] != '200000':
            return Status.FAIL, resp
        else:
            for item in resp['data']['items']:
                if item['walletTxId'] == tx_id:
                    if item['status'] == 'SUCCESS':
                        return Status.SUCC, item
                    elif item['status'] in ('PROCESSING', 'WAIT_TRM_MGT'):
                        return Status.PENDING, item
                    else:
                        return Status.FAIL, item
            return Status.FAIL, f'not found kucoin deposite tx_id:{tx_id}'


    def get_future_pos(self):
        params = {}
        positions = {}
        params['currency'] = 'USDT'
        request_path = '/api/v1/positions' + '?' + urllib.parse.urlencode(params)
        method = 'GET'
        headers = self.gen_sign(method = method, request_path = request_path, body_string='')
        url = 'https://api-futures.kucoin.com' + request_path
        resp = requests.request(method, url, headers=headers, timeout=10).json()
        print(resp)
        for item in resp['data']:
            pos = Position(symbol = item['symbol'], size = float(item['currentQty']) * self.pairs_info[item['symbol']], entry_price = float(item['avgEntryPrice']), liq_price = float(item['liquidationPrice']), leverage = float(item['leverage']), now_price = float(item['markPrice']))
            positions[item['symbol']] = pos
        #print(resp)
        print(positions)
        return positions