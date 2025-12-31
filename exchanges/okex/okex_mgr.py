import hmac
import hashlib
import requests
import json
import time
import base64
import urllib.parse
from datetime import datetime, timezone
from model.model import Balance, WithdrawalStatus, Status, Position, Chain

class OkexMgr():
    api_key: str
    secrect_key: str
    passphrase: str
    pairs_info: dict

    def __init__(self, api_key, secrect_key, passphrase = ''):
        self.api_key = api_key
        self.secrect_key = secrect_key
        self.passphrase = passphrase
        self.pairs_info = {}

    def fetch_pairs_info(self):
        resp = requests.get("https://www.okx.com/api/v5/public/instruments?instType=SWAP").json()
        for item in resp['data']:
            self.pairs_info[item['instId']] = float(item['ctVal']) * float(item['ctMult'])

    def gen_sign(self, method, request_path = '', body_string = ''):
        ts = datetime.utcnow().replace(tzinfo=timezone.utc) \
            .isoformat(timespec='milliseconds').replace("+00:00", "Z")
        prehash = ts + method.upper() + request_path + body_string
        mac = hmac.new(
            self.secrect_key.encode("utf-8"),
            prehash.encode("utf-8"),
            hashlib.sha256
        )
        signature = base64.b64encode(mac.digest()).decode()
        return {
            "OK-ACCESS-KEY": self.api_key,
            "OK-ACCESS-SIGN": signature,
            "OK-ACCESS-TIMESTAMP": ts,
            "OK-ACCESS-PASSPHRASE": self.passphrase,
            "Content-Type": "application/json"
        }

    def set_leverage(self, symbol, leverage):
        params = {}
        params['instId'] = symbol
        params['lever'] = str(leverage)
        params['mgnMode'] = 'cross'
        body = json.dumps(params)
        request_path = '/api/v5/account/set-leverage'
        url = 'https://www.okx.com' + request_path
        method = 'POST'
        headers = self.gen_sign(method = method, request_path = request_path, body_string = body)
        resp = requests.request(method, url, headers=headers, data=body, timeout=10).json()
        return resp

    def fetch_spot_balance(self): ##资金账户
        params = {}
        params['ccy'] = 'USDT'
        request_path = '/api/v5/asset/balances' + '?' + urllib.parse.urlencode(params)
        method = 'GET'
        url = 'https://www.okx.com' + request_path
        headers = self.gen_sign(method, request_path, "")
        resp = requests.request(method, url, headers=headers, timeout=10).json()
        print(resp)
        bal = Balance()
        for item in resp['data']:
            if item['ccy'] == 'USDT':
                bal.currency = item['ccy']
                bal.available = float(item['availBal'])
                bal.locked = float(item['frozenBal'])
                bal.equity = float(item['bal'])
                print(bal)
                return bal
        return bal
    
    def fetch_future_balance(self):
        params = {}
        params['ccy'] = 'USDT'
        request_path = '/api/v5/account/balance' + '?' + urllib.parse.urlencode(params)
        method = 'GET'
        url = 'https://www.okx.com' + request_path
        headers = self.gen_sign(method, request_path, "")
        resp = requests.request(method, url, headers=headers, timeout=10).json()
        print(resp)
        bal = Balance()
        for item in resp['data'][0]['details']:
            if item['ccy'] == 'USDT':
                bal.currency = item['ccy']
                bal.available = float(item['availEq'])
                bal.locked = float(item['ordFrozen'])
                bal.equity = float(item['eq'])
                print(bal)
                return bal
        return bal

    def asset_transfer_inner(self, coin, from_field, to_field, amount):
        params = {}
        params['type'] = '0'
        params['ccy'] = coin
        params['amt'] = str(amount)
        if from_field == 'spot':
            params['from'] = '6'
            params['to'] = '18'
        else:
            params['from'] = '18'
            params['to'] = '6'
        body = json.dumps(params)
        request_path = '/api/v5/asset/transfer'
        url = 'https://www.okx.com' + request_path
        method = 'POST'
        headers = self.gen_sign(method = method, request_path = request_path, body_string = body)
        resp = requests.request(method, url, headers=headers, data=body, timeout=10).json()
        print(resp)
        if resp['code'] == '0': ##成功
            return 0, resp
        else:
            return 1, resp
    
    def withdrawals(self,coin, to_exch, address, chain, amount):
        params = {}
        params['ccy'] = coin
        params['amt'] = amount
        params['dest'] = '4'
        params['toAddr'] = address
        params['toAddrType'] = '1'
        if chain == Chain.ERC20:
            params['chain'] = 'USDT-ERC20'
        elif chain == Chain.TRC20:
            params['chain'] = 'USDT-TRC20'
        params['clientId'] = 'okex_withdrawals_' + str(int(time.time() * 1000))
        body = json.dumps(params)
        request_path = '/api/v5/asset/withdrawal'
        url = 'https://www.okx.com' + request_path
        method = 'POST'
        headers = self.gen_sign(method = method, request_path = request_path, body_string = body)
        resp = requests.request(method, url, headers=headers, data=body, timeout=10).json()
        print(resp)
        if resp['code'] != '0':
            msg = resp
            return WithdrawalStatus(
                currency=coin, tx_id=None, withdraw_clt_id=params['clientId'], 
                amount=amount, to_exch=to_exch, address=address, chain=chain, status=Status.FAIL, msg=msg)
        else:
            item = resp['data'][0]
            return WithdrawalStatus(
                currency=coin, tx_id=item['wdId'], withdraw_clt_id=item['clientId'], 
                amount=item['amt'], to_exch=to_exch, address=address, chain=chain, status=Status.PENDING, msg=None)


    def query_withdrawals_record(self, coin, withdraw_clt_id):
        params = {}
        params['ccy'] = coin
        params['clientId'] = withdraw_clt_id
        params['type'] = '4'
        request_path = '/api/v5/asset/withdrawal-history' + '?' + urllib.parse.urlencode(params)
        method = 'GET'
        url = 'https://www.okx.com' + request_path
        headers = self.gen_sign(method, request_path, "")
        resp = requests.request(method, url, headers=headers, timeout=10).json()
        print(resp)
        if resp['code'] != '0':
            return Status.FAIL, resp
        else:
            item = resp['data'][0]
            if item['state'] == '2': #提币成功
                return Status.SUCC, resp
            elif item['state'] in ('-2', '-1'):
                return Status.FAIL, resp
            else:
                return Status.PENDING, resp

    def query_desposite_record(self, tx_id):
        params = {}
        params['ccy'] = 'USDT'
        params['txId'] = tx_id
        params['type'] = '4'
        request_path = '/api/v5/asset/deposit-history' + '?' + urllib.parse.urlencode(params)
        method = 'GET'
        url = 'https://www.okx.com' + request_path
        headers = self.gen_sign(method, request_path, "")
        resp = requests.request(method, url, headers=headers, timeout=10).json()
        print(resp)
        if resp['code'] != '0':
            return Status.FAIL, resp
        else:
            item = resp['data'][0]
            if item['state'] == '2': #成功  
                return Status.SUCC, resp
            elif item['state'] in ('0', '1'):
                return Status.PENDING, resp
            else:
                return Status.FAIL, resp

    def get_future_pos(self):
        params = {}
        positions = {}
        params['instType'] = 'SWAP'
        request_path = '/api/v5/account/positions' + '?' + urllib.parse.urlencode(params)
        method = 'GET'
        url = 'https://www.okx.com' + request_path
        headers = self.gen_sign(method, request_path, "")
        resp = requests.request(method, url, headers=headers, timeout=10).json()
        print(resp)
        for item in resp['data']:
            pos = Position(symbol = item['instType'], size = float(item['availPos']) * self.pairs_info[item['instType']], entry_price = float(item['avgPx']), liq_price = float(item['liqPx']), leverage = float(item['lever']), now_price = float(item['last']))
            positions[item['instType']] = pos
        #print(resp)
        print(positions)
        return positions